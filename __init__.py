"""WorkAgent - 轻量级 AI Agent 开发框架"""

__version__ = "0.1.0"

from core.agent import AgentRuntime
from core.hooks import HookManager
from core.types import AgentConfig
from llm.router import LLMRouter
from tools.registry import ToolRegistry

__all__ = [
    "AgentRuntime",
    "HookManager",
    "AgentConfig",
    "LLMRouter",
    "ToolRegistry",
]
