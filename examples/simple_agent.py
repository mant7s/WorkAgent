#!/usr/bin/env python3
"""
WorkAgent 最小可行示例

功能：
- ReAct 循环展示
- 工具调用（calculator, web_search）
- 结构化日志输出
- Token 预算控制

运行方式：
    export OPENAI_API_KEY=your-api-key
    python examples/simple_agent.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件（从项目根目录加载）
try:
    from dotenv import load_dotenv
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()  # 尝试从当前目录加载
except ImportError:
    pass  # python-dotenv 未安装，跳过

import structlog
import structlog

from core.agent import AgentRuntime
from core.hooks import HookManager
from core.types import AgentConfig
from llm.router import LLMRouter
from tools.builtin import get_builtin_registry
from tools.registry import ToolRegistry

# 配置结构化日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def setup_agent() -> AgentRuntime:
    """初始化 Agent"""
    logger.info("🔧 Setting up agent...")

    # 1. 初始化 LLM Router
    llm_router = LLMRouter().create_default()

    if not llm_router.list_providers():
        logger.warning("⚠️  No LLM provider available. Demo will show framework structure only.")
        # 创建一个空的 router 用于演示
        llm_router = LLMRouter()
    else:
        logger.info(f"✅ LLM providers: {llm_router.list_providers()}")

    # 2. 初始化工具注册表（使用内置工具）
    tool_registry = get_builtin_registry()
    tools = tool_registry.list_tools()
    logger.info(f"✅ Loaded {len(tools)} tools: {[t.name for t in tools]}")

    # 3. 初始化 Hook Manager
    hook_manager = HookManager()

    @hook_manager.on("agent:started")
    async def on_started(event):
        logger.info(f"🚀 Hook: Agent started - {event.data['query'][:50]}...")

    @hook_manager.on("agent:iteration")
    async def on_iteration(event):
        logger.info(f"🔄 Hook: Iteration {event.data['iteration']} completed")

    @hook_manager.on("agent:completed")
    async def on_completed(event):
        result = event.data.get("result", {})
        logger.info(f"✅ Hook: Agent completed - {result.get('iterations', 0)} iterations")

    # 4. 创建 Agent 配置
    config = AgentConfig(
        model="gpt-4o-mini",
        temperature=0.7,
        max_iterations=10,
        token_budget=5000,
    )

    # 5. 创建 Agent Runtime
    agent = AgentRuntime(
        config=config,
        llm_router=llm_router,
        tool_registry=tool_registry,
        hook_manager=hook_manager,
    )

    logger.info("✅ Agent setup complete!")
    return agent


async def run_example(agent: AgentRuntime, query: str, description: str, demo_mode: bool = False):
    """运行单个示例"""
    print("\n" + "=" * 70)
    print(f"📋 {description}")
    print("=" * 70)
    print(f"📝 Query: {query}")
    print("-" * 70)

    if demo_mode:
        print("\n⚠️  DEMO MODE: No LLM provider available")
        print("   Showing framework structure without LLM calls...")
        print("\n   To run with LLM, set OPENAI_API_KEY environment variable")
        return

    try:
        result = await agent.run(query)

        print(f"\n✨ Final Answer:")
        print(f"   {result.answer}")
        print(f"\n📊 Statistics:")
        print(f"   • Iterations: {result.iterations}")
        print(f"   • Tokens used: {result.tokens_used.total_tokens}")
        print(f"   • Execution time: {result.execution_time:.2f}s")

        if result.incomplete:
            print(f"   ⚠️  Status: Incomplete (max iterations reached)")

        # 显示 ReAct 循环详情
        if result.thoughts:
            print(f"\n🔄 ReAct Loop Details:")
            for i, (thought, obs) in enumerate(zip(result.thoughts, result.observations), 1):
                print(f"\n   Step {i}:")
                if thought.content:
                    print(f"   💭 Thought: {thought.content[:100]}...")
                if thought.tool_calls:
                    for tc in thought.tool_calls:
                        print(f"   🔧 Tool Call: {tc.name}({tc.arguments})")
                if obs:
                    print(f"   👁️  Observation: {str(obs.data)[:80]}...")

    except Exception as e:
        logger.error(f"❌ Example failed: {e}")
        print(f"\n❌ Error: {e}")


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("🤖 WorkAgent - 轻量级 AI Agent 框架示例")
    print("=" * 70)

    # 检查 API Key
    demo_mode = not os.getenv("OPENAI_API_KEY")
    if demo_mode:
        print("\n⚠️  Warning: OPENAI_API_KEY not set")
        print("   Set it with: export OPENAI_API_KEY=your-api-key")
        print("   Or create a .env file with your API key")
        print("\n   Continuing with demo mode (showing framework structure)...\n")

    try:
        agent = await setup_agent()
    except RuntimeError as e:
        print(f"\n❌ Setup failed: {e}")
        return

    # 示例 1: 需要计算的查询
    await run_example(
        agent,
        query="Calculate 15 * 23 + 47 and tell me the result.",
        description="示例 1: 数学计算（使用 calculator 工具）",
        demo_mode=demo_mode,
    )

    # 示例 2: 需要搜索的查询
    await run_example(
        agent,
        query="What is the capital of France? Please search for this information.",
        description="示例 2: 信息查询（使用 web_search 工具）",
        demo_mode=demo_mode,
    )

    # 示例 3: 组合查询
    await run_example(
        agent,
        query="What is the capital of France and what is 15 * 23?",
        description="示例 3: 组合查询（同时使用搜索和计算）",
        demo_mode=demo_mode,
    )

    print("\n" + "=" * 70)
    if demo_mode:
        print("✅ Demo completed! (Set OPENAI_API_KEY to run with LLM)")
    else:
        print("✅ All examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
