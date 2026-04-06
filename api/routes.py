"""WorkAgent API 路由

定义 FastAPI 路由和端点。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import get_config
from core.agent import AgentRuntime
from core.hooks import HookManager
from core.types import AgentConfig
from llm.router import LLMRouter
from tools.builtin import get_builtin_registry
from tools.registry import ToolRegistry

logger = structlog.get_logger()


# ============== Pydantic 模型 ==============


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="消息角色: system, user, assistant")
    content: str = Field(..., description="消息内容")


class ChatCompletionRequest(BaseModel):
    """聊天完成请求"""
    model: str = Field(default="gpt-4o-mini", description="模型名称")
    messages: List[ChatMessage] = Field(..., description="消息列表")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, description="最大生成 token 数")
    tools: Optional[List[str]] = Field(default=None, description="指定可用工具列表")
    max_iterations: int = Field(default=10, ge=1, le=50, description="最大迭代次数")
    token_budget: int = Field(default=10000, ge=100, description="Token 预算")


class ChatCompletionResponse(BaseModel):
    """聊天完成响应"""
    id: str
    model: str
    content: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Dict[str, int]
    iterations: int
    execution_time: float


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    providers: List[str]
    tools: List[str]


# ============== 应用状态 ==============


class AppState:
    """应用状态"""
    def __init__(self):
        self.llm_router: Optional[LLMRouter] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.hook_manager: Optional[HookManager] = None
        self.version: str = "0.1.0"


app_state = AppState()


def init_app_state():
    """初始化应用状态"""
    # 初始化 LLM Router
    app_state.llm_router = LLMRouter().create_default()

    # 初始化工具注册表
    app_state.tool_registry = get_builtin_registry()

    # 初始化 Hook Manager
    app_state.hook_manager = HookManager()

    # 注册示例 Hook
    @app_state.hook_manager.on("agent:started")
    async def on_agent_started(event):
        logger.info("hook_agent_started", data=event.data)

    @app_state.hook_manager.on("agent:completed")
    async def on_agent_completed(event):
        logger.info("hook_agent_completed", iterations=event.data.get("result", {}).get("iterations"))

    logger.info(
        "app_state_initialized",
        providers=app_state.llm_router.list_providers(),
        tools=[t.name for t in app_state.tool_registry.list_tools()],
    )


# ============== 路由创建 ==============

def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    config = get_config()
    
    app = FastAPI(
        title="WorkAgent API",
        description="轻量级 AI Agent 框架 API",
        version="0.1.0",
    )

    # 添加 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # 前端开发服务器
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 错误处理
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    # ============== 路由 ==============

    @app.get("/api/tools")
    async def api_list_tools():
        """列出可用工具 (前端 API)"""
        if not app_state.tool_registry:
            raise HTTPException(status_code=503, detail="Service not ready")

        tools = app_state.tool_registry.list_tools()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "parameters": t.parameters,
                }
                for t in tools
            ]
        }

    @app.post("/api/agent/run")
    async def api_run_agent(request: ChatCompletionRequest):
        """运行 Agent (前端 API)"""
        if not app_state.llm_router or not app_state.tool_registry:
            raise HTTPException(status_code=503, detail="Service not ready")

        # 获取最后一条用户消息作为查询
        user_messages = [m for m in request.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message found")

        query = user_messages[-1].content

        # 创建 Agent 配置
        agent_config = AgentConfig(
            model=request.model,
            temperature=request.temperature,
            max_iterations=request.max_iterations,
            token_budget=request.token_budget,
            tools=request.tools,
        )

        # 创建 Agent Runtime
        agent = AgentRuntime(
            config=agent_config,
            llm_router=app_state.llm_router,
            tool_registry=app_state.tool_registry,
            hook_manager=app_state.hook_manager,
        )

        try:
            # 执行 Agent
            result = await agent.run(query)

            # 构建响应
            return ChatCompletionResponse(
                id=f"chatcmpl-{id(result)}",
                model=request.model,
                content=result.answer,
                tool_calls=[
                    {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                    for thought in result.thoughts
                    for tc in thought.tool_calls
                ],
                usage={
                    "prompt_tokens": result.tokens_used.prompt_tokens,
                    "completion_tokens": result.tokens_used.completion_tokens,
                    "total_tokens": result.tokens_used.total_tokens,
                },
                iterations=result.iterations,
                execution_time=result.execution_time,
            )

        except Exception as e:
            logger.error("chat_completion_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """健康检查端点"""
        return HealthResponse(
            status="healthy",
            version=app_state.version,
            providers=app_state.llm_router.list_providers() if app_state.llm_router else [],
            tools=[t.name for t in app_state.tool_registry.list_tools()] if app_state.tool_registry else [],
        )

    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(request: ChatCompletionRequest):
        """
        聊天完成端点

        支持 ReAct 循环和工具调用
        """
        if not app_state.llm_router or not app_state.tool_registry:
            raise HTTPException(status_code=503, detail="Service not ready")

        # 获取最后一条用户消息作为查询
        user_messages = [m for m in request.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message found")

        query = user_messages[-1].content

        # 创建 Agent 配置
        agent_config = AgentConfig(
            model=request.model,
            temperature=request.temperature,
            max_iterations=request.max_iterations,
            token_budget=request.token_budget,
            tools=request.tools,
        )

        # 创建 Agent Runtime
        agent = AgentRuntime(
            config=agent_config,
            llm_router=app_state.llm_router,
            tool_registry=app_state.tool_registry,
            hook_manager=app_state.hook_manager,
        )

        try:
            # 执行 Agent
            result = await agent.run(query)

            # 构建响应
            return ChatCompletionResponse(
                id=f"chatcmpl-{id(result)}",
                model=request.model,
                content=result.answer,
                tool_calls=[
                    {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                    for thought in result.thoughts
                    for tc in thought.tool_calls
                ],
                usage={
                    "prompt_tokens": result.tokens_used.prompt_tokens,
                    "completion_tokens": result.tokens_used.completion_tokens,
                    "total_tokens": result.tokens_used.total_tokens,
                },
                iterations=result.iterations,
                execution_time=result.execution_time,
            )

        except Exception as e:
            logger.error("chat_completion_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

    @app.get("/v1/tools")
    async def list_tools():
        """列出可用工具"""
        if not app_state.tool_registry:
            raise HTTPException(status_code=503, detail="Service not ready")

        tools = app_state.tool_registry.list_tools()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "parameters": t.parameters,
                }
                for t in tools
            ]
        }

    @app.post("/v1/tools/{tool_name}")
    async def execute_tool(tool_name: str, params: Dict[str, Any]):
        """直接执行工具"""
        if not app_state.tool_registry:
            raise HTTPException(status_code=503, detail="Service not ready")

        if not app_state.tool_registry.has_tool(tool_name):
            raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

        try:
            result = await app_state.tool_registry.execute(tool_name, **params)
            return {"result": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")

    return app