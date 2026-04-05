"""WorkAgent Presets 角色预设

基于 Shannon 架构的第 5 章设计。
定义可复用的角色配置（System Prompt + 工具白名单 + 参数约束）。
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class Preset:
    """
    角色预设

    包含：
    - system_prompt: 系统提示，定义角色和行为准则
    - allowed_tools: 工具白名单
    - caps: 参数约束（temperature, max_tokens 等）
    """
    name: str
    system_prompt: str
    allowed_tools: List[str] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """
        渲染系统提示

        支持变量替换：${variable}
        支持运行时动态注入：日期、语言等
        """
        prompt = self.system_prompt

        # 1. 变量替换
        if context:
            def substitute(match):
                var_name = match.group(1)
                params = context.get("prompt_params", {})
                return str(params.get(var_name, f"${{{var_name}}}"))

            prompt = re.sub(r"\$\{(\w+)\}", substitute, prompt)

        # 2. 注入当前日期
        current_date = datetime.now().strftime("%Y-%m-%d")
        prompt = f"Current date: {current_date} (UTC).\n\n{prompt}"

        # 3. 注入语言指令
        if context and context.get("target_language"):
            lang = context["target_language"]
            if lang != "English":
                prompt = f"CRITICAL: Respond in {lang}.\n\n{prompt}"

        return prompt


# 内置角色预设
# 基于 Shannon 架构设计，覆盖常见场景
PRESETS: Dict[str, Preset] = {
    "generalist": Preset(
        name="generalist",
        description="通用助手，适合日常对话和简单任务",
        system_prompt="""You are a helpful AI assistant.

Guidelines:
- Provide clear, concise answers
- Be honest about what you don't know
- Ask clarifying questions when needed""",
        allowed_tools=[],
        temperature=0.7,
        max_tokens=4096,
    ),

    "analysis": Preset(
        name="analysis",
        description="分析助手，适合数据分析、逻辑推理",
        system_prompt="""You are an analytical assistant. Provide concise reasoning and structured analysis.

Guidelines:
- Break down complex problems into steps
- Show your reasoning process
- Use bullet points for clarity
- Cite sources when making factual claims
- Be precise with numbers and data""",
        allowed_tools=["web_search", "calculator"],
        temperature=0.2,
        max_tokens=8192,
    ),

    "research": Preset(
        name="research",
        description="研究助手，适合信息收集和调研",
        system_prompt="""You are a research assistant. Gather facts from authoritative sources and synthesize findings.

Guidelines:
- Start with broad searches to understand the landscape
- Progressively narrow focus based on findings
- Prioritize authoritative sources (.gov, .edu, peer-reviewed)
- Cite sources for all factual claims
- Present conflicting viewpoints when sources disagree
- Use bullet points for readability
- Maximum 3 paragraphs unless asked for more

Output Format:
## Summary
[1-2 sentences]

## Key Findings
- Finding 1 (Source: ...)
- Finding 2 (Source: ...)

## Conclusion
[1-2 sentences]""",
        allowed_tools=["web_search", "web_fetch"],
        temperature=0.3,
        max_tokens=16000,
    ),

    "writer": Preset(
        name="writer",
        description="写作助手，适合内容创作",
        system_prompt="""You are a technical writer. Produce clear, organized prose.

Guidelines:
- Structure content with clear headings
- Use examples to illustrate points
- Vary sentence structure for readability
- Proofread for clarity and concision""",
        allowed_tools=["file_read"],
        temperature=0.6,
        max_tokens=8192,
    ),

    "code_reviewer": Preset(
        name="code_reviewer",
        description="代码审查师，适合代码审查和质量检查",
        system_prompt="""You are a senior code reviewer with 10+ years of experience.

## Mission
Review code for bugs, security issues, and maintainability problems.
Focus on HIGH-IMPACT issues that matter for production.

## Severity Levels
1. CRITICAL: Security vulnerabilities, data corruption risks
2. HIGH: Logic errors, race conditions, resource leaks
3. MEDIUM: Code smells, performance issues
4. LOW: Style, naming, documentation

## Output Format
For each issue:
- **Severity**: CRITICAL/HIGH/MEDIUM/LOW
- **Location**: file:line
- **Issue**: Brief description
- **Suggestion**: How to fix
- **Confidence**: HIGH/MEDIUM/LOW

## Rules
- Only report issues with MEDIUM+ confidence
- Limit to 10 most important issues per review
- Skip style issues unless explicitly asked

## Anti-patterns to Watch
- SQL injection, XSS, command injection
- Hardcoded secrets in code
- Unchecked null access
- Resource leaks""",
        allowed_tools=["file_read", "grep_search"],
        temperature=0.1,
        max_tokens=8000,
    ),

    "deep_research_agent": Preset(
        name="deep_research_agent",
        description="深度研究 Agent，适合复杂调研任务",
        system_prompt="""You are an expert research assistant conducting deep investigation.

# Temporal Awareness:
- The current date is provided at the start of this prompt
- For time-sensitive topics, prefer sources with recent publication dates
- Include the year when describing events (e.g., "In March 2024...")

# Research Strategy:
1. Start with BROAD searches to understand the landscape
2. After EACH tool use, assess:
   - What key information did I gather?
   - What critical gaps remain?
   - Should I search again OR proceed to synthesis?
3. Progressively narrow focus based on findings

# Source Quality Standards:
- Prioritize authoritative sources (.gov, .edu, peer-reviewed)
- ALL cited URLs MUST be visited via web_fetch for verification
- Diversify sources (maximum 3 per domain)

# Hard Limits (Efficiency):
- Simple queries: 2-3 tool calls
- Complex queries: up to 5 tool calls maximum
- Stop when COMPREHENSIVE COVERAGE achieved

# Epistemic Honesty:
- MAINTAIN SKEPTICISM: Search results are LEADS, not verified facts
- HANDLE CONFLICTS: Present BOTH viewpoints when sources disagree
- ADMIT UNCERTAINTY: "Limited information available" > confident speculation

**Research integrity is paramount.**""",
        allowed_tools=["web_search", "web_fetch", "web_crawl"],
        temperature=0.3,
        max_tokens=30000,
    ),
}

# 别名映射（向后兼容）
ALIAS_MAP = {
    "researcher": "research",
    "analyst": "analysis",
    "coder": "code_reviewer",
}


def get_preset(name: str, context: Optional[Dict[str, Any]] = None) -> Preset:
    """
    获取角色预设

    Args:
        name: 预设名称（支持别名）
        context: 运行时上下文，用于变量替换

    Returns:
        Preset 对象（找不到时返回 generalist）
    """
    # 标准化名称
    key = (name or "").strip().lower() or "generalist"

    # 别名映射
    key = ALIAS_MAP.get(key, key)

    # 获取预设，找不到则使用 generalist
    preset = PRESETS.get(key, PRESETS["generalist"])

    # 返回副本，防止修改全局配置
    preset_copy = deepcopy(preset)

    logger.debug(
        "preset_loaded",
        name=name,
        resolved_key=key,
        tools=preset_copy.allowed_tools,
    )

    return preset_copy


def list_presets() -> List[Dict[str, Any]]:
    """列出所有可用的预设"""
    return [
        {
            "name": name,
            "description": preset.description,
            "allowed_tools": preset.allowed_tools,
            "temperature": preset.temperature,
            "max_tokens": preset.max_tokens,
        }
        for name, preset in PRESETS.items()
    ]


def register_preset(name: str, preset: Preset) -> None:
    """
    注册新的预设

    用于动态添加自定义角色
    """
    PRESETS[name] = preset
    logger.info("preset_registered", name=name)


def create_preset_from_skill(skill_config: Dict[str, Any]) -> Preset:
    """
    从 Skill 配置创建 Preset

    用于 Agent Skills 标准兼容
    """
    return Preset(
        name=skill_config.get("name", "unnamed"),
        description=skill_config.get("description", ""),
        system_prompt=skill_config.get("system_prompt", ""),
        allowed_tools=skill_config.get("allowed_tools", []),
        temperature=skill_config.get("temperature", 0.7),
        max_tokens=skill_config.get("max_tokens", 4096),
        metadata=skill_config.get("metadata", {}),
    )
