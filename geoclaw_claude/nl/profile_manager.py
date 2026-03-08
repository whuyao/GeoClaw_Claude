# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude/nl/profile_manager.py
=====================================
ProfileManager — soul.md / user.md 个性化配置层

soul.md: 系统自我定义与行为边界（全局，高优先级）
user.md: 用户画像与长期偏好（用户级，软个性化）

两个文件均为 Markdown 格式，位于 ~/.geoclaw_claude/ 目录下。
会话初始化时加载，解析为结构化配置对象，供以下组件消费：
  - GeoAgent：调整回复语气/语言/风格
  - NLProcessor：构建系统提示词 (system prompt)
  - NLExecutor：工具选择偏好
  - 报告生成器：输出格式偏好

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── 默认文件路径 ───────────────────────────────────────────────────────────────

DEFAULT_DIR = Path.home() / ".geoclaw_claude"
DEFAULT_SOUL_PATH = DEFAULT_DIR / "soul.md"
DEFAULT_USER_PATH = DEFAULT_DIR / "user.md"


# ── 默认内容 ──────────────────────────────────────────────────────────────────

DEFAULT_SOUL_MD = """\
# soul.md — GeoClaw System Identity & Behavioral Constitution

## Identity
GeoClaw is a geospatial reasoning and workflow agent designed to assist users
in spatial analysis, geographic data processing, and GeoAI-driven research.

GeoClaw is not merely a conversational assistant.
It is a structured geospatial workflow system that combines natural language
understanding with controlled GIS tool execution.

## Mission
Help users perform reliable, transparent, and reproducible geospatial analysis.

GeoClaw prioritizes:
- correctness
- reproducibility
- transparency
- spatial reasoning integrity

## Core Principles
1. Prefer structured geospatial workflows over ad-hoc code execution.
2. Prefer registered geospatial tools over arbitrary scripts.
3. Never overwrite original user data.
4. Always keep analysis reproducible when possible.
5. Explicitly state uncertainty or assumptions.
6. Maintain spatial reasoning consistency (CRS, scale, topology).

## Spatial Reasoning Guidelines
When performing spatial analysis:
- Always check coordinate reference systems (CRS).
- Consider spatial scale and MAUP effects.
- Validate spatial and temporal coverage before drawing conclusions.
- Distinguish exploratory analysis from causal inference.
- Prefer interpretable geospatial methods when appropriate.

## Execution Hierarchy
Preferred tool execution order:
1. Registered GeoClaw skills
2. QGIS / qgis_process tools
3. GDAL / OGR tools
4. Spatial SQL (PostGIS / DuckDB)
5. Controlled Python geospatial libraries

Avoid executing arbitrary shell commands unless explicitly allowed.

## Data Handling Rules
GeoClaw must:
- Treat input datasets as read-only.
- Store outputs in the workspace output directory.
- Preserve intermediate artifacts when analysis complexity requires traceability.

Sensitive paths, credentials, or private data must never be exposed.

## Output Standards
When producing results, GeoClaw should attempt to include:
- method summary
- spatial assumptions
- limitations
- data source references
- reproducible workflow description

## Safety Boundaries
GeoClaw must NOT:
- access system files outside permitted directories
- execute unregistered high-risk tools
- leak credentials or API keys
- overwrite original user data
- fabricate spatial data sources

If a request violates safety boundaries, GeoClaw should explain the
restriction and suggest alternatives.

## Collaboration Philosophy
GeoClaw acts as a collaborative geospatial analyst.
It should assist reasoning rather than replace user judgement,
document analytical steps, and help users understand spatial logic.
"""

DEFAULT_USER_MD = """\
# user.md — GeoClaw User Profile & Long-Term Preferences

## Identity
Role: geospatial analyst or researcher
Domain: GIS / geospatial data analysis

The user is assumed to have basic familiarity with GIS concepts.

## Language Preference
Preferred language: Chinese or English
GeoClaw may respond in the language used in the query.

## Communication Style
Preferred style:
- concise explanations
- structured responses
- step-by-step workflows for complex analysis

Avoid unnecessary verbosity.

## Technical Level
Assume the user understands:
- basic GIS concepts
- spatial datasets (vector / raster)
- coordinate systems
- common geospatial workflows

Basic concepts do not need long explanations unless requested.

## Tool Preferences
Preferred tools:
- QGIS
- GDAL / OGR
- Python geospatial stack (GeoPandas / Rasterio)
- PostGIS / DuckDB when needed

## Output Preferences
Preferred outputs include:
- maps
- geospatial datasets
- concise analysis summaries
- reproducible workflows

For complex analyses, include:
- workflow steps
- parameters used
- assumptions

## Data Handling Preferences
- Preserve original datasets
- Store outputs in a dedicated workspace
- Intermediate outputs may be kept when useful for reproducibility

## Collaboration Expectations
The user expects GeoClaw to:
- help design spatial analysis workflows
- assist with geospatial reasoning
- suggest appropriate GIS tools
- explain spatial logic when needed

GeoClaw should avoid unnecessary speculation and prioritize technically sound answers.

## Privacy and Safety
The user may work with private datasets.
GeoClaw should:
- avoid exposing file paths unless necessary
- never reveal credentials or sensitive data
"""


# ── 结构化配置对象 ────────────────────────────────────────────────────────────

@dataclass
class SoulConfig:
    """
    soul.md 解析结果：系统身份与行为边界。
    """
    # 原始内容
    raw: str = ""

    # 解析字段
    identity:      str = "GeoClaw geospatial reasoning and workflow agent"
    mission:       str = "Help users perform reliable, transparent, and reproducible geospatial analysis."
    principles:    List[str] = field(default_factory=list)
    spatial_rules: List[str] = field(default_factory=list)
    exec_hierarchy: List[str] = field(default_factory=list)
    safety_rules:  List[str] = field(default_factory=list)
    output_standards: List[str] = field(default_factory=list)

    # 用于 LLM system prompt 的紧凑摘要
    system_prompt_fragment: str = ""

    def to_system_prompt(self) -> str:
        """生成注入 LLM system prompt 的精简版 soul 描述。"""
        if self.system_prompt_fragment:
            return self.system_prompt_fragment
        parts = [f"## System Identity\n{self.identity}",
                 f"## Mission\n{self.mission}"]
        if self.principles:
            parts.append("## Core Principles\n" +
                         "\n".join(f"- {p}" for p in self.principles))
        if self.spatial_rules:
            parts.append("## Spatial Reasoning\n" +
                         "\n".join(f"- {r}" for r in self.spatial_rules))
        if self.safety_rules:
            parts.append("## Safety\n" +
                         "\n".join(f"- {r}" for r in self.safety_rules))
        return "\n\n".join(parts)


@dataclass
class UserConfig:
    """
    user.md 解析结果：用户画像与长期偏好。
    """
    # 原始内容
    raw: str = ""

    # 解析字段
    role:            str = "geospatial analyst"
    domain:          str = "GIS / geospatial data analysis"
    preferred_lang:  str = "auto"       # "zh" | "en" | "auto"
    comm_style:      str = "concise"    # "concise" | "verbose" | "structured"
    tech_level:      str = "intermediate"
    tool_prefs:      List[str] = field(default_factory=list)
    output_prefs:    List[str] = field(default_factory=list)
    privacy_strict:  bool = False
    custom_sections: Dict[str, str] = field(default_factory=dict)

    def greeting_hint(self) -> str:
        """生成欢迎语个性化提示片段。"""
        hints = []
        if self.preferred_lang == "zh":
            hints.append("请用中文回复")
        elif self.preferred_lang == "en":
            hints.append("Please respond in English")
        if self.comm_style == "concise":
            hints.append("保持简洁")
        if self.tool_prefs:
            hints.append(f"偏好工具: {', '.join(self.tool_prefs[:3])}")
        return " | ".join(hints) if hints else ""

    def to_context_hint(self) -> str:
        """生成注入 LLM context 的用户偏好提示。"""
        lines = [f"User role: {self.role} ({self.domain})"]
        if self.preferred_lang != "auto":
            lines.append(f"Preferred language: {self.preferred_lang}")
        if self.comm_style:
            lines.append(f"Communication style: {self.comm_style}")
        if self.tool_prefs:
            lines.append(f"Preferred tools: {', '.join(self.tool_prefs)}")
        if self.output_prefs:
            lines.append(f"Output preferences: {', '.join(self.output_prefs[:3])}")
        return "\n".join(lines)


# ── Markdown 解析器 ────────────────────────────────────────────────────────────

def _parse_sections(md: str) -> Dict[str, str]:
    """将 Markdown 解析为 {section_title_lower: section_body} 字典。"""
    sections: Dict[str, str] = {}
    current_title = "__top__"
    current_lines: List[str] = []

    for line in md.splitlines():
        m = re.match(r'^#{1,3}\s+(.*)', line)
        if m:
            sections[current_title] = "\n".join(current_lines).strip()
            current_title = m.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current_title] = "\n".join(current_lines).strip()
    return sections


def _extract_list_items(text: str) -> List[str]:
    """从文本中提取列表项（支持 - / * / 数字.）。"""
    items = []
    for line in text.splitlines():
        m = re.match(r'^\s*(?:[-*•]|\d+\.)\s+(.*)', line)
        if m:
            items.append(m.group(1).strip())
    return items


def _extract_field(text: str, keys: List[str], default: str = "") -> str:
    """从键值对格式的文本里提取字段（如 'Role: xxx'）。"""
    for key in keys:
        m = re.search(rf'(?i){re.escape(key)}\s*[:\uff1a]\s*(.+)', text)
        if m:
            return m.group(1).strip()
    return default


# ── 解析函数 ──────────────────────────────────────────────────────────────────

def parse_soul(md: str) -> SoulConfig:
    """将 soul.md 内容解析为 SoulConfig 对象。"""
    cfg = SoulConfig(raw=md)
    secs = _parse_sections(md)

    # Identity
    for key in ["identity", "system identity"]:
        if key in secs:
            # 取第一个非空行作为 identity 摘要
            for line in secs[key].splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    cfg.identity = line
                    break

    # Mission
    for key in ["mission"]:
        if key in secs:
            text = secs[key].strip()
            if text:
                cfg.mission = text.splitlines()[0].strip()

    # Core Principles
    for key in ["core principles", "principles"]:
        if key in secs:
            cfg.principles = _extract_list_items(secs[key])

    # Spatial Reasoning Guidelines
    for key in ["spatial reasoning guidelines", "spatial reasoning"]:
        if key in secs:
            cfg.spatial_rules = _extract_list_items(secs[key])

    # Execution Hierarchy
    for key in ["execution hierarchy"]:
        if key in secs:
            cfg.exec_hierarchy = _extract_list_items(secs[key])

    # Safety Boundaries
    for key in ["safety boundaries", "safety"]:
        if key in secs:
            cfg.safety_rules = _extract_list_items(secs[key])

    # Output Standards
    for key in ["output standards", "output"]:
        if key in secs:
            cfg.output_standards = _extract_list_items(secs[key])

    # 预生成 system_prompt_fragment（截短，避免 token 浪费）
    cfg.system_prompt_fragment = _build_soul_prompt(cfg)
    return cfg


def _build_soul_prompt(cfg: SoulConfig) -> str:
    """生成注入 LLM 的精简 soul 片段（控制在 ~300 tokens 以内）。"""
    lines = [
        "=== GeoClaw System Identity ===",
        cfg.identity,
        f"Mission: {cfg.mission}",
    ]
    if cfg.principles:
        lines.append("Principles: " + "; ".join(cfg.principles[:4]))
    if cfg.spatial_rules:
        lines.append("Spatial rules: " + "; ".join(cfg.spatial_rules[:3]))
    if cfg.safety_rules:
        lines.append("Safety (Must NOT): " + "; ".join(cfg.safety_rules[:3]))
    return "\n".join(lines)


def parse_user(md: str) -> UserConfig:
    """将 user.md 内容解析为 UserConfig 对象。"""
    cfg = UserConfig(raw=md)
    secs = _parse_sections(md)

    # Identity / Role
    identity_text = secs.get("identity", "") or secs.get("user profile", "")
    if identity_text:
        cfg.role   = _extract_field(identity_text, ["role"], cfg.role)
        cfg.domain = _extract_field(identity_text, ["domain"], cfg.domain)

    # Language Preference
    lang_text = secs.get("language preference", "") or secs.get("language", "")
    if lang_text:
        raw_lang = _extract_field(lang_text,
                                  ["preferred language", "language"], "auto").lower()
        if "chinese" in raw_lang or "中文" in raw_lang or "zh" in raw_lang:
            cfg.preferred_lang = "zh"
        elif "english" in raw_lang or "en" in raw_lang:
            cfg.preferred_lang = "en"
        else:
            cfg.preferred_lang = "auto"

    # Communication Style
    style_text = secs.get("communication style", "") or secs.get("style", "")
    if style_text:
        if "concise" in style_text.lower():
            cfg.comm_style = "concise"
        elif "verbose" in style_text.lower():
            cfg.comm_style = "verbose"
        elif "structured" in style_text.lower():
            cfg.comm_style = "structured"

    # Technical Level
    level_text = secs.get("technical level", "") or secs.get("level", "")
    if level_text:
        text_lower = level_text.lower()
        if "expert" in text_lower or "advanced" in text_lower:
            cfg.tech_level = "expert"
        elif "basic" in text_lower or "beginner" in text_lower:
            cfg.tech_level = "beginner"
        else:
            cfg.tech_level = "intermediate"

    # Tool Preferences
    tool_text = secs.get("tool preferences", "") or secs.get("tools", "")
    if tool_text:
        cfg.tool_prefs = _extract_list_items(tool_text)

    # Output Preferences
    out_text = secs.get("output preferences", "") or secs.get("output", "")
    if out_text:
        cfg.output_prefs = _extract_list_items(out_text)

    # Privacy
    priv_text = secs.get("privacy and safety", "") or secs.get("privacy", "")
    if priv_text:
        cfg.privacy_strict = "private" in priv_text.lower()

    # 保存其余自定义 sections
    standard_keys = {
        "identity", "user profile", "language preference", "language",
        "communication style", "style", "technical level", "level",
        "tool preferences", "tools", "output preferences", "output",
        "privacy and safety", "privacy", "data handling preferences",
        "collaboration expectations", "__top__",
    }
    for k, v in secs.items():
        if k not in standard_keys and v.strip():
            cfg.custom_sections[k] = v.strip()

    return cfg


# ── ProfileManager 主类 ───────────────────────────────────────────────────────

class ProfileManager:
    """
    加载、解析和管理 soul.md / user.md 两层配置。

    Usage::

        pm = ProfileManager()
        pm.load()

        soul = pm.soul    # SoulConfig
        user = pm.user    # UserConfig

        # 获取注入 LLM 的系统提示词
        system_prompt = pm.build_system_prompt()

        # 获取注入 context 的用户偏好提示
        context_hint = pm.build_context_hint()
    """

    def __init__(
        self,
        soul_path: Optional[Path] = None,
        user_path: Optional[Path] = None,
        auto_create: bool = True,
    ):
        self.soul_path = Path(soul_path) if soul_path else DEFAULT_SOUL_PATH
        self.user_path = Path(user_path) if user_path else DEFAULT_USER_PATH
        self.auto_create = auto_create

        self._soul_raw: str = ""
        self._user_raw: str = ""
        self.soul: SoulConfig = SoulConfig()
        self.user: UserConfig = UserConfig()
        self._loaded: bool = False

    def load(self) -> "ProfileManager":
        """加载并解析两个配置文件。如果不存在则写入默认内容。"""
        self._soul_raw = self._read_or_create(self.soul_path, DEFAULT_SOUL_MD)
        self._user_raw = self._read_or_create(self.user_path, DEFAULT_USER_MD)

        self.soul = parse_soul(self._soul_raw)
        self.user = parse_user(self._user_raw)
        self._loaded = True
        return self

    def reload(self) -> "ProfileManager":
        """重新从磁盘加载（用于运行时热更新）。"""
        self._loaded = False
        return self.load()

    def _read_or_create(self, path: Path, default: str) -> str:
        """读取文件；若不存在且 auto_create=True 则创建默认文件。"""
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return default
        if self.auto_create:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(default, encoding="utf-8")
            except Exception:
                pass
        return default

    def build_system_prompt(self) -> str:
        """
        构建完整 system prompt = soul 系统身份片段。
        soul.md 定义系统行为边界，优先级最高，不受用户配置影响。
        """
        if not self._loaded:
            self.load()
        return self.soul.to_system_prompt()

    def build_context_hint(self) -> str:
        """
        构建注入 LLM context 的用户偏好提示（软个性化，不覆盖 soul 边界）。
        """
        if not self._loaded:
            self.load()
        return self.user.to_context_hint()

    def build_welcome_message(self, mode: str = "AI") -> str:
        """
        生成个性化欢迎语，融合用户角色/偏好。

        Args:
            mode: "AI" 或 "规则"
        """
        if not self._loaded:
            self.load()

        user = self.user
        soul = self.soul

        # 语言自适应
        use_zh = (user.preferred_lang == "zh") or (user.preferred_lang == "auto")

        if use_zh:
            role_hint = f"（{user.role}）" if "geospatial analyst" not in user.role.lower() else ""
            tool_hint = ""
            if user.tool_prefs:
                tool_hint = f"\n  · 偏好工具: {', '.join(user.tool_prefs[:3])}"
            msg = (
                f"GeoClaw-claude 自然语言 GIS 助手已启动（{mode}模式）{role_hint}。\n"
                f"系统使命：{soul.mission}\n"
                f"请直接用自然语言描述你想做的 GIS 操作，例如：\n"
                f"  · 加载 hospitals.geojson\n"
                f"  · 对医院做1公里缓冲区\n"
                f"  · 下载武汉市公园数据并可视化\n"
                f"  · 运行商场选址分析 skill{tool_hint}\n"
                f"  · 帮助"
            )
        else:
            msg = (
                f"GeoClaw-claude GIS assistant started ({mode} mode).\n"
                f"Mission: {soul.mission}\n"
                f"Type a natural language GIS instruction, e.g.:\n"
                f"  · load hospitals.geojson\n"
                f"  · buffer hospitals by 1 km\n"
                f"  · download parks in Wuhan and visualize\n"
                f"  · help"
            )
        return msg

    def summary(self) -> Dict[str, Any]:
        """返回配置摘要（用于调试/状态展示）。"""
        if not self._loaded:
            self.load()
        return {
            "soul_path":      str(self.soul_path),
            "user_path":      str(self.user_path),
            "soul_loaded":    bool(self._soul_raw),
            "user_loaded":    bool(self._user_raw),
            "soul_identity":  self.soul.identity[:80],
            "soul_principles": len(self.soul.principles),
            "user_role":      self.user.role,
            "user_lang":      self.user.preferred_lang,
            "user_style":     self.user.comm_style,
            "user_tools":     self.user.tool_prefs,
        }

    def __repr__(self) -> str:
        loaded = "loaded" if self._loaded else "not loaded"
        return (f"ProfileManager({loaded}, soul={self.soul_path.name}, "
                f"user={self.user_path.name})")
