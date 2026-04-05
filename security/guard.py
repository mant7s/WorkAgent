"""PromptGuard - Prompt 安全过滤器

基于轻量级 Agent 框架 v2 设计文档第 5.2 节实现：
- 危险模式检测
- PII 脱敏
- 轻量级替代 OPA，使用 Python 实现核心安全策略
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Pattern, Set

import structlog

from config import get_config

logger = structlog.get_logger(__name__)


class PIIPattern(Enum):
    """PII 敏感信息模式"""

    EMAIL = (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "EMAIL_REDACTED")
    PHONE = (r'\b(?:\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b', "PHONE_REDACTED")
    CREDIT_CARD = (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', "CREDIT_CARD_REDACTED")
    SSN = (r'\b\d{3}-\d{2}-\d{4}\b', "SSN_REDACTED")
    IP_ADDRESS = (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', "IP_REDACTED")

    def __init__(self, pattern: str, replacement: str):
        self.pattern = pattern
        self.replacement = replacement


@dataclass
class GuardResult:
    """安全检查结果

    Attributes:
        allowed: 是否允许通过
        reason: 拒绝原因（如果 allowed 为 False）
        risk_score: 风险评分（0.0 - 1.0）
        detected_patterns: 检测到的危险模式
        pii_detected: 检测到的 PII 类型列表
        sanitized_prompt: 脱敏后的提示词
    """

    allowed: bool = True
    reason: Optional[str] = None
    risk_score: float = 0.0
    detected_patterns: List[str] = None
    pii_detected: List[str] = None
    sanitized_prompt: Optional[str] = None

    def __post_init__(self):
        if self.detected_patterns is None:
            self.detected_patterns = []
        if self.pii_detected is None:
            self.pii_detected = []


class PromptInjectionError(Exception):
    """Prompt 注入攻击检测错误"""

    pass


class PromptGuard:
    """Prompt 安全过滤器

    轻量级替代 OPA，使用 Python 实现核心安全策略。

    功能：
    1. 危险模式检测（Prompt 注入攻击）
    2. PII 敏感信息检测和脱敏
    3. 长度限制检查
    4. 自定义关键词过滤

    Example:
        >>> config = {
        ...     "max_prompt_length": 10000,
        ...     "blocked_keywords": ["delete all", "drop table"],
        ...     "enable_pii_detection": True,
        ... }
        >>> guard = PromptGuard(config)
        >>>
        >>> result = guard.check("What is the weather today?")
        >>> if result.allowed:
        ...     print("Prompt is safe")
        ... else:
        ...     print(f"Blocked: {result.reason}")
        >>>
        >>> # 脱敏
        >>> sanitized = guard.sanitize("Contact me at user@example.com")
        >>> print(sanitized)  # "Contact me at [EMAIL_REDACTED]"
    """

    # 危险模式 - Prompt 注入攻击检测
    DANGEROUS_PATTERNS: List[tuple] = [
        (r'ignore\s+previous\s+instructions', "ignore_previous_instructions"),
        (r'ignore\s+all\s+(?:prior\s+)?instructions', "ignore_all_instructions"),
        (r'disregard\s+all\s+prior', "disregard_prior"),
        (r'system\s*:\s*you\s+are\s+now', "system_override"),
        (r'\[system\s+override\]', "system_override_bracket"),
        (r'admin\s*:\s*', "admin_impersonation"),
        (r'you\s+are\s+now\s+(?:a\s+)?(?:developer|admin|system)', "role_override"),
        (r'forget\s+(?:everything|all)\s+(?:you\s+)?(?:were\s+)?told', "forget_instructions"),
        (r'delete\s+all', "delete_all"),
        (r'drop\s+table', "drop_table"),
        (r'rm\s+-rf', "rm_rf"),
        (r'format\s+(?:your|the)\s+(?:hard\s+)?drive', "format_drive"),
        (r'sudo\s+', "sudo_command"),
        (r'exec\s*\(', "code_execution"),
        (r'eval\s*\(', "code_evaluation"),
        (r'<script', "xss_attempt"),
        (r'javascript:', "javascript_protocol"),
        (r'on\w+\s*=', "event_handler"),
        (r'document\.cookie', "cookie_access"),
        (r'localstorage', "localstorage_access"),
        (r'sessionstorage', "sessionstorage_access"),
        (r'new\s+function', "dynamic_function"),
        (r'function\s*\(\s*\)\s*{', "anonymous_function"),
        (r'__proto__', "prototype_pollution"),
        (r'constructor', "constructor_access"),
    ]

    def __init__(self, config: Optional[Dict] = None):
        """初始化 PromptGuard

        Args:
            config: 配置字典（可选，默认从配置文件加载）
                - max_prompt_length: 最大提示词长度
                - blocked_keywords: 自定义屏蔽关键词列表
                - enable_pii_detection: 是否启用 PII 检测
                - enable_dangerous_detection: 是否启用危险模式检测
                - custom_patterns: 自定义正则模式列表
        """
        # 从应用配置加载默认设置
        app_config = get_config()
        
        # 合并配置：传入的配置优先于应用配置
        self.config = config or {}
        self.max_length = self.config.get(
            "max_prompt_length",
            app_config.security.max_prompt_length
        )
        self.blocked_keywords: Set[str] = set(
            kw.lower() for kw in self.config.get(
                "blocked_keywords",
                app_config.security.blocked_keywords
            )
        )
        self.enable_pii = self.config.get(
            "enable_pii_detection",
            app_config.security.pii_redaction_enabled
        )
        self.enable_dangerous = self.config.get(
            "enable_dangerous_detection",
            app_config.security.prompt_guard_enabled
        )

        # 编译正则表达式
        self._dangerous_patterns: List[tuple] = []
        if self.enable_dangerous:
            for pattern, name in self.DANGEROUS_PATTERNS:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    self._dangerous_patterns.append((compiled, name))
                except re.error as e:
                    logger.warning("Failed to compile pattern", pattern=pattern, error=str(e))

        # 自定义模式
        for pattern_dict in self.config.get("custom_patterns", []):
            try:
                compiled = re.compile(pattern_dict["pattern"], re.IGNORECASE)
                self._dangerous_patterns.append((compiled, pattern_dict.get("name", "custom")))
            except re.error as e:
                logger.warning("Failed to compile custom pattern", error=str(e))

        logger.info(
            "prompt_guard.initialized",
            max_length=self.max_length,
            blocked_keywords=len(self.blocked_keywords),
            dangerous_patterns=len(self._dangerous_patterns),
            enable_pii=self.enable_pii,
        )

    def check(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> GuardResult:
        """检查 Prompt 安全性

        Args:
            prompt: 输入提示词
            user_id: 用户 ID（用于日志）
            context: 上下文信息

        Returns:
            GuardResult: 检查结果
        """
        result = GuardResult(allowed=True)
        risk_score = 0.0

        # 长度检查
        if len(prompt) > self.max_length:
            result.allowed = False
            result.reason = f"Prompt too long: {len(prompt)} > {self.max_length}"
            result.risk_score = 1.0

            logger.warning(
                "prompt_guard.length_exceeded",
                user_id=user_id,
                length=len(prompt),
                max_length=self.max_length,
            )
            return result

        prompt_lower = prompt.lower()

        # 检查危险模式
        if self.enable_dangerous:
            for pattern, name in self._dangerous_patterns:
                if pattern.search(prompt):
                    result.allowed = False
                    result.reason = f"Potential prompt injection detected: {name}"
                    result.risk_score = 0.9
                    result.detected_patterns.append(name)

                    logger.warning(
                        "prompt_guard.injection_detected",
                        user_id=user_id,
                        pattern=name,
                        prompt_preview=prompt[:100],
                    )
                    return result

        # 检查敏感信息
        if self.enable_pii:
            pii_detected = self._detect_pii(prompt)
            if pii_detected:
                result.pii_detected = pii_detected
                risk_score += len(pii_detected) * 0.2

                logger.info(
                    "prompt_guard.pii_detected",
                    user_id=user_id,
                    pii_types=pii_detected,
                )

        # 检查自定义关键词
        for keyword in self.blocked_keywords:
            if keyword in prompt_lower:
                result.allowed = False
                result.reason = f"Blocked keyword detected: {keyword}"
                result.risk_score = 0.8

                logger.warning(
                    "prompt_guard.blocked_keyword",
                    user_id=user_id,
                    keyword=keyword,
                )
                return result

        # 计算最终风险评分
        result.risk_score = min(risk_score, 1.0)

        # 如果允许通过，提供脱敏版本
        if result.allowed and result.pii_detected:
            result.sanitized_prompt = self.sanitize(prompt)

        logger.debug(
            "prompt_guard.check_completed",
            user_id=user_id,
            allowed=result.allowed,
            risk_score=result.risk_score,
        )

        return result

    def _detect_pii(self, text: str) -> List[str]:
        """检测 PII 信息

        Args:
            text: 输入文本

        Returns:
            List[str]: 检测到的 PII 类型列表
        """
        detected = []
        for pii_type in PIIPattern:
            if re.search(pii_type.pattern, text):
                detected.append(pii_type.name)
        return detected

    def sanitize(self, text: str) -> str:
        """脱敏处理

        将检测到的 PII 信息替换为占位符。

        Args:
            text: 输入文本

        Returns:
            str: 脱敏后的文本
        """
        result = text
        for pii_type in PIIPattern:
            result = re.sub(pii_type.pattern, f"[{pii_type.replacement}]", result)
        return result

    def validate_and_raise(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> str:
        """验证并抛出异常（如果不通过）

        Args:
            prompt: 输入提示词
            user_id: 用户 ID
            context: 上下文信息

        Returns:
            str: 脱敏后的提示词（如果通过）

        Raises:
            PromptInjectionError: 如果检查不通过
        """
        result = self.check(prompt, user_id, context)

        if not result.allowed:
            raise PromptInjectionError(result.reason or "Prompt rejected by guard")

        return result.sanitized_prompt or prompt

    def add_blocked_keyword(self, keyword: str) -> None:
        """添加屏蔽关键词

        Args:
            keyword: 要屏蔽的关键词
        """
        self.blocked_keywords.add(keyword.lower())
        logger.info("prompt_guard.keyword_added", keyword=keyword)

    def remove_blocked_keyword(self, keyword: str) -> None:
        """移除屏蔽关键词

        Args:
            keyword: 要移除的关键词
        """
        self.blocked_keywords.discard(keyword.lower())
        logger.info("prompt_guard.keyword_removed", keyword=keyword)

    def get_stats(self) -> Dict[str, any]:
        """获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "max_length": self.max_length,
            "blocked_keywords_count": len(self.blocked_keywords),
            "dangerous_patterns_count": len(self._dangerous_patterns),
            "enable_pii_detection": self.enable_pii,
            "enable_dangerous_detection": self.enable_dangerous,
            "blocked_keywords": list(self.blocked_keywords),
        }


# FastAPI 中间件示例（用于文档）
async def prompt_guard_middleware_factory(guard: PromptGuard):
    """创建 FastAPI 中间件的工厂函数

    Example:
        >>> from fastapi import FastAPI, Request, JSONResponse
        >>> app = FastAPI()
        >>> guard = PromptGuard()
        >>>
        >>> @app.middleware("http")
        >>> async def prompt_guard_middleware(request: Request, call_next):
        ...     if request.url.path == "/agent/run":
        ...         body = await request.json()
        ...         prompt = body.get("query", "")
        ...
        ...         result = guard.check(prompt, user_id=request.headers.get("x-user-id"))
        ...
        ...         if not result.allowed:
        ...             return JSONResponse(
        ...                 status_code=400,
        ...                 content={"error": "Prompt rejected", "reason": result.reason}
        ...             )
        ...
        ...         # 脱敏
        ...         if result.sanitized_prompt:
        ...             body["query"] = result.sanitized_prompt
        ...
        ...     response = await call_next(request)
        ...     return response
    """
    # 这是一个文档示例，实际使用时需要集成到 FastAPI 应用中
    pass
