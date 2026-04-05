"""WorkAgent Skills 技能系统

基于 Shannon 架构的第 5 章设计。
实现 Presets 角色预设和 Skills 技能配置。
"""

from .registry import SkillRegistry, Preset, Skill
from .presets import get_preset, list_presets, PRESETS

__all__ = [
    "SkillRegistry",
    "Preset",
    "Skill",
    "get_preset",
    "list_presets",
    "PRESETS",
]
