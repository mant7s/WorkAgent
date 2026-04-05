"""WorkAgent Agent Runtime"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from config import get_config
from .types import (
    Action,
    AgentConfig,
    AgentResult,
    AgentStatus,
    BudgetExceededError,
    Message,
    Observation,
    Thought,
    TokenUsage,
    ToolCall,
)
from .hooks import HookManager
from tools.registry import ToolRegistry
from llm.router import LLMRouter

logger = structlog.get_logger()


class AgentRuntime:
    """
    Agent 运行时 - 核心执行引擎

    职责：
    1. 管理 ReAct 循环（Reason → Act → Observe）
    2. 协调工具调用
    3. 管理上下文窗口
    4. 执行预算控制
    5. 触发 Hooks 事件
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        llm_router: Optional[LLMRouter] = None,
        tool_registry: Optional[ToolRegistry] = None,
        hook_manager: Optional[HookManager] = None,
    ):
        # 从配置文件加载默认配置
        app_config = get_config()
        
        # 使用传入的配置或从配置文件创建
        if config is None:
            config = AgentConfig(
                model=app_config.agent.default_model,
                temperature=app_config.agent.default_temperature,
                max_iterations=app_config.agent.default_max_iterations,
                token_budget=app_config.agent.default_token_budget,
                timeout=app_config.agent.default_timeout,
            )
        
        self.config = config
        self.llm = llm_router or LLMRouter().create_default()
        self.tools = tool_registry or ToolRegistry()
        self.hooks = hook_manager or HookManager()
        self.status = AgentStatus.IDLE
        self.iteration = 0
        self.tokens_used = TokenUsage()
        self.thoughts: List[Thought] = []
        self.observations: List[Observation] = []
        self._logger = structlog.get_logger()

    async def run(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        """
        执行 Agent 任务

        Args:
            query: 用户查询
            context: 额外上下文

        Returns:
            AgentResult 执行结果
        """
        start_time = time.time()
        self.status = AgentStatus.RUNNING
        self.iteration = 0
        self.tokens_used = TokenUsage()
        self.thoughts = []
        self.observations = []

        self._logger.info(
            "agent_started",
            query=query[:100],
            max_iterations=self.config.max_iterations,
            token_budget=self.config.token_budget,
        )

        # 触发开始 Hook
        await self.hooks.trigger(
            "agent:started",
            {
                "query": query,
                "config": self.config,
            },
            source="AgentRuntime",
        )

        try:
            result = await self._react_loop(query, context or {})
            self.status = AgentStatus.COMPLETED

            result.execution_time = time.time() - start_time

            self._logger.info(
                "agent_completed",
                iterations=result.iterations,
                tokens_used=result.tokens_used.total_tokens,
                execution_time=result.execution_time,
            )

            # 触发完成 Hook
            await self.hooks.trigger(
                "agent:completed",
                {
                    "result": result,
                    "tokens_used": self.tokens_used,
                },
                source="AgentRuntime",
            )

            return result

        except BudgetExceededError as e:
            self.status = AgentStatus.FAILED
            self._logger.error("agent_budget_exceeded", error=str(e))

            result = AgentResult(
                answer=f"Token budget exceeded: {self.tokens_used.total_tokens}/{self.config.token_budget}",
                thoughts=self.thoughts,
                observations=self.observations,
                tokens_used=self.tokens_used,
                iterations=self.iteration,
                error=str(e),
            )

            await self.hooks.trigger(
                "agent:failed",
                {"error": str(e), "reason": "budget_exceeded"},
                source="AgentRuntime",
            )
            return result

        except Exception as e:
            self.status = AgentStatus.FAILED
            self._logger.error("agent_failed", error=str(e))

            await self.hooks.trigger(
                "agent:failed",
                {"error": str(e)},
                source="AgentRuntime",
            )

            # 返回部分结果
            return AgentResult(
                answer=f"Error: {str(e)}",
                thoughts=self.thoughts,
                observations=self.observations,
                tokens_used=self.tokens_used,
                iterations=self.iteration,
                error=str(e),
            )

    async def _react_loop(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> AgentResult:
        """
        ReAct 循环实现

        Reason → Act → Observe 循环
        """
        system_prompt = self._build_system_prompt()

        while self.iteration < self.config.max_iterations:
            # 检查预算
            if self.tokens_used.total_tokens >= self.config.token_budget:
                raise BudgetExceededError(
                    f"Token budget exceeded: {self.tokens_used.total_tokens}"
                )

            self._logger.info(
                "react_iteration",
                iteration=self.iteration + 1,
                max_iterations=self.config.max_iterations,
            )

            # Step 1: Reason - 思考下一步
            thought = await self._reason(query, system_prompt, context)
            self.thoughts.append(thought)

            self._logger.info(
                "reason_completed",
                thought=thought.content[:100] if thought.content else "(no content)",
                has_tool_calls=len(thought.tool_calls) > 0,
            )

            # 检查是否完成（没有工具调用表示可以给出最终答案）
            if not thought.tool_calls:
                self._logger.info("agent_thinking_complete")
                return AgentResult(
                    answer=thought.content or "No answer provided",
                    thoughts=self.thoughts,
                    observations=self.observations,
                    tokens_used=self.tokens_used,
                    iterations=self.iteration + 1,
                )

            # Step 2: Act - 执行动作
            for tool_call in thought.tool_calls:
                action = await self._act(tool_call)

                # Step 3: Observe - 观察结果
                observation = await self._observe(action)
                self.observations.append(observation)

                self._logger.info(
                    "act_observe_completed",
                    tool=action.tool,
                    observation_type=observation.type,
                )

            self.iteration += 1

            # 触发迭代 Hook
            await self.hooks.trigger(
                "agent:iteration",
                {
                    "iteration": self.iteration,
                    "thought": thought,
                    "observations": self.observations[-len(thought.tool_calls):] if thought.tool_calls else [],
                },
                source="AgentRuntime",
            )

        # 达到最大迭代次数
        self._logger.warning("max_iterations_reached")

        return AgentResult(
            answer="Maximum iterations reached without completion",
            thoughts=self.thoughts,
            observations=self.observations,
            tokens_used=self.tokens_used,
            iterations=self.iteration,
            incomplete=True,
        )

    async def _reason(
        self,
        query: str,
        system_prompt: str,
        context: Dict[str, Any],
    ) -> Thought:
        """
        推理阶段

        调用 LLM 进行思考
        """
        messages = self._build_messages(query, system_prompt, context)

        # 获取工具 schemas
        tools = self.tools.get_schemas()

        response = await self.llm.chat(
            messages=[m.to_dict() for m in messages],
            model=self.config.model,
            temperature=self.config.temperature,
            tools=tools if tools else None,
        )

        # 更新 token 统计
        self.tokens_used += response.usage

        # 解析工具调用
        tool_calls = []
        for tc in response.tool_calls:
            try:
                args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
            except json.JSONDecodeError:
                args = {}

            tool_calls.append(
                ToolCall(
                    name=tc["name"],
                    arguments=args,
                    id=tc.get("id"),
                )
            )

        return Thought(
            content=response.content,
            tool_calls=tool_calls,
            raw_response=response.raw_response,
        )

    async def _act(self, tool_call: ToolCall) -> Action:
        """
        执行动作

        将工具调用转换为 Action
        """
        return Action(
            type="tool_call",
            tool=tool_call.name,
            params=tool_call.arguments,
        )

    async def _observe(self, action: Action) -> Observation:
        """
        观察执行结果

        执行工具并返回观察结果
        """
        if action.type != "tool_call" or not action.tool:
            return Observation(
                type="error",
                data="Invalid action",
                error="Invalid action type",
            )

        # 检查工具是否存在
        if not self.tools.has_tool(action.tool):
            return Observation(
                type="error",
                data=f"Tool not found: {action.tool}",
                tool=action.tool,
                error=f"Tool not found: {action.tool}",
            )

        # 检查工具策略
        if not self._check_tool_policy(action.tool, action.params or {}):
            return Observation(
                type="error",
                data="Tool execution denied by policy",
                tool=action.tool,
                error="Policy denied",
            )

        # 执行工具
        try:
            result = await self.tools.execute(action.tool, **(action.params or {}))
            return Observation(
                type="tool_result",
                data=result,
                tool=action.tool,
            )
        except Exception as e:
            return Observation(
                type="error",
                data=str(e),
                tool=action.tool,
                error=str(e),
            )

    def _check_tool_policy(self, tool: str, params: Dict) -> bool:
        """
        工具策略检查

        轻量级安全策略
        """
        # 检查工具是否在白名单
        if self.config.tools and tool not in self.config.tools:
            self._logger.warning("tool_not_in_whitelist", tool=tool)
            return False

        # 检查危险参数模式
        dangerous_patterns = ["rm -rf", "drop table", "delete from", "shutdown", "reboot"]
        param_str = str(params).lower()

        for pattern in dangerous_patterns:
            if pattern in param_str:
                self._logger.warning("dangerous_pattern_detected", pattern=pattern)
                return False

        return True

    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        return f"""You are an AI assistant with access to tools.

Current date: {datetime.now().isoformat()}
Token budget: {self.config.token_budget} (used: {self.tokens_used.total_tokens})
Iteration: {self.iteration + 1}/{self.config.max_iterations}

Follow the ReAct pattern:
1. Think about what you need to do to answer the question
2. Use tools to gather information or perform calculations
3. Observe the results
4. Continue until you can provide a complete answer

When you have enough information, provide a final answer without using tools.

Available tools:
{self.tools.describe_tools()}
"""

    def _build_messages(
        self,
        query: str,
        system_prompt: str,
        context: Dict[str, Any],
    ) -> List[Message]:
        """构建消息列表"""
        messages: List[Message] = []

        # 系统消息
        messages.append(Message(role="system", content=system_prompt))

        # 添加上下文中的历史消息（如果有）
        if "history" in context:
            for msg in context["history"]:
                messages.append(Message(
                    role=msg.get("role", "user"),
                    content=msg.get("content"),
                ))

        # 用户查询
        messages.append(Message(role="user", content=query))

        # 添加 ReAct 循环中的历史
        for thought, obs in zip(self.thoughts, self.observations):
            # 助手的思考
            if thought.content:
                messages.append(Message(role="assistant", content=thought.content))

            # 如果有工具调用，添加工具调用和结果
            if thought.tool_calls:
                tool_calls_data = []
                for tc in thought.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id or f"call_{len(tool_calls_data)}",
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    })

                messages.append(Message(
                    role="assistant",
                    content=None,
                    tool_calls=tool_calls_data,
                ))

                # 工具结果
                if obs.tool:
                    messages.append(Message(
                        role="tool",
                        content=str(obs.data),
                        tool_call_id=tc.id or f"call_{len(tool_calls_data) - 1}",
                    ))

        return messages
