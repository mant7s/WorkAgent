"""WorkAgent 配置加载器

支持从 YAML 文件、环境变量和 .env 文件加载配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 可选依赖
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# 尝试加载 python-dotenv
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    load_dotenv = None


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False
    log_level: str = "INFO"


@dataclass
class AgentConfig:
    """Agent 配置"""
    default_model: str = "gpt-4o-mini"
    default_temperature: float = 0.7
    default_max_iterations: int = 10
    default_token_budget: int = 10000
    default_timeout: float = 300.0


@dataclass
class ModelConfig:
    """模型配置"""
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    default: bool = False  # 是否为默认模型


@dataclass
class BudgetConfig:
    """预算配置"""
    enabled: bool = True
    task_budget: int = 10000
    session_budget: int = 50000
    agent_budget: int = 5000
    warning_threshold: float = 0.8
    backpressure_enabled: bool = True


@dataclass
class SecurityConfig:
    """安全配置"""
    prompt_guard_enabled: bool = True
    max_prompt_length: int = 10000
    blocked_keywords: List[str] = field(default_factory=list)
    pii_redaction_enabled: bool = True
    multi_tenant_enabled: bool = False


@dataclass
class ObservabilityConfig:
    """可观测性配置"""
    tracing_enabled: bool = False
    otlp_endpoint: Optional[str] = None
    service_name: str = "workagent"
    metrics_enabled: bool = False
    metrics_port: int = 9090


@dataclass
class Config:
    """主配置类"""
    server: ServerConfig = field(default_factory=ServerConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    tools: Dict[str, Any] = field(default_factory=dict)
    skills: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """从字典创建配置"""
        config = cls()

        if "server" in data:
            config.server = ServerConfig(**data["server"])
        if "agent" in data:
            config.agent = AgentConfig(**data["agent"])
        if "models" in data:
            config.models = {}
            for name, model_data in data["models"].items():
                # 解析环境变量占位符
                resolved_data = {k: cls._resolve_env_value(v) for k, v in model_data.items()}
                config.models[name] = ModelConfig(**resolved_data)
            
            # 如果没有设置默认模型，将第一个模型设为默认
            if config.models and not any(m.default for m in config.models.values()):
                first_model = list(config.models.values())[0]
                first_model.default = True
        if "budget" in data:
            config.budget = BudgetConfig(**data["budget"])
        if "security" in data:
            config.security = SecurityConfig(**data["security"])
        if "observability" in data:
            config.observability = ObservabilityConfig(**data["observability"])
        if "tools" in data:
            config.tools = data["tools"]
        if "skills" in data:
            config.skills = data["skills"]

        return config

    @staticmethod
    def _resolve_env_value(value: Any) -> Any:
        """解析环境变量占位符
        
        支持格式：${ENV_VAR} 或 ${ENV_VAR:-default_value}
        """
        if not isinstance(value, str):
            return value
        
        import re
        pattern = r'\$\{([^}]+)\}'
        
        def replace_env_var(match):
            env_expr = match.group(1)
            # 检查是否有默认值 ${VAR:-default}
            if ':-' in env_expr:
                var_name, default = env_expr.split(':-', 1)
                return os.environ.get(var_name, default)
            else:
                return os.environ.get(env_expr, '')
        
        return re.sub(pattern, replace_env_var, value)

    def get_default_model(self) -> Optional[str]:
        """获取默认模型名称"""
        for name, model in self.models.items():
            if model.default:
                return name
        # 如果没有设置默认模型，返回第一个
        if self.models:
            return list(self.models.keys())[0]
        return None

    def get_model_config(self, name: Optional[str] = None) -> Optional[ModelConfig]:
        """获取模型配置
        
        Args:
            name: 模型名称，如果为 None 则返回默认模型
        """
        if name is None:
            name = self.get_default_model()
        return self.models.get(name) if name else None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "server": self.server.__dict__,
            "agent": self.agent.__dict__,
            "models": {
                name: model.__dict__
                for name, model in self.models.items()
            },
            "budget": self.budget.__dict__,
            "security": self.security.__dict__,
            "observability": self.observability.__dict__,
            "tools": self.tools,
            "skills": self.skills,
        }


def _load_dotenv():
    """加载 .env 文件
    
    优先级：
    1. .env.local（如果存在）
    2. .env（如果存在）
    """
    if not DOTENV_AVAILABLE:
        return
    
    # 先加载 .env
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
        logger.debug("dotenv_loaded", path=str(env_path))
    
    # 再加载 .env.local（覆盖 .env 中的值）
    env_local_path = Path(".env.local")
    if env_local_path.exists():
        load_dotenv(env_local_path, override=True)
        logger.debug("dotenv_loaded", path=str(env_local_path))


# 全局配置实例
_config: Optional[Config] = None


def load_config(config_path: Optional[str] = None) -> Config:
    """
    加载配置文件

    优先级：
    1. 指定的 config_path
    2. 环境变量 WORKAGENT_CONFIG
    3. 默认路径 config/config.yaml
    4. 使用默认配置
    
    环境变量优先级（从高到低）：
    1. 系统环境变量
    2. .env.local 文件
    3. .env 文件
    4. 配置文件中的值
    """
    global _config
    
    # 首先加载 .env 文件
    _load_dotenv()

    # 确定配置文件路径
    if config_path:
        path = Path(config_path)
    elif "WORKAGENT_CONFIG" in os.environ:
        path = Path(os.environ["WORKAGENT_CONFIG"])
    else:
        path = Path("config/config.yaml")

    # 如果 YAML 不可用，使用默认配置
    if not YAML_AVAILABLE:
        logger.warning("yaml_not_available", message="PyYAML not installed, using default config")
        _config = Config()
        return _config

    # 加载配置文件
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            _config = Config.from_dict(data)
            logger.info("config_loaded", path=str(path))
        except Exception as e:
            logger.error("config_load_failed", path=str(path), error=str(e))
            _config = Config()
    else:
        logger.warning("config_not_found", path=str(path), message="Using default config")
        _config = Config()

    # 从环境变量覆盖配置
    _override_from_env()

    return _config


def _override_from_env():
    """从环境变量覆盖配置"""
    global _config
    if _config is None:
        return

    # 服务器配置
    if "WORKAGENT_HOST" in os.environ:
        _config.server.host = os.environ["WORKAGENT_HOST"]
    if "WORKAGENT_PORT" in os.environ:
        _config.server.port = int(os.environ["WORKAGENT_PORT"])
    if "WORKAGENT_LOG_LEVEL" in os.environ:
        _config.server.log_level = os.environ["WORKAGENT_LOG_LEVEL"]

    # Agent 配置
    if "WORKAGENT_DEFAULT_MODEL" in os.environ:
        _config.agent.default_model = os.environ["WORKAGENT_DEFAULT_MODEL"]
    if "WORKAGENT_DEFAULT_TEMPERATURE" in os.environ:
        _config.agent.default_temperature = float(os.environ["WORKAGENT_DEFAULT_TEMPERATURE"])

    # OpenAI API Key
    if "OPENAI_API_KEY" in os.environ:
        if "openai" not in _config.models:
            _config.models["openai"] = ModelConfig()
        _config.models["openai"].api_key = os.environ["OPENAI_API_KEY"]

    # 可观测性
    if "OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ:
        _config.observability.tracing_enabled = True
        _config.observability.otlp_endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]


def get_config() -> Config:
    """获取当前配置"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> Config:
    """重新加载配置"""
    global _config
    _config = None
    return load_config()
