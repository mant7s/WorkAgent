"""OpenTelemetry Tracing - 链路追踪

基于轻量级 Agent 框架 v2 设计文档第 5.1 节实现：
- OpenTelemetry Tracer、Span
- 装饰器方式
- 可选依赖，不强制
"""

from __future__ import annotations

import asyncio
import functools
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, TypeVar, Union

import structlog

from config import get_config

logger = structlog.get_logger(__name__)

# 尝试导入 OpenTelemetry，如果不存在则使用 mock
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    trace = None
    Status = None
    StatusCode = None

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class TracingConfig:
    """链路追踪配置

    Attributes:
        enabled: 是否启用
        service_name: 服务名称
        exporter_endpoint: OTLP 导出端点
        console_export: 是否导出到控制台
        sample_rate: 采样率（0.0 - 1.0）
        attributes: 全局属性
    """

    enabled: bool = True
    service_name: str = "agent-framework"
    exporter_endpoint: Optional[str] = None
    console_export: bool = False
    sample_rate: float = 1.0
    attributes: Dict[str, Any] = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}

    @classmethod
    def from_app_config(cls, app_config=None) -> "TracingConfig":
        """从应用配置创建追踪配置"""
        if app_config is None:
            app_config = get_config()
        
        return cls(
            enabled=app_config.observability.tracing_enabled,
            service_name=app_config.observability.service_name,
            exporter_endpoint=app_config.observability.otlp_endpoint,
            console_export=False,
            sample_rate=1.0,
        )


class MockSpan:
    """Mock Span - 当 OpenTelemetry 不可用时使用"""

    def __init__(self, name: str, attributes: Optional[Dict] = None):
        self.name = name
        self.attributes = attributes or {}
        self._status = "unset"

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_attributes(self, attributes: Dict[str, Any]) -> None:
        self.attributes.update(attributes)

    def set_status(self, status: Any, description: Optional[str] = None) -> None:
        self._status = str(status)

    def record_exception(self, exception: Exception, attributes: Optional[Dict] = None) -> None:
        logger.exception(
            "mock_span.exception",
            span_name=self.name,
            exception=str(exception),
            attributes=attributes,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockTracer:
    """Mock Tracer - 当 OpenTelemetry 不可用时使用"""

    def __init__(self, name: str = "mock"):
        self.name = name

    def start_as_current_span(
        self,
        name: str,
        context: Optional[Any] = None,
        kind: Optional[Any] = None,
        attributes: Optional[Dict] = None,
        links: Optional[Any] = None,
        start_time: Optional[Any] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ):
        return MockSpan(name, attributes)

    def start_span(
        self,
        name: str,
        context: Optional[Any] = None,
        kind: Optional[Any] = None,
        attributes: Optional[Dict] = None,
        links: Optional[Any] = None,
        start_time: Optional[Any] = None,
    ):
        return MockSpan(name, attributes)


def _get_mock_tracer(name: str = "mock") -> MockTracer:
    return MockTracer(name)


class TracingManager:
    """链路追踪管理器

    管理 OpenTelemetry Tracer 的生命周期和配置。
    当 OpenTelemetry 不可用时，自动降级为 Mock 实现。

    Example:
        >>> config = TracingConfig(
        ...     enabled=True,
        ...     service_name="my-agent",
        ...     exporter_endpoint="http://localhost:4317",
        ... )
        >>> manager = TracingManager(config)
        >>> manager.initialize()
        >>>
        >>> # 使用 tracer
        >>> tracer = manager.get_tracer()
        >>> with tracer.start_as_current_span("my_operation") as span:
        ...     span.set_attribute("key", "value")
    """

    _instance: Optional[TracingManager] = None
    _initialized: bool = False

    def __new__(cls, config: Optional[TracingConfig] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Optional[TracingConfig] = None):
        if self._initialized:
            return

        # 如果没有传入配置，从应用配置创建
        if config is None:
            config = TracingConfig.from_app_config()
        
        self.config = config
        self._tracer: Optional[Any] = None
        self._provider: Optional[Any] = None

    def initialize(self) -> bool:
        """初始化链路追踪

        Returns:
            bool: 是否成功初始化
        """
        if not self.config.enabled:
            logger.info("tracing.disabled")
            self._tracer = _get_mock_tracer()
            return True

        if not OPENTELEMETRY_AVAILABLE:
            logger.warning("opentelemetry.not_available, using mock tracer")
            self._tracer = _get_mock_tracer()
            return False

        try:
            # 创建 Provider
            self._provider = TracerProvider()

            # 添加控制台导出器（用于调试）
            if self.config.console_export:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter

                processor = BatchSpanProcessor(ConsoleSpanExporter())
                self._provider.add_span_processor(processor)

            # 添加 OTLP 导出器
            if self.config.exporter_endpoint:
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )

                    otlp_exporter = OTLPSpanExporter(
                        endpoint=self.config.exporter_endpoint,
                        insecure=True,
                    )
                    processor = BatchSpanProcessor(otlp_exporter)
                    self._provider.add_span_processor(processor)
                except ImportError:
                    logger.warning("otlp_exporter.not_available")

            # 设置为全局 provider
            trace.set_tracer_provider(self._provider)

            # 获取 tracer
            self._tracer = trace.get_tracer(
                self.config.service_name,
                "0.1.0",
            )

            self._initialized = True

            logger.info(
                "tracing.initialized",
                service_name=self.config.service_name,
                exporter_endpoint=self.config.exporter_endpoint,
            )

            return True

        except Exception as e:
            logger.error("tracing.initialization_failed", error=str(e))
            self._tracer = _get_mock_tracer()
            return False

    def get_tracer(self) -> Any:
        """获取 tracer

        Returns:
            Tracer: OpenTelemetry Tracer 或 MockTracer
        """
        if self._tracer is None:
            self.initialize()
        return self._tracer

    def shutdown(self) -> None:
        """关闭链路追踪"""
        if self._provider and OPENTELEMETRY_AVAILABLE:
            self._provider.shutdown()
            logger.info("tracing.shutdown")

    @classmethod
    def get_instance(cls) -> TracingManager:
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# 全局 tracer 获取函数
def get_tracer(name: Optional[str] = None) -> Any:
    """获取 tracer

    Args:
        name: tracer 名称（可选）

    Returns:
        Tracer: OpenTelemetry Tracer 或 MockTracer
    """
    manager = TracingManager.get_instance()
    tracer = manager.get_tracer()

    if name and OPENTELEMETRY_AVAILABLE:
        return trace.get_tracer(name)

    return tracer


def start_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    context: Optional[Any] = None,
) -> Any:
    """开始一个 span

    Args:
        name: span 名称
        attributes: 属性
        context: 上下文

    Returns:
        Span: OpenTelemetry Span 或 MockSpan
    """
    tracer = get_tracer()
    return tracer.start_as_current_span(name, context=context, attributes=attributes)


def get_current_span() -> Optional[Any]:
    """获取当前 span

    Returns:
        Optional[Span]: 当前 span
    """
    if not OPENTELEMETRY_AVAILABLE:
        return None
    return trace.get_current_span()


def set_span_attribute(key: str, value: Any) -> None:
    """设置当前 span 的属性

    Args:
        key: 属性名
        value: 属性值
    """
    span = get_current_span()
    if span:
        span.set_attribute(key, value)


def record_exception(exception: Exception, attributes: Optional[Dict] = None) -> None:
    """记录异常到当前 span

    Args:
        exception: 异常对象
        attributes: 额外属性
    """
    span = get_current_span()
    if span:
        span.record_exception(exception, attributes)


def trace_span(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    component: Optional[str] = None,
):
    """追踪装饰器

    自动为函数创建 span，记录执行时间和异常。

    Args:
        name: span 名称（默认为函数名）
        attributes: 属性
        component: 组件名

    Example:
        >>> @trace_span("agent.run", {"component": "agent"})
        ... async def run_agent(query: str) -> str:
        ...     return await process(query)
        >>>
        >>> @trace_span(component="tools")
        ... def execute_tool(tool_name: str) -> Any:
        ...     return tool_registry.execute(tool_name)
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__
        span_attributes = attributes or {}

        if component:
            span_attributes["component"] = component

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()

            with tracer.start_as_current_span(
                span_name, attributes=span_attributes
            ) as span:
                # 记录函数参数
                if args:
                    span.set_attribute("args_count", len(args))
                if kwargs:
                    span.set_attribute("kwargs_keys", list(kwargs.keys()))

                start_time = time.time()

                try:
                    result = await func(*args, **kwargs)

                    # 记录成功
                    duration = time.time() - start_time
                    span.set_attribute("duration_ms", duration * 1000)
                    span.set_attribute("status", "success")

                    if OPENTELEMETRY_AVAILABLE:
                        span.set_status(Status(StatusCode.OK))

                    return result

                except Exception as e:
                    # 记录异常
                    duration = time.time() - start_time
                    span.set_attribute("duration_ms", duration * 1000)
                    span.set_attribute("status", "error")
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))

                    if OPENTELEMETRY_AVAILABLE:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)

                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()

            with tracer.start_as_current_span(
                span_name, attributes=span_attributes
            ) as span:
                if args:
                    span.set_attribute("args_count", len(args))
                if kwargs:
                    span.set_attribute("kwargs_keys", list(kwargs.keys()))

                start_time = time.time()

                try:
                    result = func(*args, **kwargs)

                    duration = time.time() - start_time
                    span.set_attribute("duration_ms", duration * 1000)
                    span.set_attribute("status", "success")

                    if OPENTELEMETRY_AVAILABLE:
                        span.set_status(Status(StatusCode.OK))

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    span.set_attribute("duration_ms", duration * 1000)
                    span.set_attribute("status", "error")
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))

                    if OPENTELEMETRY_AVAILABLE:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)

                    raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# 便捷装饰器
def trace_agent(name: Optional[str] = None):
    """Agent 追踪装饰器"""
    return trace_span(name or "agent.run", component="agent")


def trace_tool(name: Optional[str] = None):
    """工具追踪装饰器"""
    return trace_span(name or "tool.execute", component="tool")


def trace_workflow(name: Optional[str] = None):
    """工作流追踪装饰器"""
    return trace_span(name or "workflow.execute", component="workflow")


def trace_llm(name: Optional[str] = None):
    """LLM 调用追踪装饰器"""
    return trace_span(name or "llm.call", component="llm")


# 上下文管理器
@contextmanager
def span_context(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
):
    """Span 上下文管理器

    Example:
        >>> with span_context("my_operation", {"key": "value"}) as span:
        ...     result = do_something()
        ...     span.set_attribute("result", result)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span


# 初始化函数
def initialize_tracing(
    service_name: str = "agent-framework",
    exporter_endpoint: Optional[str] = None,
    console_export: bool = False,
    enabled: bool = True,
) -> TracingManager:
    """初始化链路追踪

    Args:
        service_name: 服务名称
        exporter_endpoint: OTLP 导出端点
        console_export: 是否导出到控制台
        enabled: 是否启用

    Returns:
        TracingManager: 追踪管理器实例
    """
    config = TracingConfig(
        enabled=enabled,
        service_name=service_name,
        exporter_endpoint=exporter_endpoint,
        console_export=console_export,
    )

    manager = TracingManager(config)
    manager.initialize()

    return manager


# 检查 OpenTelemetry 是否可用
def is_tracing_available() -> bool:
    """检查 OpenTelemetry 是否可用

    Returns:
        bool: 是否可用
    """
    return OPENTELEMETRY_AVAILABLE


def initialize_from_config() -> TracingManager:
    """从配置文件初始化链路追踪

    Returns:
        TracingManager: 追踪管理器实例
    """
    config = TracingConfig.from_app_config()
    manager = TracingManager(config)
    manager.initialize()
    return manager
