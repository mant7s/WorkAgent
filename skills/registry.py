"""WorkAgent Skills 注册表

实现 Skills 技能系统的注册和管理。
支持 Shannon Presets 和 Agent Skills 两种格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 可选依赖
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class Skill:
    """
    技能定义

    基于 Agent Skills 标准设计：
    - name: 技能名称
    - description: 技能描述（用于自动匹配）
    - system_prompt: 系统提示
    - allowed_tools: 工具白名单
    - requires_role: 关联的 Preset 角色
    - budget_max: Token 预算上限
    - dangerous: 是否为危险操作
    """
    name: str
    description: str
    system_prompt: str
    allowed_tools: List[str] = field(default_factory=list)
    requires_role: Optional[str] = None
    budget_max: Optional[int] = None
    dangerous: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_file: Optional[str] = None

    @classmethod
    def from_markdown(cls, file_path: str) -> "Skill":
        """
        从 Markdown 文件解析 Skill

        格式：
        ---
        name: my-skill
        description: 描述
        allowed-tools: Tool1, Tool2
        ---

        ## 指令内容
        ...
        """
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")

        # 解析 frontmatter
        if content.startswith("---") and YAML_AVAILABLE:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
            else:
                frontmatter = {}
                body = content
        else:
            frontmatter = {}
            body = content

        # 解析 allowed-tools
        allowed_tools_str = frontmatter.get("allowed-tools", "")
        allowed_tools = [t.strip() for t in allowed_tools_str.split(",") if t.strip()]

        return cls(
            name=frontmatter.get("name", path.stem),
            description=frontmatter.get("description", ""),
            system_prompt=body,
            allowed_tools=allowed_tools,
            requires_role=frontmatter.get("requires-role"),
            budget_max=frontmatter.get("budget-max"),
            dangerous=frontmatter.get("dangerous", False),
            metadata=frontmatter,
            source_file=file_path,
        )


@dataclass
class Preset:
    """角色预设（简化版，完整实现在 presets.py）"""
    name: str
    system_prompt: str
    allowed_tools: List[str] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096


class SkillRegistry:
    """
    Skills 注册表

    管理所有可用的 Skills，支持：
    1. 从目录加载 Skills
    2. 运行时注册 Skills
    3. 根据查询自动匹配 Skills
    """

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._logger = structlog.get_logger()

    def register(self, skill: Skill) -> None:
        """注册技能"""
        self._skills[skill.name] = skill
        self._logger.debug("skill_registered", name=skill.name, description=skill.description[:50])

    def load_from_directory(self, directory: str) -> int:
        """
        从目录加载所有 Skills

        遍历目录中的所有 .md 文件，解析为 Skill
        """
        path = Path(directory)
        if not path.exists():
            self._logger.warning("skill_directory_not_found", directory=directory)
            return 0

        count = 0
        for file_path in path.rglob("*.md"):
            try:
                skill = Skill.from_markdown(str(file_path))
                self.register(skill)
                count += 1
            except Exception as e:
                self._logger.error("skill_load_failed", file=str(file_path), error=str(e))

        self._logger.info("skills_loaded", directory=directory, count=count)
        return count

    def get(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "allowed_tools": skill.allowed_tools,
                "requires_role": skill.requires_role,
                "dangerous": skill.dangerous,
            }
            for skill in self._skills.values()
        ]

    def find_matching_skills(self, query: str) -> List[Skill]:
        """
        根据查询找到匹配的技能

        简单的关键词匹配，实际可以用 embedding
        """
        query_lower = query.lower()
        matches = []

        for skill in self._skills.values():
            # 检查名称匹配
            if skill.name.lower() in query_lower:
                matches.append(skill)
                continue

            # 检查描述匹配
            if skill.description and any(
                word in skill.description.lower()
                for word in query_lower.split()
            ):
                matches.append(skill)

        return matches

    def apply_skill_to_agent(
        self,
        agent_config: Dict[str, Any],
        skill_name: str,
    ) -> Dict[str, Any]:
        """
        将 Skill 应用到 Agent 配置

        合并 Skill 的配置到 Agent 配置
        """
        skill = self.get(skill_name)
        if not skill:
            self._logger.warning("skill_not_found", name=skill_name)
            return agent_config

        # 合并配置
        config = agent_config.copy()

        # 应用系统提示
        if skill.system_prompt:
            config["system_prompt"] = skill.system_prompt

        # 应用工具白名单
        if skill.allowed_tools:
            config["tools"] = skill.allowed_tools

        # 应用预算限制
        if skill.budget_max:
            config["token_budget"] = min(
                config.get("token_budget", float("inf")),
                skill.budget_max,
            )

        # 应用角色
        if skill.requires_role:
            config["role"] = skill.requires_role

        self._logger.info(
            "skill_applied",
            skill=skill_name,
            role=skill.requires_role,
            tools=skill.allowed_tools,
        )

        return config


# 全局注册表
_global_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """获取全局 Skills 注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry
