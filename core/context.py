"""WorkAgent 上下文工程模块

实现上下文管理、压缩和记忆系统。
基于 Shannon 架构的第 7-8 章设计。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

import structlog

logger = structlog.get_logger()


@dataclass
class ContextConfig:
    """上下文配置"""
    max_tokens: int = 8000  # 上下文窗口上限
    warning_threshold: float = 0.75  # 警告阈值（75%）
    target_compression_ratio: float = 0.5  # 压缩后目标比例
    recent_messages_keep: int = 5  # 保留最近消息数
    primer_messages_keep: int = 3  # 保留开头消息数（Primers）


@dataclass
class Message:
    """消息"""
    role: str  # system, user, assistant, tool
    content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result: Dict[str, Any] = {"role": self.role}
        if self.content:
            result["content"] = self.content
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    def estimate_tokens(self) -> int:
        """估算 token 数"""
        text = self.content or ""
        # 每 4 个字符约 1 个 token + 格式开销
        return len(text) // 4 + 5


class ContextWindow:
    """
    上下文窗口管理器

    实现上下文工程四策略：
    1. Write - 把信息写到上下文之外（通过 MemoryStore）
    2. Select - 把相关信息检索回来（通过语义检索）
    3. Compress - 压缩上下文（三段式保留策略）
    4. Isolate - 隔离上下文（通过子 Agent）
    """

    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self.messages: List[Message] = []
        self.summary: Optional[str] = None  # 压缩后的摘要
        self._logger = structlog.get_logger()

    def add_message(self, message: Message) -> None:
        """添加消息"""
        self.messages.append(message)

        # 检查是否需要压缩
        current_tokens = self.estimate_tokens()
        if current_tokens > self.config.max_tokens * self.config.warning_threshold:
            self._logger.info(
                "context_compression_triggered",
                current_tokens=current_tokens,
                max_tokens=self.config.max_tokens,
            )
            self._compress()

    def estimate_tokens(self) -> int:
        """估算当前上下文 token 数"""
        return sum(msg.estimate_tokens() for msg in self.messages)

    def get_messages(self) -> List[Message]:
        """获取当前上下文消息"""
        return self.messages.copy()

    def _compress(self) -> None:
        """
        三段式保留策略压缩

        1. Primers: 保留开头 N 条（用户最初需求、系统设定）
        2. Summary: 中间部分压缩成摘要
        3. Recents: 保留最近 N 条
        """
        if len(self.messages) <= self.config.primer_messages_keep + self.config.recent_messages_keep:
            return

        # 1. 提取 Primers（开头）
        primers = self.messages[:self.config.primer_messages_keep]

        # 2. 提取 Recents（结尾）
        recents = self.messages[-self.config.recent_messages_keep:]

        # 3. 中间部分生成摘要
        middle_start = self.config.primer_messages_keep
        middle_end = len(self.messages) - self.config.recent_messages_keep
        middle_messages = self.messages[middle_start:middle_end]

        # 生成摘要（简化版，实际应该用 LLM）
        self.summary = self._generate_summary(middle_messages)

        # 重建消息列表
        self.messages = primers + [
            Message(
                role="system",
                content=f"[Previous context summary]: {self.summary}",
                metadata={"is_summary": True},
            )
        ] + recents

        self._logger.info(
            "context_compressed",
            primers=len(primers),
            summary_tokens=len(self.summary) // 4 if self.summary else 0,
            recents=len(recents),
        )

    def _generate_summary(self, messages: List[Message]) -> str:
        """
        生成消息摘要

        简化实现：提取关键信息
        实际生产环境应该用 LLM 生成
        """
        key_points = []

        for msg in messages:
            if msg.role == "user":
                # 提取用户问题
                content = msg.content or ""
                if len(content) > 50:
                    content = content[:50] + "..."
                key_points.append(f"User asked: {content}")

            elif msg.role == "assistant" and msg.tool_calls:
                # 提取工具调用
                for tc in msg.tool_calls:
                    name = tc.get("function", {}).get("name", "unknown")
                    key_points.append(f"Used tool: {name}")

        # 去重并限制长度
        unique_points = list(dict.fromkeys(key_points))
        summary = "; ".join(unique_points[:5])  # 最多 5 个要点

        return summary if summary else "Previous conversation"

    def clear(self) -> None:
        """清空上下文"""
        self.messages.clear()
        self.summary = None


class MemoryItem:
    """记忆条目"""

    def __init__(
        self,
        content: str,
        source: str = "unknown",
        metadata: Optional[Dict] = None,
        score: float = 1.0,
    ):
        self.id = datetime.now().isoformat()
        self.content = content
        self.source = source  # recent, semantic, summary
        self.metadata = metadata or {}
        self.score = score
        self.timestamp = datetime.now()


class MemoryStore(Protocol):
    """记忆存储协议"""

    async def save(self, session_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        """保存记忆"""
        ...

    async def fetch_recent(self, session_id: str, limit: int = 10) -> List[MemoryItem]:
        """获取最近记忆"""
        ...

    async def fetch_semantic(self, query: str, limit: int = 5, threshold: float = 0.7) -> List[MemoryItem]:
        """语义检索"""
        ...

    async def clear(self, session_id: str) -> None:
        """清除会话记忆"""
        ...


class InMemoryStore:
    """内存存储（开发/测试用）"""

    def __init__(self):
        self._store: Dict[str, List[MemoryItem]] = {}
        self._logger = structlog.get_logger()

    async def save(self, session_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        """保存记忆"""
        # 检查是否重复（95% 相似度阈值）
        existing = self._store.get(session_id, [])
        for item in existing:
            similarity = self._calculate_similarity(content, item.content)
            if similarity > 0.95:
                self._logger.debug("memory_duplicate_skipped", similarity=similarity)
                return item.id

        item = MemoryItem(
            content=content,
            source=metadata.get("source", "unknown") if metadata else "unknown",
            metadata=metadata,
        )

        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].append(item)

        self._logger.debug("memory_saved", session_id=session_id, item_id=item.id)
        return item.id

    async def fetch_recent(self, session_id: str, limit: int = 10) -> List[MemoryItem]:
        """获取最近记忆"""
        items = self._store.get(session_id, [])
        # 按时间倒序
        sorted_items = sorted(items, key=lambda x: x.timestamp, reverse=True)
        return sorted_items[:limit]

    async def fetch_semantic(self, query: str, limit: int = 5, threshold: float = 0.7) -> List[MemoryItem]:
        """
        语义检索（简化版）

        实际生产环境应该使用向量数据库和 Embedding
        """
        results = []
        query_lower = query.lower()

        # 简单的关键词匹配作为演示
        for session_id, items in self._store.items():
            for item in items:
                # 计算简单相似度（关键词匹配）
                score = self._calculate_similarity(query_lower, item.content.lower())
                if score >= threshold:
                    item.score = score
                    results.append(item)

        # 按相似度排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    async def clear(self, session_id: str) -> None:
        """清除会话记忆"""
        if session_id in self._store:
            del self._store[session_id]

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简化版）"""
        # 使用 Jaccard 相似度
        set1 = set(text1.split())
        set2 = set(text2.split())

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0


class HierarchicalMemory:
    """
    分层记忆系统

    三层融合：
    1. Recent - 最近记忆（保持对话连贯）
    2. Semantic - 语义相关（找历史中相关的）
    3. Summary - 摘要（快速了解长期上下文）
    """

    def __init__(self, store: MemoryStore):
        self.store = store
        self._logger = structlog.get_logger()

    async def fetch(
        self,
        query: str,
        session_id: str,
        recent_k: int = 5,
        semantic_k: int = 3,
        max_total: int = 10,
    ) -> List[MemoryItem]:
        """
        分层获取记忆

        Args:
            query: 查询内容
            session_id: 会话 ID
            recent_k: 最近记忆数量
            semantic_k: 语义相关记忆数量
            max_total: 返回总数上限
        """
        seen_ids = set()
        results = []

        # 1. 最近记忆
        recent = await self.store.fetch_recent(session_id, recent_k)
        for item in recent:
            if item.id not in seen_ids:
                item.source = "recent"
                seen_ids.add(item.id)
                results.append(item)

        self._logger.debug("memory_fetched_recent", count=len(recent))

        # 2. 语义记忆
        semantic = await self.store.fetch_semantic(query, semantic_k)
        for item in semantic:
            if item.id not in seen_ids:
                item.source = "semantic"
                seen_ids.add(item.id)
                results.append(item)

        self._logger.debug("memory_fetched_semantic", count=len(semantic))

        # 限制总数
        if len(results) > max_total:
            results = results[:max_total]

        self._logger.info(
            "memory_fetched_total",
            total=len(results),
            recent=len(recent),
            semantic=len(semantic),
        )

        return results


class ContextManager:
    """
    上下文管理器

    整合 ContextWindow 和 HierarchicalMemory，提供统一的上下文管理接口。
    """

    def __init__(
        self,
        config: Optional[ContextConfig] = None,
        memory_store: Optional[MemoryStore] = None,
    ):
        self.config = config or ContextConfig()
        self.context_window = ContextWindow(self.config)
        self.memory = HierarchicalMemory(memory_store or InMemoryStore())
        self._logger = structlog.get_logger()

    async def build_context(
        self,
        query: str,
        session_id: str,
        system_prompt: str,
    ) -> List[Dict[str, Any]]:
        """
        构建完整上下文

        包含：
        1. System Prompt
        2. 相关记忆（从分层记忆系统获取）
        3. 当前对话历史（从 ContextWindow 获取）
        4. 用户查询
        """
        messages: List[Dict[str, Any]] = []

        # 1. System Prompt
        messages.append({"role": "system", "content": system_prompt})

        # 2. 获取相关记忆
        memories = await self.memory.fetch(query, session_id)
        if memories:
            memory_content = "\n".join([f"- {m.content}" for m in memories[:3]])
            messages.append({
                "role": "system",
                "content": f"Relevant context from previous conversations:\n{memory_content}",
            })

        # 3. 当前对话历史
        for msg in self.context_window.get_messages():
            messages.append(msg.to_dict())

        # 4. 用户查询
        messages.append({"role": "user", "content": query})

        return messages

    def add_message(self, message: Message) -> None:
        """添加消息到上下文窗口"""
        self.context_window.add_message(message)

    async def save_to_memory(self, session_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        """保存到长期记忆"""
        return await self.memory.store.save(session_id, content, metadata)

    def clear_context(self) -> None:
        """清空当前上下文"""
        self.context_window.clear()
