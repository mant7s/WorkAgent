"""WorkAgent OpenAI Provider"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
import structlog

from core.types import LLMError, TokenUsage

logger = structlog.get_logger()


class OpenAIProvider:
    """
    OpenAI API 提供商

    特性：
    1. 支持 chat.completions API
    2. 支持 Function Calling
    3. Token 使用统计
    4. 异步调用
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.default_model = model
        self.timeout = timeout
        self._logger = structlog.get_logger()

        if not self.api_key:
            logger.warning("OpenAI API key not provided")

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        max_tokens: Optional[int] = None,
    ) -> "OpenAIResponse":
        """
        调用 OpenAI Chat Completion API

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            tools: 工具定义列表
            tool_choice: 工具选择策略
            max_tokens: 最大生成 token 数

        Returns:
            OpenAIResponse 对象
        """
        model = model or self.default_model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        if max_tokens:
            payload["max_tokens"] = max_tokens

        self._logger.debug(
            "openai_request",
            model=model,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as e:
            self._logger.error(
                "openai_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise LLMError(f"OpenAI API error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            self._logger.error("openai_request_error", error=str(e))
            raise LLMError(f"OpenAI request failed: {e}") from e

        # 解析响应
        result = OpenAIResponse.from_api_response(data)

        self._logger.debug(
            "openai_response",
            model=model,
            tokens_used=result.usage.total_tokens if result.usage else 0,
            has_tool_calls=len(result.tool_calls) > 0,
        )

        return result

    def is_available(self) -> bool:
        """检查 Provider 是否可用"""
        return bool(self.api_key)


class OpenAIResponse:
    """OpenAI API 响应封装"""

    def __init__(
        self,
        content: Optional[str],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[TokenUsage] = None,
        model: Optional[str] = None,
        raw_response: Optional[Dict[str, Any]] = None,
    ):
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.usage = usage or TokenUsage()
        self.model = model
        self.raw_response = raw_response or {}

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "OpenAIResponse":
        """从 API 响应创建对象"""
        choice = data["choices"][0]
        message = choice["message"]

        content = message.get("content")
        tool_calls = message.get("tool_calls", [])
        model = data.get("model")

        # 解析 usage
        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return cls(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=model,
            raw_response=data,
        )

    def has_tool_calls(self) -> bool:
        """检查是否有工具调用"""
        return len(self.tool_calls) > 0

    def get_tool_calls(self) -> List[Dict[str, Any]]:
        """获取工具调用列表"""
        result = []
        for tc in self.tool_calls:
            if tc["type"] == "function":
                func = tc["function"]
                result.append({
                    "id": tc.get("id"),
                    "name": func["name"],
                    "arguments": func["arguments"],
                })
        return result
