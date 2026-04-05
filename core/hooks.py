"""WorkAgent 事件钩子系统"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class HookEvent:
    """钩子事件数据"""
    name: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None


HookHandler = Callable[[HookEvent], Any]
AsyncHookHandler = Callable[[HookEvent], Any]


class HookManager:
    """
    事件钩子管理器

    支持同步和异步钩子处理函数
    支持事件优先级和一次性钩子
    """

    def __init__(self):
        self._handlers: Dict[str, List[tuple[int, HookHandler]]] = {}
        self._once_handlers: Dict[str, List[tuple[int, HookHandler]]] = {}
        self._logger = structlog.get_logger()

    def register(
        self,
        event: str,
        handler: HookHandler | AsyncHookHandler,
        priority: int = 0,
        once: bool = False,
    ) -> HookManager:
        """
        注册事件钩子

        Args:
            event: 事件名称
            handler: 处理函数
            priority: 优先级（数字越大越先执行）
            once: 是否只执行一次
        """
        target = self._once_handlers if once else self._handlers

        if event not in target:
            target[event] = []

        target[event].append((priority, handler))
        target[event].sort(key=lambda x: x[0], reverse=True)

        self._logger.debug(
            "hook_registered",
            event_name=event,
            handler=handler.__name__,
            priority=priority,
            once=once,
        )
        return self

    def unregister(self, event: str, handler: HookHandler) -> bool:
        """
        注销事件钩子

        Returns:
            是否成功注销
        """
        for target in [self._handlers, self._once_handlers]:
            if event in target:
                original_len = len(target[event])
                target[event] = [(p, h) for p, h in target[event] if h != handler]
                if len(target[event]) < original_len:
                    return True
        return False

    async def trigger(self, event: str, data: Dict[str, Any], source: Optional[str] = None) -> None:
        """
        触发事件

        Args:
            event: 事件名称
            data: 事件数据
            source: 事件来源
        """
        hook_event = HookEvent(name=event, data=data, source=source)

        # 处理普通钩子
        if event in self._handlers:
            for priority, handler in self._handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(hook_event)
                    else:
                        handler(hook_event)
                except Exception as e:
                    self._logger.error(
                        "hook_handler_error",
                        event_name=event,
                        handler=handler.__name__,
                        error=str(e),
                    )

        # 处理一次性钩子
        if event in self._once_handlers:
            for priority, handler in self._once_handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(hook_event)
                    else:
                        handler(hook_event)
                except Exception as e:
                    self._logger.error(
                        "hook_handler_error",
                        event_name=event,
                        handler=handler.__name__,
                        error=str(e),
                    )
            # 清除一次性钩子
            del self._once_handlers[event]

    def on(self, event: str, priority: int = 0) -> Callable:
        """
        装饰器方式注册钩子

        Example:
            @hooks.on("agent:started")
            async def on_agent_started(event):
                print(f"Agent started: {event.data}")
        """
        def decorator(handler: HookHandler) -> HookHandler:
            self.register(event, handler, priority)
            return handler
        return decorator

    def once(self, event: str, priority: int = 0) -> Callable:
        """
        装饰器方式注册一次性钩子

        Example:
            @hooks.once("agent:completed")
            async def on_agent_completed(event):
                print(f"Agent completed: {event.data}")
        """
        def decorator(handler: HookHandler) -> HookHandler:
            self.register(event, handler, priority, once=True)
            return handler
        return decorator

    def clear(self, event: Optional[str] = None) -> None:
        """
        清除钩子

        Args:
            event: 事件名称，如果为 None 则清除所有钩子
        """
        if event:
            self._handlers.pop(event, None)
            self._once_handlers.pop(event, None)
        else:
            self._handlers.clear()
            self._once_handlers.clear()

    def list_events(self) -> List[str]:
        """列出所有已注册事件"""
        events = set(self._handlers.keys()) | set(self._once_handlers.keys())
        return sorted(list(events))

    def get_handlers(self, event: str) -> List[HookHandler]:
        """获取事件的所有处理函数"""
        handlers = []
        if event in self._handlers:
            handlers.extend([h for _, h in self._handlers[event]])
        if event in self._once_handlers:
            handlers.extend([h for _, h in self._once_handlers[event]])
        return handlers
