"""WorkAgent LLM 路由"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from config import get_config
from core.types import LLMError, TokenUsage
from .providers.openai import OpenAIProvider

logger = structlog.get_logger()


@dataclass
class LLMResponse:
    """LLM 响应统一格式"""
    content: str
    tool_calls: List[Dict[str, Any]]
    usage: TokenUsage
    model: str
    raw_response: Optional[Dict[str, Any]] = None


class LLMRouter:
    """
    LLM 路由器

    职责：
    1. 多模型提供商管理
    2. 统一的 chat 接口
    3. Token 使用统计
    4. 简单的模型选择逻辑
    """

    def __init__(self, config=None):
        self._providers: Dict[str, OpenAIProvider] = {}
        self._default_provider: Optional[str] = None
        self._logger = structlog.get_logger()
        self._total_usage = TokenUsage()
        self._config = config or get_config()

    def register_provider(
        self,
        name: str,
        provider: OpenAIProvider,
        default: bool = False,
    ) -> "LLMRouter":
        """
        注册 LLM 提供商

        Args:
            name: 提供商名称
            provider: 提供商实例
            default: 是否设为默认
        """
        self._providers[name] = provider

        if default or self._default_provider is None:
            self._default_provider = name

        self._logger.info(
            "provider_registered",
            name=name,
            default=default,
        )
        return self

    def create_default(self) -> "LLMRouter":
        """创建默认配置（从配置文件加载）"""
        # 从配置文件加载模型配置
        default_model_name = self._config.get_default_model()
        
        for name, model_config in self._config.models.items():
            if model_config.provider == "openai":
                provider = OpenAIProvider(
                    api_key=model_config.api_key,
                    base_url=model_config.base_url,
                )
                if provider.is_available():
                    # 使用配置中的 default 字段或第一个模型作为默认
                    is_default = model_config.default or (name == default_model_name)
                    self.register_provider(name, provider, default=is_default)

        # 如果没有配置，尝试创建默认 OpenAI 提供商
        if not self._providers:
            openai_provider = OpenAIProvider()
            if openai_provider.is_available():
                self.register_provider("openai", openai_provider, default=True)

        return self

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        provider: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        统一的 chat 接口

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            tools: 工具定义
            provider: 指定提供商
            **kwargs: 额外参数

        Returns:
            LLMResponse 对象
        """
        # 选择提供商
        provider_name = provider or self._default_provider
        if not provider_name:
            raise LLMError("No LLM provider available")

        if provider_name not in self._providers:
            raise LLMError(f"Provider not found: {provider_name}")

        llm_provider = self._providers[provider_name]

        self._logger.debug(
            "llm_chat_request",
            provider=provider_name,
            model=model or "default",
            message_count=len(messages),
        )

        try:
            # 调用提供商
            response = await llm_provider.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                tools=tools,
                **kwargs,
            )

            # 转换为统一格式
            result = LLMResponse(
                content=response.content,
                tool_calls=response.get_tool_calls(),
                usage=response.usage,
                model=response.model or model or "unknown",
                raw_response=response.raw_response,
            )

            # 更新统计
            self._total_usage += result.usage

            self._logger.debug(
                "llm_chat_response",
                provider=provider_name,
                model=result.model,
                tokens_used=result.usage.total_tokens,
                has_tool_calls=len(result.tool_calls) > 0,
            )

            return result

        except Exception as e:
            self._logger.error(
                "llm_chat_error",
                provider=provider_name,
                error=str(e),
            )
            raise

    def get_usage_stats(self) -> TokenUsage:
        """获取 Token 使用统计"""
        return self._total_usage

    def reset_usage_stats(self) -> None:
        """重置 Token 使用统计"""
        self._total_usage = TokenUsage()

    def list_providers(self) -> List[str]:
        """列出所有可用提供商"""
        return list(self._providers.keys())

    def get_default_provider(self) -> Optional[str]:
        """获取默认提供商名称"""
        return self._default_provider
