"""WorkAgent 核心数据类型定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentStatus(Enum):
    """Agent 执行状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TokenUsage:
    """Token 使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class AgentConfig:
    """Agent 配置"""
    max_iterations: int = 10
    min_iterations: int = 1
    token_budget: int = 10000
    temperature: float = 0.7
    model: str = "gpt-4o-mini"
    timeout: float = 300.0
    skills: Optional[List[str]] = None
    tools: Optional[List[str]] = None

    def __post_init__(self):
        if self.skills is None:
            self.skills = []
        if self.tools is None:
            self.tools = []


@dataclass
class ToolCall:
    """工具调用定义"""
    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class Thought:
    """推理结果"""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class Observation:
    """观察结果"""
    type: str  # "tool_result", "response", "error"
    data: Any
    tool: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


@dataclass
class Action:
    """执行动作"""
    type: str  # "tool_call", "respond"
    tool: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    content: Optional[str] = None


@dataclass
class AgentResult:
    """Agent 执行结果"""
    answer: str
    thoughts: List[Thought] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    tokens_used: TokenUsage = field(default_factory=TokenUsage)
    iterations: int = 0
    execution_time: float = 0.0
    incomplete: bool = False
    error: Optional[str] = None


@dataclass
class Message:
    """对话消息"""
    role: str  # "system", "user", "assistant", "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result: Dict[str, Any] = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        if self.tool_calls is not None:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            result["name"] = self.name
        return result


class BudgetExceededError(Exception):
    """Token 预算超出错误"""
    pass


class ToolExecutionError(Exception):
    """工具执行错误"""
    pass


class LLMError(Exception):
    """LLM 调用错误"""
    pass
