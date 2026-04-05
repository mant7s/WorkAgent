"""BudgetManager - 三级预算控制 + 背压控制

基于轻量级 Agent 框架 v2 设计文档第 4.3 节实现：
- 三级预算：task_budget / session_budget / agent_budget
- 三种模式：HARD_LIMIT / SOFT_LIMIT / REQUIRE_APPROVAL
- 背压控制：根据使用率计算延迟
- 幂等性保证
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

from config import get_config

logger = structlog.get_logger(__name__)


class BudgetMode(Enum):
    """预算控制模式"""

    HARD_LIMIT = "hard"  # 超出即拒绝
    SOFT_LIMIT = "soft"  # 超出警告但继续
    REQUIRE_APPROVAL = "approval"  # 超出需人工确认


@dataclass
class BudgetConfig:
    """预算配置

    Attributes:
        task_budget: 任务级预算（单个任务最大 Token 数）
        session_budget: 会话级预算（整个会话累计 Token 数）
        agent_budget: Agent 级预算（单个 Agent 执行最大 Token 数）
        mode: 预算控制模式
        warning_threshold: 警告阈值（使用率超过此值触发警告）
        backpressure_enabled: 是否启用背压控制
    """

    task_budget: int = 10000
    session_budget: int = 50000
    agent_budget: int = 5000
    mode: BudgetMode = BudgetMode.SOFT_LIMIT
    warning_threshold: float = 0.8
    backpressure_enabled: bool = True

    @classmethod
    def from_app_config(cls, app_config=None) -> "BudgetConfig":
        """从应用配置创建预算配置"""
        if app_config is None:
            app_config = get_config()
        
        return cls(
            task_budget=app_config.budget.task_budget,
            session_budget=app_config.budget.session_budget,
            agent_budget=app_config.budget.agent_budget,
            warning_threshold=app_config.budget.warning_threshold,
            backpressure_enabled=app_config.budget.backpressure_enabled,
        )


@dataclass
class BudgetCheckResult:
    """预算检查结果

    Attributes:
        can_proceed: 是否可以继续执行
        reason: 拒绝原因（如果 can_proceed 为 False）
        warnings: 警告信息列表
        require_approval: 是否需要人工审批
        backpressure_delay: 背压延迟（秒）
        usage_ratio: 当前使用率
    """

    can_proceed: bool = True
    reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    require_approval: bool = False
    backpressure_delay: float = 0.0
    usage_ratio: float = 0.0


class BudgetExceededError(Exception):
    """预算超出错误"""

    pass


class CircuitBreaker:
    """熔断器 - 防止级联故障

    状态流转：
    CLOSED -> OPEN（失败次数超过阈值）
    OPEN -> HALF_OPEN（超时后）
    HALF_OPEN -> CLOSED（成功）
    HALF_OPEN -> OPEN（失败）
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        """当前状态"""
        return self._state

    async def can_execute(self) -> bool:
        """检查是否可以执行"""
        async with self._lock:
            if self._state == "CLOSED":
                return True

            if self._state == "OPEN":
                # 检查是否超过恢复超时
                if self._last_failure_time and (
                    time.time() - self._last_failure_time >= self.recovery_timeout
                ):
                    self._state = "HALF_OPEN"
                    self._half_open_calls = 0
                    logger.info("circuit_breaker.state_change", state="HALF_OPEN")
                    return True
                return False

            if self._state == "HALF_OPEN":
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            return True

    async def record_success(self) -> None:
        """记录成功"""
        async with self._lock:
            if self._state == "HALF_OPEN":
                self._state = "CLOSED"
                self._failure_count = 0
                self._half_open_calls = 0
                logger.info("circuit_breaker.state_change", state="CLOSED")
            else:
                self._failure_count = max(0, self._failure_count - 1)

    async def record_failure(self) -> None:
        """记录失败"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                logger.warning("circuit_breaker.state_change", state="OPEN")
            elif self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                logger.warning(
                    "circuit_breaker.opened",
                    failure_count=self._failure_count,
                    threshold=self.failure_threshold,
                )


class BudgetManager:
    """Token 预算管理器

    三级预算控制：
    1. Task: 单次任务
    2. Session: 会话累计
    3. Agent: 单 Agent 执行

    特性：
    - 背压控制（渐进式减速）
    - 熔断器模式
    - 幂等性保证

    Example:
        >>> config = BudgetConfig(
        ...     task_budget=10000,
        ...     session_budget=50000,
        ...     mode=BudgetMode.SOFT_LIMIT
        ... )
        >>> manager = BudgetManager(config)
        >>> result = await manager.check_budget(
        ...     task_id="task_1",
        ...     session_id="session_1",
        ...     agent_id="agent_1",
        ...     estimated_tokens=1000
        ... )
        >>> if result.can_proceed:
        ...     # 执行操作
        ...     await manager.record_usage("task_1", "session_1", 800, "key_1")
    """

    def __init__(self, config: Optional[BudgetConfig] = None):
        # 如果没有传入配置，从应用配置创建
        if config is None:
            config = BudgetConfig.from_app_config()
        self.config = config
        self._task_usage: Dict[str, int] = {}
        self._session_usage: Dict[str, int] = {}
        self._agent_usage: Dict[str, int] = {}
        self._processed_keys: Set[str] = set()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

        logger.info(
            "budget_manager.initialized",
            task_budget=self.config.task_budget,
            session_budget=self.config.session_budget,
            agent_budget=self.config.agent_budget,
            mode=self.config.mode.value,
        )

    async def check_budget(
        self,
        task_id: str,
        session_id: str,
        agent_id: str,
        estimated_tokens: int,
    ) -> BudgetCheckResult:
        """检查预算

        Args:
            task_id: 任务 ID
            session_id: 会话 ID
            agent_id: Agent ID
            estimated_tokens: 预估 Token 使用量

        Returns:
            BudgetCheckResult: 检查结果
        """
        async with self._lock:
            # 获取当前使用量
            task_used = self._task_usage.get(task_id, 0)
            session_used = self._session_usage.get(session_id, 0)
            agent_used = self._agent_usage.get(agent_id, 0)

            # 计算预估后总量
            task_total = task_used + estimated_tokens
            session_total = session_used + estimated_tokens
            agent_total = agent_used + estimated_tokens

            result = BudgetCheckResult(can_proceed=True)

            # 检查 Agent 预算
            if agent_total > self.config.agent_budget:
                if self.config.mode == BudgetMode.HARD_LIMIT:
                    result.can_proceed = False
                    result.reason = (
                        f"Agent budget exceeded: {agent_total}/{self.config.agent_budget}"
                    )
                elif self.config.mode == BudgetMode.REQUIRE_APPROVAL:
                    result.require_approval = True
                    result.warnings.append("Agent budget will be exceeded")
                else:
                    result.warnings.append("Agent budget will be exceeded")

            # 检查任务预算
            if task_total > self.config.task_budget:
                if self.config.mode == BudgetMode.HARD_LIMIT:
                    result.can_proceed = False
                    result.reason = f"Task budget exceeded: {task_total}/{self.config.task_budget}"
                elif self.config.mode == BudgetMode.REQUIRE_APPROVAL:
                    result.require_approval = True
                    result.warnings.append("Task budget will be exceeded")
                else:
                    result.warnings.append("Task budget will be exceeded")

            # 检查会话预算
            if session_total > self.config.session_budget:
                if self.config.mode == BudgetMode.HARD_LIMIT:
                    result.can_proceed = False
                    result.reason = (
                        f"Session budget exceeded: {session_total}/{self.config.session_budget}"
                    )
                else:
                    result.warnings.append("Session budget will be exceeded")

            # 计算背压延迟
            if self.config.backpressure_enabled:
                usage_ratio = session_total / self.config.session_budget
                result.usage_ratio = usage_ratio
                result.backpressure_delay = self._calculate_backpressure(usage_ratio)

                if result.backpressure_delay > 0:
                    logger.debug(
                        "budget_manager.backpressure_applied",
                        delay=result.backpressure_delay,
                        usage_ratio=usage_ratio,
                    )

            return result

    def _calculate_backpressure(self, usage_ratio: float) -> float:
        """计算背压延迟

        根据使用率计算延迟时间：
        - usage_ratio < 0.8 → 0ms
        - 0.8-0.85 → 50ms
        - 0.85-0.9 → 300ms
        - 0.9-0.95 → 750ms
        - >0.95 → 1500ms

        Args:
            usage_ratio: 使用率（0.0 - 1.0）

        Returns:
            float: 延迟时间（秒）
        """
        if usage_ratio < self.config.warning_threshold:
            return 0.0
        elif usage_ratio < 0.85:
            return 0.05  # 50ms
        elif usage_ratio < 0.9:
            return 0.3  # 300ms
        elif usage_ratio < 0.95:
            return 0.75  # 750ms
        else:
            return 1.5  # 1500ms

    async def record_usage(
        self,
        task_id: str,
        session_id: str,
        agent_id: str,
        tokens_used: int,
        idempotency_key: str,
    ) -> None:
        """记录使用量（幂等）

        Args:
            task_id: 任务 ID
            session_id: 会话 ID
            agent_id: Agent ID
            tokens_used: 实际使用的 Token 数
            idempotency_key: 幂等性键（防止重复记录）
        """
        async with self._lock:
            # 检查幂等性
            if idempotency_key in self._processed_keys:
                logger.debug(
                    "budget_manager.duplicate_request_skipped",
                    idempotency_key=idempotency_key,
                )
                return

            self._task_usage[task_id] = self._task_usage.get(task_id, 0) + tokens_used
            self._session_usage[session_id] = (
                self._session_usage.get(session_id, 0) + tokens_used
            )
            self._agent_usage[agent_id] = self._agent_usage.get(agent_id, 0) + tokens_used

            self._processed_keys.add(idempotency_key)

            logger.info(
                "budget_manager.usage_recorded",
                task_id=task_id,
                session_id=session_id,
                agent_id=agent_id,
                tokens_used=tokens_used,
                task_total=self._task_usage[task_id],
                session_total=self._session_usage[session_id],
                agent_total=self._agent_usage[agent_id],
            )

    async def get_usage(
        self, task_id: Optional[str] = None, session_id: Optional[str] = None, agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取使用量统计

        Args:
            task_id: 任务 ID（可选）
            session_id: 会话 ID（可选）
            agent_id: Agent ID（可选）

        Returns:
            Dict: 使用量统计
        """
        async with self._lock:
            result = {
                "task_usage": {},
                "session_usage": {},
                "agent_usage": {},
            }

            if task_id:
                used = self._task_usage.get(task_id, 0)
                result["task_usage"] = {
                    "id": task_id,
                    "used": used,
                    "budget": self.config.task_budget,
                    "remaining": max(0, self.config.task_budget - used),
                    "usage_ratio": used / self.config.task_budget if self.config.task_budget > 0 else 0,
                }

            if session_id:
                used = self._session_usage.get(session_id, 0)
                result["session_usage"] = {
                    "id": session_id,
                    "used": used,
                    "budget": self.config.session_budget,
                    "remaining": max(0, self.config.session_budget - used),
                    "usage_ratio": used / self.config.session_budget if self.config.session_budget > 0 else 0,
                }

            if agent_id:
                used = self._agent_usage.get(agent_id, 0)
                result["agent_usage"] = {
                    "id": agent_id,
                    "used": used,
                    "budget": self.config.agent_budget,
                    "remaining": max(0, self.config.agent_budget - used),
                    "usage_ratio": used / self.config.agent_budget if self.config.agent_budget > 0 else 0,
                }

            return result

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """获取或创建熔断器

        Args:
            name: 熔断器名称

        Returns:
            CircuitBreaker: 熔断器实例
        """
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker()
        return self._circuit_breakers[name]

    async def reset(self, task_id: Optional[str] = None, session_id: Optional[str] = None) -> None:
        """重置预算统计

        Args:
            task_id: 要重置的任务 ID（可选）
            session_id: 要重置的会话 ID（可选）
        """
        async with self._lock:
            if task_id:
                self._task_usage.pop(task_id, None)
                logger.info("budget_manager.task_reset", task_id=task_id)

            if session_id:
                self._session_usage.pop(session_id, None)
                logger.info("budget_manager.session_reset", session_id=session_id)

            if not task_id and not session_id:
                self._task_usage.clear()
                self._session_usage.clear()
                self._agent_usage.clear()
                self._processed_keys.clear()
                logger.info("budget_manager.all_reset")

    async def apply_backpressure(self, session_id: str) -> float:
        """应用背压延迟

        Args:
            session_id: 会话 ID

        Returns:
            float: 实际延迟时间（秒）
        """
        usage = await self.get_usage(session_id=session_id)
        session_data = usage.get("session_usage", {})
        usage_ratio = session_data.get("usage_ratio", 0.0)

        delay = self._calculate_backpressure(usage_ratio)
        if delay > 0:
            logger.info(
                "budget_manager.backpressure_sleep",
                session_id=session_id,
                delay=delay,
                usage_ratio=usage_ratio,
            )
            await asyncio.sleep(delay)

        return delay
