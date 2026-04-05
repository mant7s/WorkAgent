"""TenantManager - 多租户管理器

基于轻量级 Agent 框架 v2 设计文档第 5.3 节实现：
- 数据行级隔离（tenant_id 字段）
- 资源配额隔离
- 配置隔离
- ContextVar 实现
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import structlog

from config import get_config

logger = structlog.get_logger(__name__)

# 租户上下文变量
tenant_context: ContextVar[Optional[str]] = ContextVar("tenant", default=None)


def get_current_tenant() -> Optional[str]:
    """获取当前租户 ID

    Returns:
        Optional[str]: 当前租户 ID
    """
    return tenant_context.get()


def set_current_tenant(tenant_id: str) -> None:
    """设置当前租户 ID

    Args:
        tenant_id: 租户 ID
    """
    tenant_context.set(tenant_id)


@dataclass
class TenantQuota:
    """租户配额配置

    Attributes:
        max_tokens_per_day: 每日最大 Token 数
        max_concurrent_tasks: 最大并发任务数
        max_requests_per_minute: 每分钟最大请求数
        allowed_models: 允许的模型列表
        max_workflows: 最大工作流数
        max_agents: 最大 Agent 数
    """

    max_tokens_per_day: int = 100000
    max_concurrent_tasks: int = 5
    max_requests_per_minute: int = 60
    allowed_models: List[str] = field(default_factory=lambda: ["gpt-4o-mini", "claude-sonnet"])
    max_workflows: int = 10
    max_agents: int = 5

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "max_tokens_per_day": self.max_tokens_per_day,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "max_requests_per_minute": self.max_requests_per_minute,
            "allowed_models": self.allowed_models,
            "max_workflows": self.max_workflows,
            "max_agents": self.max_agents,
        }


@dataclass
class TenantConfig:
    """租户配置

    Attributes:
        tenant_id: 租户唯一标识
        name: 租户名称
        quota: 配额配置
        settings: 自定义设置
        enabled: 是否启用
        metadata: 元数据
    """

    tenant_id: str
    name: str
    quota: TenantQuota = field(default_factory=TenantQuota)
    settings: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.tenant_id:
            self.tenant_id = str(uuid4())


class TenantContext:
    """租户上下文管理器

    用于在异步上下文中管理租户 ID。

    Example:
        >>> async with TenantContext("tenant_123"):
        ...     # 在这个上下文中，get_current_tenant() 返回 "tenant_123"
        ...     await process_request()
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._token: Optional[Any] = None

    async def __aenter__(self) -> TenantContext:
        self._token = tenant_context.set(self.tenant_id)
        logger.debug("tenant.context_entered", tenant_id=self.tenant_id)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._token:
            tenant_context.reset(self._token)
        logger.debug("tenant.context_exited", tenant_id=self.tenant_id)


class TenantManager:
    """多租户管理器

    实现：
    1. 数据行级隔离（tenant_id 字段）
    2. 资源配额隔离
    3. 配置隔离
    4. ContextVar 实现

    Example:
        >>> manager = TenantManager()
        >>>
        >>> # 注册租户
        >>> config = TenantConfig(
        ...     tenant_id="tenant_123",
        ...     name="Acme Corp",
        ...     quota=TenantQuota(max_tokens_per_day=50000)
        ... )
        >>> manager.register_tenant(config)
        >>>
        >>> # 设置当前租户
        >>> manager.set_tenant("tenant_123")
        >>>
        >>> # 检查配额
        >>> if manager.check_quota("tenant_123", tokens=1000):
        ...     # 执行操作
        ...     manager.record_usage("tenant_123", tokens=1000)
    """

    def __init__(self, multi_tenant_enabled: Optional[bool] = None):
        self._tenants: Dict[str, TenantConfig] = {}
        self._usage: Dict[str, Dict[str, Any]] = {}
        self._concurrent_tasks: Dict[str, int] = {}
        self._request_timestamps: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()
        
        # 从配置读取多租户设置
        app_config = get_config()
        self._enabled = multi_tenant_enabled if multi_tenant_enabled is not None else app_config.security.multi_tenant_enabled

        logger.info("tenant_manager.initialized", multi_tenant_enabled=self._enabled)

    def register_tenant(self, config: TenantConfig) -> None:
        """注册租户

        Args:
            config: 租户配置
        """
        self._tenants[config.tenant_id] = config
        self._usage[config.tenant_id] = {
            "tokens_today": 0,
            "workflows": 0,
            "agents": 0,
        }
        self._concurrent_tasks[config.tenant_id] = 0
        self._request_timestamps[config.tenant_id] = []

        logger.info(
            "tenant.registered",
            tenant_id=config.tenant_id,
            name=config.name,
        )

    def unregister_tenant(self, tenant_id: str) -> bool:
        """注销租户

        Args:
            tenant_id: 租户 ID

        Returns:
            bool: 是否成功
        """
        if tenant_id in self._tenants:
            del self._tenants[tenant_id]
            del self._usage[tenant_id]
            del self._concurrent_tasks[tenant_id]
            del self._request_timestamps[tenant_id]

            logger.info("tenant.unregistered", tenant_id=tenant_id)
            return True
        return False

    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        """获取租户配置

        Args:
            tenant_id: 租户 ID

        Returns:
            Optional[TenantConfig]: 租户配置
        """
        return self._tenants.get(tenant_id)

    def set_tenant(self, tenant_id: str) -> bool:
        """设置当前租户

        Args:
            tenant_id: 租户 ID

        Returns:
            bool: 是否成功
        """
        if tenant_id not in self._tenants:
            logger.warning("tenant.not_found", tenant_id=tenant_id)
            return False

        tenant_context.set(tenant_id)
        logger.debug("tenant.set_current", tenant_id=tenant_id)
        return True

    def get_current_tenant_id(self) -> Optional[str]:
        """获取当前租户 ID

        Returns:
            Optional[str]: 当前租户 ID
        """
        return tenant_context.get()

    def get_current_tenant_config(self) -> Optional[TenantConfig]:
        """获取当前租户配置

        Returns:
            Optional[TenantConfig]: 当前租户配置
        """
        tenant_id = self.get_current_tenant_id()
        if tenant_id:
            return self._tenants.get(tenant_id)
        return None

    def get_quota(self, tenant_id: str) -> Optional[TenantQuota]:
        """获取租户配额

        Args:
            tenant_id: 租户 ID

        Returns:
            Optional[TenantQuota]: 配额配置
        """
        tenant = self._tenants.get(tenant_id)
        return tenant.quota if tenant else None

    async def check_quota(
        self,
        tenant_id: str,
        tokens: int = 0,
        model: Optional[str] = None,
        check_concurrent: bool = True,
        check_rate_limit: bool = True,
    ) -> Dict[str, Any]:
        """检查配额

        Args:
            tenant_id: 租户 ID
            tokens: 预估 Token 数
            model: 模型名称
            check_concurrent: 是否检查并发
            check_rate_limit: 是否检查速率限制

        Returns:
            Dict: 检查结果
                - allowed: 是否允许
                - reason: 拒绝原因
                - quota: 配额信息
        """
        async with self._lock:
            tenant = self._tenants.get(tenant_id)
            if not tenant:
                return {"allowed": False, "reason": "Tenant not found"}

            if not tenant.enabled:
                return {"allowed": False, "reason": "Tenant is disabled"}

            quota = tenant.quota
            usage = self._usage.get(tenant_id, {})

            # 检查 Token 配额
            if tokens > 0:
                if usage.get("tokens_today", 0) + tokens > quota.max_tokens_per_day:
                    return {
                        "allowed": False,
                        "reason": f"Token quota exceeded: {usage['tokens_today'] + tokens}/{quota.max_tokens_per_day}",
                        "quota": quota.to_dict(),
                    }

            # 检查模型权限
            if model and quota.allowed_models:
                if model not in quota.allowed_models:
                    return {
                        "allowed": False,
                        "reason": f"Model not allowed: {model}",
                        "allowed_models": quota.allowed_models,
                    }

            # 检查并发
            if check_concurrent:
                current = self._concurrent_tasks.get(tenant_id, 0)
                if current >= quota.max_concurrent_tasks:
                    return {
                        "allowed": False,
                        "reason": f"Concurrent task limit reached: {current}/{quota.max_concurrent_tasks}",
                        "quota": quota.to_dict(),
                    }

            # 检查速率限制
            if check_rate_limit:
                now = asyncio.get_event_loop().time()
                timestamps = self._request_timestamps.get(tenant_id, [])
                # 清理过期的时间戳（1分钟前）
                valid_timestamps = [ts for ts in timestamps if now - ts < 60]
                if len(valid_timestamps) >= quota.max_requests_per_minute:
                    return {
                        "allowed": False,
                        "reason": f"Rate limit exceeded: {len(valid_timestamps)}/{quota.max_requests_per_minute} per minute",
                        "quota": quota.to_dict(),
                    }

            return {"allowed": True, "quota": quota.to_dict()}

    async def record_usage(
        self,
        tenant_id: str,
        tokens: int = 0,
        workflow: bool = False,
        agent: bool = False,
    ) -> None:
        """记录使用量

        Args:
            tenant_id: 租户 ID
            tokens: Token 使用量
            workflow: 是否创建工作流
            agent: 是否创建 Agent
        """
        async with self._lock:
            if tenant_id not in self._usage:
                self._usage[tenant_id] = {
                    "tokens_today": 0,
                    "workflows": 0,
                    "agents": 0,
                }

            usage = self._usage[tenant_id]
            usage["tokens_today"] += tokens

            if workflow:
                usage["workflows"] += 1
            if agent:
                usage["agents"] += 1

            # 记录请求时间戳
            if tenant_id not in self._request_timestamps:
                self._request_timestamps[tenant_id] = []
            self._request_timestamps[tenant_id].append(asyncio.get_event_loop().time())

            logger.debug(
                "tenant.usage_recorded",
                tenant_id=tenant_id,
                tokens=tokens,
                total_tokens=usage["tokens_today"],
            )

    async def increment_concurrent(self, tenant_id: str) -> bool:
        """增加并发计数

        Args:
            tenant_id: 租户 ID

        Returns:
            bool: 是否成功
        """
        async with self._lock:
            tenant = self._tenants.get(tenant_id)
            if not tenant:
                return False

            current = self._concurrent_tasks.get(tenant_id, 0)
            if current >= tenant.quota.max_concurrent_tasks:
                return False

            self._concurrent_tasks[tenant_id] = current + 1
            return True

    async def decrement_concurrent(self, tenant_id: str) -> None:
        """减少并发计数

        Args:
            tenant_id: 租户 ID
        """
        async with self._lock:
            if tenant_id in self._concurrent_tasks:
                self._concurrent_tasks[tenant_id] = max(
                    0, self._concurrent_tasks[tenant_id] - 1
                )

    def get_usage(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """获取使用量统计

        Args:
            tenant_id: 租户 ID

        Returns:
            Optional[Dict]: 使用量统计
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        usage = self._usage.get(tenant_id, {})
        quota = tenant.quota

        return {
            "tenant_id": tenant_id,
            "tokens": {
                "used": usage.get("tokens_today", 0),
                "quota": quota.max_tokens_per_day,
                "remaining": max(0, quota.max_tokens_per_day - usage.get("tokens_today", 0)),
            },
            "workflows": {
                "used": usage.get("workflows", 0),
                "quota": quota.max_workflows,
            },
            "agents": {
                "used": usage.get("agents", 0),
                "quota": quota.max_agents,
            },
            "concurrent_tasks": {
                "current": self._concurrent_tasks.get(tenant_id, 0),
                "quota": quota.max_concurrent_tasks,
            },
        }

    def list_tenants(self) -> List[str]:
        """列出所有租户 ID

        Returns:
            List[str]: 租户 ID 列表
        """
        return list(self._tenants.keys())

    def update_tenant_config(
        self, tenant_id: str, **kwargs: Any
    ) -> Optional[TenantConfig]:
        """更新租户配置

        Args:
            tenant_id: 租户 ID
            **kwargs: 要更新的字段

        Returns:
            Optional[TenantConfig]: 更新后的配置
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
            elif key in tenant.settings:
                tenant.settings[key] = value
            else:
                tenant.settings[key] = value

        logger.info("tenant.config_updated", tenant_id=tenant_id, updates=list(kwargs.keys()))
        return tenant

    async def reset_usage(self, tenant_id: Optional[str] = None) -> None:
        """重置使用量统计

        Args:
            tenant_id: 租户 ID（可选，不指定则重置所有）
        """
        async with self._lock:
            if tenant_id:
                if tenant_id in self._usage:
                    self._usage[tenant_id] = {
                        "tokens_today": 0,
                        "workflows": 0,
                        "agents": 0,
                    }
                if tenant_id in self._request_timestamps:
                    self._request_timestamps[tenant_id] = []
                logger.info("tenant.usage_reset", tenant_id=tenant_id)
            else:
                for tid in self._usage:
                    self._usage[tid] = {
                        "tokens_today": 0,
                        "workflows": 0,
                        "agents": 0,
                    }
                for tid in self._request_timestamps:
                    self._request_timestamps[tid] = []
                logger.info("tenant.all_usage_reset")


# 行级隔离装饰器示例
def with_tenant_isolation(func):
    """行级隔离装饰器（用于数据访问层）

    自动在查询中添加 tenant_id 过滤条件。

    Example:
        >>> @with_tenant_isolation
        ... async def get_session(session_id: str):
        ...     tenant_id = get_current_tenant()
        ...     # 查询时会自动过滤 tenant_id
        ...     return await db.query(Session).filter_by(
        ...         id=session_id,
        ...         tenant_id=tenant_id
        ...     ).first()
    """
    # 这是一个文档示例，实际实现需要根据 ORM 框架调整
    return func
