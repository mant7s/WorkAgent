"""WorkAgent 核心模块"""

from .types import (
    AgentStatus,
    AgentConfig,
    ToolCall,
    Thought,
    Observation,
    Action,
    AgentResult,
    Message,
    TokenUsage,
)
from .hooks import HookManager, HookEvent
from .agent import AgentRuntime
from .context import (
    ContextWindow,
    ContextConfig,
    ContextManager,
    MemoryItem,
    MemoryStore,
    InMemoryStore,
    HierarchicalMemory,
)

# 导入新模块
from budget import (
    BudgetMode,
    BudgetConfig,
    BudgetCheckResult,
    BudgetManager,
    CircuitBreaker,
    BudgetExceededError,
)
from workflow import (
    TaskStatus,
    WorkflowStatus,
    Task,
    Workflow,
    WorkflowEngine,
    WorkflowError,
    WorkflowSignal,
)
from security import (
    GuardResult,
    PromptGuard,
    PromptInjectionError,
    PIIPattern,
    TenantManager,
    TenantContext,
    get_current_tenant,
    set_current_tenant,
)
from observability import (
    TracingConfig,
    TracingManager,
    trace_span,
    get_tracer,
    start_span,
    get_current_span,
    set_span_attribute,
    record_exception,
)

__all__ = [
    # 核心类型
    "AgentStatus",
    "AgentConfig",
    "ToolCall",
    "Thought",
    "Observation",
    "Action",
    "AgentResult",
    "Message",
    "TokenUsage",
    # 核心组件
    "HookManager",
    "HookEvent",
    "AgentRuntime",
    "ContextWindow",
    "ContextConfig",
    "ContextManager",
    "MemoryItem",
    "MemoryStore",
    "InMemoryStore",
    "HierarchicalMemory",
    # 预算管理
    "BudgetMode",
    "BudgetConfig",
    "BudgetCheckResult",
    "BudgetManager",
    "CircuitBreaker",
    "BudgetExceededError",
    # 工作流引擎
    "TaskStatus",
    "WorkflowStatus",
    "Task",
    "Workflow",
    "WorkflowEngine",
    "WorkflowError",
    "WorkflowSignal",
    # 安全模块
    "GuardResult",
    "PromptGuard",
    "PromptInjectionError",
    "PIIPattern",
    "TenantManager",
    "TenantContext",
    "get_current_tenant",
    "set_current_tenant",
    # 可观测性
    "TracingConfig",
    "TracingManager",
    "trace_span",
    "get_tracer",
    "start_span",
    "get_current_span",
    "set_span_attribute",
    "record_exception",
]
