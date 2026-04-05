"""WorkAgent 内置工具"""

from __future__ import annotations

import asyncio
import json
import math
import random
import re
from typing import Any, Dict, List, Optional

import structlog

from .registry import ToolRegistry

logger = structlog.get_logger()


def get_builtin_registry() -> ToolRegistry:
    """获取包含所有内置工具的注册表"""
    registry = ToolRegistry()

    # 注册所有内置工具
    _register_calculator(registry)
    _register_web_search(registry)
    _register_datetime(registry)

    return registry


def _register_calculator(registry: ToolRegistry) -> None:
    """注册计算器工具"""

    @registry.register(
        name="calculator",
        description="执行数学计算，支持基本运算、科学计算函数",
        category="math",
    )
    def calculator(expression: str) -> str:
        """
        安全执行数学表达式

        Args:
            expression: 数学表达式，如 "15 * 23" 或 "sqrt(16)"

        Returns:
            计算结果
        """
        logger.info(f"🧮 Calculating: {expression}")

        # 清理表达式
        expression = expression.strip()

        # 定义允许的函数和常量
        safe_dict = {
            # 数学函数
            "abs": abs,
            "round": round,
            "max": max,
            "min": min,
            "sum": sum,
            # 数学常量
            "pi": math.pi,
            "e": math.e,
            # 数学模块函数
            "sqrt": math.sqrt,
            "pow": math.pow,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            "ceil": math.ceil,
            "floor": math.floor,
            "factorial": math.factorial,
        }

        try:
            # 安全评估表达式
            result = eval(expression, {"__builtins__": {}}, safe_dict)

            # 格式化结果
            if isinstance(result, float):
                # 处理浮点数精度问题
                if result == int(result):
                    return str(int(result))
                return f"{result:.10f}".rstrip("0").rstrip(".")

            return str(result)

        except ZeroDivisionError:
            return "Error: Division by zero"
        except Exception as e:
            return f"Error: {str(e)}"


def _register_web_search(registry: ToolRegistry) -> None:
    """注册网页搜索工具（模拟实现）"""

    @registry.register(
        name="web_search",
        description="搜索网页信息，返回相关结果列表",
        category="search",
    )
    async def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        模拟网页搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（默认5）

        Returns:
            搜索结果列表
        """
        logger.info(f"🔍 Searching: {query}")

        # 模拟网络延迟
        await asyncio.sleep(0.5)

        # 模拟搜索结果（实际项目中应调用真实搜索引擎 API）
        results = _generate_mock_search_results(query, max_results)

        logger.info(f"📊 Found {len(results)} results")
        return results

    @registry.register(
        name="get_current_weather",
        description="获取指定城市的当前天气信息",
        category="search",
    )
    async def get_current_weather(location: str, unit: str = "celsius") -> Dict[str, Any]:
        """
        模拟获取天气信息

        Args:
            location: 城市名称
            unit: 温度单位，celsius 或 fahrenheit

        Returns:
            天气信息
        """
        logger.info(f"🌤️ Getting weather for: {location}")

        # 模拟网络延迟
        await asyncio.sleep(0.3)

        # 模拟天气数据
        temp_c = random.randint(-5, 35)
        if unit == "fahrenheit":
            temp = temp_c * 9 // 5 + 32
            temp_unit = "°F"
        else:
            temp = temp_c
            temp_unit = "°C"

        conditions = ["晴朗", "多云", "阴天", "小雨", "大雨", "雪", "雾"]
        condition = random.choice(conditions)

        return {
            "location": location,
            "temperature": f"{temp}{temp_unit}",
            "condition": condition,
            "humidity": f"{random.randint(30, 90)}%",
            "wind_speed": f"{random.randint(0, 30)} km/h",
            "updated_at": "2024-01-01 12:00:00",
        }


def _register_datetime(registry: ToolRegistry) -> None:
    """注册日期时间工具"""

    @registry.register(
        name="get_current_time",
        description="获取当前日期和时间",
        category="datetime",
    )
    def get_current_time(format: str = "iso") -> str:
        """
        获取当前时间

        Args:
            format: 时间格式，支持 iso、human、date、time

        Returns:
            格式化的时间字符串
        """
        from datetime import datetime

        now = datetime.now()

        if format == "iso":
            return now.isoformat()
        elif format == "human":
            return now.strftime("%Y年%m月%d日 %H:%M:%S")
        elif format == "date":
            return now.strftime("%Y-%m-%d")
        elif format == "time":
            return now.strftime("%H:%M:%S")
        else:
            return now.strftime(format)


def _generate_mock_search_results(query: str, max_results: int) -> List[Dict[str, Any]]:
    """生成模拟搜索结果"""

    # 知识库数据
    knowledge_base = {
        "法国": {
            "capital": "巴黎 (Paris)",
            "population": "约6700万",
            "language": "法语",
            "currency": "欧元 (EUR)",
        },
        "巴黎": {
            "description": "法国首都，世界著名的艺术、时尚、 gastronomy 和文化中心",
            "landmarks": ["埃菲尔铁塔", "卢浮宫", "凯旋门", "圣母院"],
        },
        "python": {
            "description": "一种高级编程语言，以简洁易读著称",
            "creator": "Guido van Rossum",
            "first_release": "1991年",
        },
        "openai": {
            "description": "一家人工智能研究实验室和公司",
            "products": ["GPT-4", "DALL-E", "ChatGPT", "Whisper"],
            "founded": "2015年",
        },
    }

    results = []

    # 检查知识库
    for key, info in knowledge_base.items():
        if key.lower() in query.lower() or query.lower() in key.lower():
            results.append({
                "title": f"关于 {key} 的信息",
                "url": f"https://example.com/knowledge/{key}",
                "snippet": json.dumps(info, ensure_ascii=False),
                "source": "知识库",
            })

    # 如果没有匹配，生成通用结果
    if not results:
        for i in range(min(max_results, 3)):
            results.append({
                "title": f"搜索结果 {i+1} for '{query}'",
                "url": f"https://example.com/search?q={query}&page={i+1}",
                "snippet": f"这是关于 '{query}' 的模拟搜索结果 {i+1}。在实际应用中，这里会显示真实的搜索结果摘要。",
                "source": "模拟搜索引擎",
            })

    return results[:max_results]


# 创建默认内置工具注册表
builtin_registry = get_builtin_registry()
