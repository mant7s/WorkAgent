# WorkAgent - 轻量级 AI Agent 框架

一个轻量级、可扩展的 AI Agent 开发框架，支持 ReAct 循环、工具调用、上下文管理、技能系统和生产级特性。

## 特性

- **ReAct 循环**: 支持 Reason → Act → Observe 循环
- **工具系统**: 装饰器方式注册工具，支持参数自动提取和 OpenAI Function Calling Schema 生成
- **LLM 路由**: 多模型提供商管理，统一接口
- **事件钩子**: 支持同步/异步事件处理
- **Token 预算**: 基础 Token 使用控制
- **上下文管理**: 上下文窗口压缩（三段式保留策略）、分层记忆检索
- **技能系统**: 角色预设（Presets）和技能注册（Skills）
- **FastAPI 服务**: 提供 RESTful API 接口
- **结构化日志**: 使用 structlog 输出结构化日志

### 生产级特性 (v2)

- **三级预算控制** ([`BudgetManager`](budget/manager.py#L72)): Task/Session/Agent 三级预算 + 背压控制 + 熔断器
- **DAG 工作流引擎** ([`WorkflowEngine`](workflow/engine.py#L102)): 支持并行/串行/DAG 执行，信号控制（暂停/恢复/取消）
- **Prompt 安全防护** ([`PromptGuard`](security/guard.py#L77)): 注入攻击检测、PII 脱敏、危险模式识别
- **多租户隔离** ([`TenantManager`](security/tenant.py#L116)): 行级隔离、资源配额、ContextVar 实现
- **OpenTelemetry 追踪** ([`TracingManager`](observability/tracing.py#L112)): 链路追踪、装饰器方式、可选依赖

## 项目结构

```
WorkAgent/
├── api/                    # API 模块（对外暴露接口）
│   ├── __init__.py        # 导出 create_app
│   └── routes.py          # FastAPI 路由定义
├── config/                 # 配置管理
│   ├── __init__.py
│   ├── loader.py          # 配置加载器
│   └── config.yaml        # 默认配置文件
├── core/                   # 核心模块
│   ├── types.py           # 数据类型定义
│   ├── hooks.py           # 事件钩子系统
│   ├── agent.py           # AgentRuntime 实现
│   └── context.py         # 上下文管理和记忆系统
├── budget/                 # 预算控制模块
│   ├── __init__.py
│   └── manager.py         # BudgetManager 实现
├── workflow/               # 工作流引擎
│   ├── __init__.py
│   └── engine.py          # WorkflowEngine 实现
├── security/               # 安全模块
│   ├── __init__.py
│   ├── guard.py           # PromptGuard 实现
│   └── tenant.py          # 多租户管理
├── observability/          # 可观测性模块
│   ├── __init__.py
│   └── tracing.py         # OpenTelemetry 集成
├── tools/                  # 工具系统
│   ├── registry.py        # 工具注册表
│   └── builtin.py         # 内置工具
├── skills/                 # 技能系统
│   ├── presets.py         # 角色预设
│   └── registry.py        # 技能注册表
├── llm/                    # LLM 模块
│   ├── router.py          # LLM 路由
│   └── providers/         # 提供商实现
│       └── openai.py      # OpenAI Provider
├── examples/               # 示例
│   ├── simple_agent.py    # 基础示例
│   ├── skills_and_context_demo.py  # Skills & Context 演示
│   ├── core_modules_demo.py        # 核心模块演示
│   └── config_demo.py              # 配置系统演示
├── server.py              # 服务端启动入口（根目录）
├── pyproject.toml         # 项目配置
├── requirements.txt       # 依赖清单
└── README.md              # 项目说明
```

## 快速开始

### 安装依赖

```bash
pip install -e .
```

或安装核心依赖：

```bash
pip install fastapi uvicorn pydantic openai httpx structlog pyyaml python-dotenv
```

### 设置环境变量

方式1：使用环境变量

```bash
export OPENAI_API_KEY=your-api-key
```

方式2：使用 .env 文件（推荐）

```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
```

环境变量优先级（从高到低）：
1. 系统环境变量
2. `.env.local` 文件
3. `.env` 文件
4. 配置文件中的值

### 运行示例
```bash
# 基础示例
python examples/simple_agent.py

# Skills & Context 演示
python examples/skills_and_context_demo.py

# 核心模块演示（BudgetManager、WorkflowEngine、Security、Observability）
python examples/core_modules_demo.py

# 配置系统演示
python examples/config_demo.py
```

### 启动 API 服务

```bash
# 使用配置文件中的设置启动
python server.py

# 覆盖端口
python server.py --port 9000

# 开发模式（自动重载）
python server.py --reload
```

或使用 uvicorn：

```bash
uvicorn api:create_app --factory --reload
```

## 使用示例

### 配置文件

框架支持通过 YAML 配置文件管理所有配置。默认配置文件位于 `config/config.yaml`：

```yaml
# 服务器配置
server:
  host: "0.0.0.0"
  port: 8000
  log_level: "INFO"

# Agent 默认配置
agent:
  default_model: "gpt-4o-mini"
  default_temperature: 0.7
  default_max_iterations: 10
  default_token_budget: 10000

# 模型配置
models:
  openai:
    provider: "openai"
    model: "gpt-4o-mini"
    api_key: null  # 从环境变量 OPENAI_API_KEY 读取
    temperature: 0.7
    default: true  # 设置为默认模型

# 预算控制配置
budget:
  enabled: true
  task_budget: 10000
  session_budget: 50000
  agent_budget: 5000
  warning_threshold: 0.8
  backpressure_enabled: true

# 安全配置
security:
  prompt_guard_enabled: true
  max_prompt_length: 10000
  pii_redaction_enabled: true
  multi_tenant_enabled: false

# 可观测性配置
observability:
  tracing_enabled: false
  service_name: "workagent"
  otlp_endpoint: null
```

### 环境变量

可以通过环境变量覆盖配置：

```bash
# 指定配置文件路径
export WORKAGENT_CONFIG=/path/to/config.yaml

# 服务器配置
export WORKAGENT_HOST=0.0.0.0
export WORKAGENT_PORT=8000
export WORKAGENT_LOG_LEVEL=INFO

# Agent 配置
export WORKAGENT_DEFAULT_MODEL=gpt-4o-mini
export WORKAGENT_DEFAULT_TEMPERATURE=0.7

# API Key
export OPENAI_API_KEY=your-api-key

# 可观测性
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### 基础用法

```python
import asyncio
from core.agent import AgentRuntime
from core.hooks import HookManager
from core.types import AgentConfig
from llm.router import LLMRouter
from tools.builtin import get_builtin_registry

async def main():
    # 方式1：不传配置，自动从配置文件加载
    agent = AgentRuntime()
    
    # 方式2：传入自定义配置（覆盖配置文件）
    config = AgentConfig(
        model="gpt-4o-mini",
        temperature=0.7,
        max_iterations=10,
        token_budget=5000,
    )
    agent = AgentRuntime(config=config)
    
    # 运行查询
    result = await agent.run("What is 15 * 23?")
    print(result.answer)

asyncio.run(main())
```

### 注册自定义工具

```python
from tools.registry import ToolRegistry

registry = ToolRegistry()

@registry.register(
    name="my_tool",
    description="我的自定义工具",
    category="custom"
)
def my_tool(param1: str, param2: int = 10) -> str:
    """工具函数文档"""
    return f"Result: {param1} - {param2}"

# 执行工具
result = await registry.execute("my_tool", param1="hello", param2=20)
```

### 使用事件钩子

```python
from core.hooks import HookManager

hooks = HookManager()

@hooks.on("agent:started")
async def on_started(event):
    print(f"Agent started: {event.data}")

@hooks.on("agent:completed")
async def on_completed(event):
    print(f"Agent completed: {event.data}")

# 触发事件
await hooks.trigger("custom:event", {"key": "value"})
```

### 使用角色预设 (Presets)

```python
from skills import get_preset, list_presets

# 列出所有可用预设
for preset in list_presets():
    print(f"{preset['name']}: {preset['description']}")

# 加载特定预设
preset = get_preset("research")
print(preset.system_prompt)
print(preset.allowed_tools)
```

### 使用上下文管理

```python
from core import ContextManager, InMemoryStore

# 创建上下文管理器
memory_store = InMemoryStore()
context_manager = ContextManager(memory_store=memory_store)

# 保存记忆
await memory_store.save(
    session_id="session_001",
    content="用户偏好信息",
    metadata={"source": "conversation"}
)

# 构建包含相关记忆的上下文
messages = await context_manager.build_context(
    query="用户的问题",
    session_id="session_001",
    system_prompt="You are a helpful assistant."
)
```

### 使用 Skills 系统

```python
from skills import SkillRegistry, Skill

# 创建注册表
registry = SkillRegistry()

# 注册技能
registry.register(Skill(
    name="code-review",
    description="审查代码",
    system_prompt="You are a code reviewer...",
    allowed_tools=["file_read"],
    requires_role="code_reviewer",
    budget_max=5000,
))

# 应用技能到 Agent 配置
config = registry.apply_skill_to_agent(agent_config, "code-review")
```

### 使用 BudgetManager

```python
from budget import BudgetManager, BudgetConfig, BudgetMode

# 创建预算管理器
config = BudgetConfig(
    task_budget=5000,      # 任务级预算
    session_budget=20000,  # 会话级预算
    agent_budget=3000,     # Agent 级预算
    mode=BudgetMode.SOFT_LIMIT,
    backpressure_enabled=True,
)

budget_manager = BudgetManager(config)

# 检查预算
result = await budget_manager.check_budget(
    task_id="task_001",
    session_id="session_001",
    agent_id="agent_001",
    estimated_tokens=1000,
)

if result.can_proceed:
    # 执行操作
    await budget_manager.record_usage(
        task_id="task_001",
        session_id="session_001",
        agent_id="agent_001",
        tokens_used=800,
        idempotency_key="unique_key_001",
    )
    
    # 应用背压
    if result.backpressure_delay > 0:
        await budget_manager.apply_backpressure("session_001")
```

### 使用 WorkflowEngine

```python
from workflow import WorkflowEngine, Task, Workflow

engine = WorkflowEngine(max_workers=5)

# 定义任务
async def fetch_data(query: str) -> dict:
    return {"results": ["data1", "data2"]}

async def process_data(dependencies: dict = None) -> dict:
    fetch_result = dependencies.get("fetch", {})
    return {"processed": fetch_result.get("results", [])}

# 创建 DAG 工作流
tasks = [
    Task(id="fetch", name="fetch_data", func=fetch_data, args=("query",)),
    Task(id="process", name="process_data", func=process_data, dependencies=["fetch"]),
]

# 执行
results = await engine.execute(tasks, mode="dag")

# 信号控制
await engine.pause("workflow_001")
await engine.resume("workflow_001")
```

### 使用 PromptGuard

```python
from security import PromptGuard

# 创建 Guard
guard = PromptGuard({
    "max_prompt_length": 1000,
    "blocked_keywords": ["delete all", "drop table"],
    "enable_pii_detection": True,
})

# 检查 Prompt
result = guard.check("What is the weather today?")
if not result.allowed:
    print(f"Blocked: {result.reason}")

# 脱敏处理
sanitized = guard.sanitize("Contact me at user@example.com")
print(sanitized)  # "Contact me at [EMAIL_REDACTED]"
```

### 使用 TenantManager

```python
from security import TenantManager, TenantConfig, TenantQuota, TenantContext

manager = TenantManager()

# 注册租户
manager.register_tenant(TenantConfig(
    tenant_id="tenant_001",
    name="Acme Corp",
    quota=TenantQuota(
        max_tokens_per_day=50000,
        max_concurrent_tasks=5,
        allowed_models=["gpt-4o-mini"],
    ),
))

# 检查配额
result = await manager.check_quota(
    tenant_id="tenant_001",
    tokens=1000,
    model="gpt-4o-mini",
)

# 在租户上下文中执行
async with TenantContext("tenant_001"):
    # 自动记录租户 ID
    current_tenant = manager.get_current_tenant_id()
    await manager.record_usage("tenant_001", tokens=1000)
```

### 使用 OpenTelemetry 追踪

```python
from observability import (
    initialize_tracing,
    trace_span,
    get_tracer,
)

# 初始化
tracing_manager = initialize_tracing(
    service_name="my-agent",
    exporter_endpoint="http://localhost:4317",
    console_export=True,
)

# 使用装饰器
@trace_span("agent.run", component="agent")
async def run_agent(query: str) -> str:
    return await process(query)

# 手动创建 span
tracer = get_tracer()
with tracer.start_as_current_span("operation") as span:
    span.set_attribute("key", "value")
    result = do_something()
```

## API 端点

### 健康检查

```bash
GET /health
```

### 聊天完成

```bash
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "What is 15 * 23?"}
  ],
  "temperature": 0.7,
  "max_iterations": 10
}
```

### 列出工具

```bash
GET /v1/tools
```

### 执行工具

```bash
POST /v1/tools/calculator
Content-Type: application/json

{
  "expression": "15 * 23"
}
```

## 内置工具

- `calculator`: 数学计算工具
- `web_search`: 网页搜索（模拟）
- `get_current_weather`: 获取天气（模拟）
- `get_current_time`: 获取当前时间

## 配置选项

### 配置文件结构

| 配置节 | 说明 |
|--------|------|
| server | 服务器配置（host, port, log_level） |
| agent | Agent 默认配置（model, temperature, max_iterations, token_budget） |
| models | 模型配置（支持多模型） |
| budget | 预算控制配置 |
| security | 安全配置 |
| observability | 可观测性配置 |
| tools | 工具配置 |
| skills | Skills 配置 |

### AgentConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_iterations | int | 10 | 最大迭代次数 |
| token_budget | int | 10000 | Token 预算 |
| temperature | float | 0.7 | 温度参数 |
| model | str | "gpt-4o-mini" | 模型名称 |
| timeout | float | 300.0 | 超时时间 |

### BudgetConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| task_budget | int | 10000 | 任务级 Token 预算 |
| session_budget | int | 50000 | 会话级 Token 预算 |
| agent_budget | int | 5000 | Agent 级 Token 预算 |
| mode | BudgetMode | SOFT_LIMIT | 预算模式（HARD_LIMIT/SOFT_LIMIT/REQUIRE_APPROVAL） |
| warning_threshold | float | 0.8 | 警告阈值 |
| backpressure_enabled | bool | True | 是否启用背压控制 |

### 背压延迟规则

| 使用率 | 延迟 |
|--------|------|
| < 80% | 0ms |
| 80% - 85% | 50ms |
| 85% - 90% | 300ms |
| 90% - 95% | 750ms |
| > 95% | 1500ms |

### WorkflowEngine 模式

| 模式 | 说明 |
|------|------|
| sequential | 串行执行 |
| parallel | 并行执行 |
| dag | DAG 拓扑排序执行 |

## 开发

### 代码格式化

```bash
black .
ruff check .
```

### 类型检查

```bash
mypy .
```

## 许可证

MIT License
