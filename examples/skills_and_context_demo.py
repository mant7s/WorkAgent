#!/usr/bin/env python3
"""
WorkAgent Skills 和 Context 演示

展示如何使用：
1. Skills 技能系统（角色预设）
2. Context 上下文管理（记忆、压缩）
3. 分层记忆检索

运行方式：
    python examples/skills_and_context_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structlog

from core import AgentRuntime, AgentConfig, ContextManager, InMemoryStore
from core.hooks import HookManager
from skills import get_preset, list_presets
from tools.builtin import get_builtin_registry
from llm.router import LLMRouter

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


async def demo_presets():
    """演示 Presets 角色预设"""
    print("\n" + "=" * 70)
    print("🎭 Demo 1: Presets 角色预设")
    print("=" * 70)

    # 列出所有可用预设
    print("\n📋 可用角色预设：")
    for preset_info in list_presets():
        print(f"  • {preset_info['name']}: {preset_info.get('description', 'No description')}")
        print(f"    工具: {preset_info['allowed_tools'] or 'None'}")
        print(f"    参数: temperature={preset_info['temperature']}, max_tokens={preset_info['max_tokens']}")
        print()

    # 加载特定预设
    print("\n🔍 加载 'research' 预设：")
    preset = get_preset("research")
    print(f"  名称: {preset.name}")
    print(f"  描述: {preset.description}")
    print(f"  允许工具: {preset.allowed_tools}")
    print(f"  系统提示预览:\n{preset.system_prompt[:300]}...")

    # 演示变量替换
    print("\n📝 渲染系统提示（带变量）：")
    preset_with_vars = get_preset("analysis")
    rendered = preset_with_vars.render_system_prompt({
        "target_language": "Chinese"
    })
    print(f"  {rendered[:200]}...")


async def demo_context_management():
    """演示上下文管理"""
    print("\n" + "=" * 70)
    print("📚 Demo 2: Context 上下文管理")
    print("=" * 70)

    # 创建上下文管理器
    memory_store = InMemoryStore()
    context_manager = ContextManager(memory_store=memory_store)

    session_id = "demo_session_001"

    # 模拟保存一些记忆
    print("\n💾 保存记忆到长期记忆：")
    await memory_store.save(
        session_id=session_id,
        content="用户喜欢 Python 编程，熟悉 FastAPI 和异步编程",
        metadata={"source": "user_profile"}
    )
    await memory_store.save(
        session_id=session_id,
        content="用户正在开发一个 AI Agent 框架",
        metadata={"source": "conversation"}
    )
    await memory_store.save(
        session_id=session_id,
        content="用户关心代码质量和架构设计",
        metadata={"source": "conversation"}
    )
    print("  ✓ 已保存 3 条记忆")

    # 构建上下文
    print("\n🔍 构建上下文（包含相关记忆）：")
    query = "How to design a good agent architecture?"
    system_prompt = "You are a helpful assistant."

    messages = await context_manager.build_context(
        query=query,
        session_id=session_id,
        system_prompt=system_prompt,
    )

    print(f"  构建的消息数: {len(messages)}")
    for i, msg in enumerate(messages):
        role = msg['role']
        content = msg.get('content', '')[:80]
        print(f"  [{i}] {role}: {content}...")

    # 演示上下文压缩
    print("\n📦 上下文压缩演示：")
    from core import ContextWindow, ContextConfig
    from core.context import Message as ContextMessage

    config = ContextConfig(max_tokens=100, warning_threshold=0.8)
    window = ContextWindow(config)

    # 添加大量消息
    for i in range(10):
        window.add_message(ContextMessage(
            role="user" if i % 2 == 0 else "assistant",
            content=f"This is message number {i} with some content to make it longer and exceed the token limit for demonstration purposes."
        ))

    print(f"  消息数: {len(window.messages)}")
    print(f"  估算 Token: {window.estimate_tokens()}")
    print(f"  是否有摘要: {window.summary is not None}")
    if window.summary:
        print(f"  摘要: {window.summary[:100]}...")


async def demo_skills_integration():
    """演示 Skills 集成"""
    print("\n" + "=" * 70)
    print("🛠️  Demo 3: Skills 集成")
    print("=" * 70)

    from skills import SkillRegistry, Skill

    # 创建注册表
    registry = SkillRegistry()

    # 注册一些技能
    print("\n📋 注册 Skills：")

    registry.register(Skill(
        name="code-review",
        description="审查代码，找出 bug 和安全问题",
        system_prompt="""You are a code reviewer. Focus on:
1. Security vulnerabilities
2. Logic errors
3. Performance issues""",
        allowed_tools=["file_read", "grep_search"],
        requires_role="code_reviewer",
        budget_max=5000,
    ))

    registry.register(Skill(
        name="research",
        description="研究技术话题，收集信息",
        system_prompt="""You are a research assistant. Gather facts and synthesize findings.""",
        allowed_tools=["web_search", "web_fetch"],
        requires_role="research",
        budget_max=10000,
    ))

    # 列出所有技能
    print("\n📚 已注册 Skills：")
    for skill_info in registry.list_skills():
        print(f"  • {skill_info['name']}: {skill_info['description']}")
        print(f"    工具: {skill_info['allowed_tools']}")
        print(f"    角色: {skill_info['requires_role']}")
        print(f"    预算: {skill_info.get('budget_max', 'unlimited')}")
        print()

    # 应用技能到 Agent 配置
    print("\n🔧 应用 Skill 到 Agent 配置：")
    agent_config = {
        "system_prompt": "You are a helpful assistant.",
        "tools": [],
        "token_budget": 20000,
    }

    print("  原始配置:")
    print(f"    system_prompt: {agent_config['system_prompt'][:50]}...")
    print(f"    tools: {agent_config['tools']}")
    print(f"    token_budget: {agent_config['token_budget']}")

    updated_config = registry.apply_skill_to_agent(agent_config, "code-review")

    print("\n  应用 'code-review' Skill 后:")
    print(f"    system_prompt: {updated_config['system_prompt'][:50]}...")
    print(f"    tools: {updated_config['tools']}")
    print(f"    token_budget: {updated_config['token_budget']}")


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("🤖 WorkAgent - Skills & Context 演示")
    print("=" * 70)

    try:
        await demo_presets()
        await demo_context_management()
        await demo_skills_integration()

        print("\n" + "=" * 70)
        print("✅ 所有演示完成！")
        print("=" * 70)

    except Exception as e:
        logger.error("demo_failed", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())
