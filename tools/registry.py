"""WorkAgent 工具注册表"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, Union

import structlog

logger = structlog.get_logger()


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"
    dangerous: bool = False
    timeout: float = 30.0

    def to_openai_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters.get("properties", {}),
                    "required": self.parameters.get("required", []),
                },
            },
        }


class Tool:
    """工具类"""

    def __init__(
        self,
        func: Callable,
        metadata: ToolMetadata,
    ):
        self.func = func
        self.metadata = metadata
        self._logger = structlog.get_logger()

    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        self._logger.debug(
            "tool_executing",
            tool=self.metadata.name,
            params=kwargs,
        )

        try:
            if asyncio.iscoroutinefunction(self.func):
                result = await self.func(**kwargs)
            else:
                result = self.func(**kwargs)

            self._logger.debug(
                "tool_completed",
                tool=self.metadata.name,
                result_type=type(result).__name__,
            )
            return result

        except Exception as e:
            self._logger.error(
                "tool_execution_error",
                tool=self.metadata.name,
                error=str(e),
            )
            raise ToolExecutionError(f"Tool {self.metadata.name} failed: {e}") from e


class ToolExecutionError(Exception):
    """工具执行错误"""
    pass


class ToolRegistry:
    """
    工具注册表

    特性：
    1. 装饰器方式注册工具
    2. 参数自动提取
    3. 异步工具执行
    4. 工具 Schema 生成（OpenAI Function Calling 格式）
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._categories: Dict[str, List[str]] = {}
        self._logger = structlog.get_logger()

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        category: str = "general",
        dangerous: bool = False,
        timeout: float = 30.0,
    ) -> Callable:
        """
        工具注册装饰器

        Args:
            name: 工具名称，默认为函数名
            description: 工具描述，默认为函数 docstring
            category: 工具分类
            dangerous: 是否为危险工具
            timeout: 超时时间
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or ""

            # 提取参数信息
            sig = inspect.signature(func)
            properties: Dict[str, Any] = {}
            required: List[str] = []

            for param_name, param in sig.parameters.items():
                param_info: Dict[str, Any] = {
                    "type": "string",  # 默认类型
                }

                # 根据注解推断类型
                if param.annotation != inspect.Parameter.empty:
                    param_info["type"] = self._python_type_to_json_type(param.annotation)

                # 检查是否有默认值
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                else:
                    param_info["default"] = param.default

                properties[param_name] = param_info

            parameters = {
                "type": "object",
                "properties": properties,
                "required": required,
            }

            metadata = ToolMetadata(
                name=tool_name,
                description=tool_desc,
                parameters=parameters,
                category=category,
                dangerous=dangerous,
                timeout=timeout,
            )

            tool = Tool(func, metadata)
            self._tools[tool_name] = tool

            if category not in self._categories:
                self._categories[category] = []
            if tool_name not in self._categories[category]:
                self._categories[category].append(tool_name)

            self._logger.debug(
                "tool_registered",
                name=tool_name,
                category=category,
                dangerous=dangerous,
            )

            return func
        return decorator

    def _python_type_to_json_type(self, py_type: Type) -> str:
        """将 Python 类型转换为 JSON Schema 类型"""
        type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        # 处理 Optional 类型
        origin = getattr(py_type, "__origin__", None)
        if origin is Union:
            args = getattr(py_type, "__args__", ())
            # 找到非 None 的类型
            for arg in args:
                if arg is not type(None):
                    py_type = arg
                    break

        return type_mapping.get(py_type, "string")

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[ToolMetadata]:
        """列出工具"""
        if category:
            return [self._tools[name].metadata for name in self._categories.get(category, [])]
        return [tool.metadata for tool in self._tools.values()]

    def get_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI Function Calling Schema"""
        return [tool.metadata.to_openai_schema() for tool in self._tools.values()]

    def describe_tools(self) -> str:
        """生成工具描述（用于 Prompt）"""
        descriptions = []
        for tool in self._tools.values():
            desc = f"- {tool.metadata.name}: {tool.metadata.description}"
            if tool.metadata.parameters.get("properties"):
                params = ", ".join(tool.metadata.parameters["properties"].keys())
                desc += f" (参数: {params})"
            descriptions.append(desc)
        return "\n".join(descriptions)

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def remove_tool(self, name: str) -> bool:
        """移除工具"""
        if name not in self._tools:
            return False

        tool = self._tools.pop(name)
        category = tool.metadata.category
        if category in self._categories and name in self._categories[category]:
            self._categories[category].remove(name)

        return True

    def clear(self) -> None:
        """清空所有工具"""
        self._tools.clear()
        self._categories.clear()

    async def execute(self, name: str, **kwargs) -> Any:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            raise ToolExecutionError(f"Tool not found: {name}")
        return await tool.execute(**kwargs)
