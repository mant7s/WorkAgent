"""配置系统使用示例

展示如何使用配置文件管理 Agent 相关配置。
"""

import asyncio
import os

# 设置环境变量示例（可选）
# os.environ["WORKAGENT_CONFIG"] = "config/config.yaml"
# os.environ["OPENAI_API_KEY"] = "your-api-key"

from config import load_config, get_config, reload_config
from core.agent import AgentRuntime
from core.types import AgentConfig
from budget.manager import BudgetManager
from security.guard import PromptGuard
from observability.tracing import TracingManager


def demo_config_loading():
    """演示配置加载"""
    print("=" * 50)
    print("配置系统演示")
    print("=" * 50)
    
    # 方式1：从默认路径加载配置
    config = load_config()
    print(f"\n1. 配置加载成功")
    print(f"   服务器端口: {config.server.port}")
    print(f"   默认模型: {config.agent.default_model}")
    print(f"   默认温度: {config.agent.default_temperature}")
    
    # 方式2：获取已加载的配置（单例）
    same_config = get_config()
    print(f"\n2. 获取已加载配置（单例）")
    print(f"   是否是同一对象: {config is same_config}")
    
    # 显示预算配置
    print(f"\n3. 预算配置")
    print(f"   任务预算: {config.budget.task_budget}")
    print(f"   会话预算: {config.budget.session_budget}")
    print(f"   Agent预算: {config.budget.agent_budget}")
    print(f"   警告阈值: {config.budget.warning_threshold}")
    print(f"   背压启用: {config.budget.backpressure_enabled}")
    
    # 显示安全配置
    print(f"\n4. 安全配置")
    print(f"   Prompt Guard: {config.security.prompt_guard_enabled}")
    print(f"   最大Prompt长度: {config.security.max_prompt_length}")
    print(f"   PII脱敏: {config.security.pii_redaction_enabled}")
    print(f"   多租户: {config.security.multi_tenant_enabled}")
    
    # 显示可观测性配置
    print(f"\n5. 可观测性配置")
    print(f"   链路追踪: {config.observability.tracing_enabled}")
    print(f"   服务名称: {config.observability.service_name}")
    print(f"   OTLP端点: {config.observability.otlp_endpoint}")
    
    # 显示模型配置
    print(f"\n6. 模型配置")
    for name, model_config in config.models.items():
        print(f"   {name}: {model_config.model} ({model_config.provider})")
    
    return config


def demo_agent_with_config():
    """演示使用配置创建 Agent"""
    print("\n" + "=" * 50)
    print("使用配置创建 Agent")
    print("=" * 50)
    
    # 方式1：不传配置，自动从配置文件加载
    print("\n1. 创建 Agent（自动加载配置）")
    agent1 = AgentRuntime()
    print(f"   模型: {agent1.config.model}")
    print(f"   温度: {agent1.config.temperature}")
    print(f"   最大迭代: {agent1.config.max_iterations}")
    print(f"   Token预算: {agent1.config.token_budget}")
    
    # 方式2：传入自定义配置（覆盖配置文件）
    print("\n2. 创建 Agent（自定义配置覆盖）")
    custom_config = AgentConfig(
        model="gpt-4o",
        temperature=0.5,
        max_iterations=5,
        token_budget=5000,
    )
    agent2 = AgentRuntime(config=custom_config)
    print(f"   模型: {agent2.config.model}")
    print(f"   温度: {agent2.config.temperature}")
    print(f"   最大迭代: {agent2.config.max_iterations}")
    print(f"   Token预算: {agent2.config.token_budget}")


def demo_budget_with_config():
    """演示使用配置创建 BudgetManager"""
    print("\n" + "=" * 50)
    print("使用配置创建 BudgetManager")
    print("=" * 50)
    
    # 方式1：不传配置，自动从配置文件加载
    print("\n1. 创建 BudgetManager（自动加载配置）")
    budget1 = BudgetManager()
    print(f"   任务预算: {budget1.config.task_budget}")
    print(f"   会话预算: {budget1.config.session_budget}")
    print(f"   Agent预算: {budget1.config.agent_budget}")
    print(f"   警告阈值: {budget1.config.warning_threshold}")
    
    # 方式2：从应用配置创建
    print("\n2. 从应用配置创建 BudgetConfig")
    from budget.manager import BudgetConfig
    from config import get_config
    
    app_config = get_config()
    budget_config = BudgetConfig.from_app_config(app_config)
    budget2 = BudgetManager(config=budget_config)
    print(f"   任务预算: {budget2.config.task_budget}")
    print(f"   背压启用: {budget2.config.backpressure_enabled}")


def demo_security_with_config():
    """演示使用配置创建 PromptGuard"""
    print("\n" + "=" * 50)
    print("使用配置创建 PromptGuard")
    print("=" * 50)
    
    # 方式1：不传配置，自动从配置文件加载
    print("\n1. 创建 PromptGuard（自动加载配置）")
    guard1 = PromptGuard()
    print(f"   最大长度: {guard1.max_length}")
    print(f"   PII检测: {guard1.enable_pii}")
    print(f"   危险检测: {guard1.enable_dangerous}")
    print(f"   屏蔽关键词: {guard1.blocked_keywords}")
    
    # 方式2：传入自定义配置（与配置文件合并）
    print("\n2. 创建 PromptGuard（自定义配置合并）")
    guard2 = PromptGuard({
        "max_prompt_length": 5000,
        "blocked_keywords": ["delete", "drop"],
    })
    print(f"   最大长度（自定义）: {guard2.max_length}")
    print(f"   屏蔽关键词（自定义）: {guard2.blocked_keywords}")


def demo_tracing_with_config():
    """演示使用配置创建 TracingManager"""
    print("\n" + "=" * 50)
    print("使用配置创建 TracingManager")
    print("=" * 50)
    
    # 方式1：不传配置，自动从配置文件加载
    print("\n1. 创建 TracingManager（自动加载配置）")
    tracing1 = TracingManager()
    tracing1.initialize()
    print(f"   启用: {tracing1.config.enabled}")
    print(f"   服务名称: {tracing1.config.service_name}")
    print(f"   OTLP端点: {tracing1.config.exporter_endpoint}")
    
    # 方式2：从应用配置创建
    print("\n2. 从应用配置创建 TracingConfig")
    from observability.tracing import TracingConfig
    from config import get_config
    
    app_config = get_config()
    tracing_config = TracingConfig.from_app_config(app_config)
    tracing2 = TracingManager(tracing_config)
    tracing2.initialize()
    print(f"   启用: {tracing2.config.enabled}")
    print(f"   服务名称: {tracing2.config.service_name}")


def demo_env_override():
    """演示环境变量覆盖配置"""
    print("\n" + "=" * 50)
    print("环境变量覆盖配置")
    print("=" * 50)
    
    # 设置环境变量
    os.environ["WORKAGENT_PORT"] = "9000"
    os.environ["WORKAGENT_DEFAULT_MODEL"] = "gpt-4o"
    os.environ["WORKAGENT_LOG_LEVEL"] = "DEBUG"
    
    # 重新加载配置
    config = reload_config()
    
    print("\n1. 环境变量覆盖后的配置")
    print(f"   端口: {config.server.port}")
    print(f"   默认模型: {config.agent.default_model}")
    print(f"   日志级别: {config.server.log_level}")
    
    # 清理环境变量
    del os.environ["WORKAGENT_PORT"]
    del os.environ["WORKAGENT_DEFAULT_MODEL"]
    del os.environ["WORKAGENT_LOG_LEVEL"]


def main():
    """主函数"""
    # 演示配置加载
    demo_config_loading()
    
    # 演示使用配置创建组件
    demo_agent_with_config()
    demo_budget_with_config()
    demo_security_with_config()
    demo_tracing_with_config()
    
    # 演示环境变量覆盖
    demo_env_override()
    
    print("\n" + "=" * 50)
    print("配置系统演示完成！")
    print("=" * 50)
    print("\n提示：")
    print("1. 修改 config/config.yaml 来更改默认配置")
    print("2. 使用环境变量 WORKAGENT_CONFIG 指定自定义配置文件路径")
    print("3. 使用环境变量（如 WORKAGENT_PORT）覆盖特定配置项")
    print("4. 所有组件都支持从配置文件自动加载配置")


if __name__ == "__main__":
    main()