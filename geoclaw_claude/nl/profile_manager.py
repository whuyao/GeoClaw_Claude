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


# ── ProfileUpdater — 对话中动态更新 soul.md / user.md ─────────────────────────

# soul.md 中不允许通过对话修改的安全字段（锁定区域关键词）
_SOUL_LOCKED_SECTIONS = [
    "Safety Boundaries",
    "Execution Hierarchy",
    "Data Handling Rules",
    "Core Principles",
]

# 触发 user.md 更新的关键词模式
_USER_UPDATE_TRIGGERS = [
    r"记住我?(?:的)?(?:偏好|习惯|设置|配置)",
    r"我?(?:喜欢|偏好|习惯使用|常用)",
    r"以后.*(?:用|使用|采用)",
    r"帮我?更新.*(?:profile|user\.md|偏好|配置)",
    r"设置我?的.*(?:语言|风格|偏好|模型)",
    r"remember (my |that |I )",
    r"set my (preference|style|language|default)",
    r"update (my |user\.?md|profile)",
    r"I (prefer|like|always use|usually use)",
]

# 触发 soul.md 更新的关键词模式（仅允许非安全字段）
_SOUL_UPDATE_TRIGGERS = [
    r"更新.*(?:系统|soul\.md|身份|任务|使命)",
    r"修改.*(?:系统身份|系统使命|输出格式|协作方式)",
    r"update (soul\.?md|system identity|mission|output format)",
    r"change (geoclaw's |system |the )?(mission|identity|output style)",
]


class ProfileUpdater:
    """
    对话中动态更新 soul.md / user.md。

    设计原则:
    - user.md  : 用户可以在对话中自由更新偏好（语言/风格/工具/角色等）
    - soul.md  : 仅允许修改非安全字段（输出格式/协作哲学/描述性内容）
                 安全相关字段（Safety Boundaries / Execution Hierarchy /
                 Core Principles / Data Handling Rules）不可通过对话修改

    调用方式（由 GeoAgent 在 chat() 中驱动）:
        updater = ProfileUpdater(profile_manager)
        result = updater.maybe_update(user_input, conversation_summary)
        if result:
            print(result.message)
    """

    def __init__(self, profile_manager: ProfileManager, verbose: bool = False):
        self.pm      = profile_manager
        self.verbose = verbose

    # ── 公共入口 ──────────────────────────────────────────────────────────────

    def maybe_update(
        self,
        user_input: str,
        conversation_summary: Optional[str] = None,
    ) -> Optional["UpdateResult"]:
        """
        检测用户输入是否包含更新偏好的意图，若有则执行更新。

        Returns:
            UpdateResult（含 file / fields / message），无更新时返回 None
        """
        import re
        text = user_input.strip()

        # 安全优先：任何试图修改锁定字段的请求，直接拒绝
        for locked in _SOUL_LOCKED_SECTIONS:
            if locked.lower() in text.lower():
                return UpdateResult(
                    file="soul.md", fields=[],
                    message=(
                        f"[安全锁定] '{locked}' 是 soul.md 中的安全字段，"
                        f"不允许通过对话修改。\n"
                        f"如需调整，请直接编辑 {self.pm.soul_path}"
                    ),
                    changed=False,
                    blocked=True,
                )

        # 检测 user.md 更新意图
        if self._matches(text, _USER_UPDATE_TRIGGERS):
            return self._update_user_md(text, conversation_summary)

        # 检测 soul.md 更新意图（仅允许非安全字段）
        if self._matches(text, _SOUL_UPDATE_TRIGGERS):
            return self._update_soul_md(text, conversation_summary)

        return None

    def update_user_field(self, field: str, value: str) -> "UpdateResult":
        """
        直接更新 user.md 中的某个字段。

        特殊字段处理：
          - session_insight  : 追加到 ## Session Insights 区块（保留历史记录）
          - frequent_cities  : 更新 ## Region Preference 区块
          - inferred_domain  : 更新 ## Inferred Research Domain 区块
          - preferred_lang / comm_style / tool_prefs 等：键值对覆盖更新
        """
        if not self.pm._loaded:
            self.pm.load()

        raw = self.pm._user_raw or DEFAULT_USER_MD

        # 特殊字段：session_insight 追加模式
        if field == "session_insight":
            updated = self._append_session_insight(raw, value)
        # 特殊字段：写入专属 section
        elif field == "frequent_cities":
            updated = self._upsert_section(raw, "Region Preference",
                                           f"Frequent cities: {value}")
        elif field == "inferred_domain":
            updated = self._upsert_section(raw, "Inferred Research Domain",
                                           f"Inferred domain: {value}")
        else:
            updated = self._set_markdown_field(raw, field, value)

        if updated == raw:
            return UpdateResult(
                file="user.md", fields=[field],
                message=f"[profile] user.md 字段 {field!r} 未变更（值已是最新）",
                changed=False,
            )
        self._write(self.pm.user_path, updated)
        self.pm.reload()
        return UpdateResult(
            file="user.md", fields=[field],
            message=f"[profile] user.md 已更新: {field} = {value!r}",
            changed=True,
        )

    def summarize_and_update(
        self,
        conversation_turns: List[Dict[str, str]],
        llm_provider: Optional[Any] = None,
    ) -> List["UpdateResult"]:
        """
        基于完整对话内容，提取用户偏好并批量更新 user.md（一次写入）。
        可由 GeoAgent.end() 在会话结束时自动触发。

        Args:
            conversation_turns: 对话历史 [{role, content}, ...]
            llm_provider: LLMProvider 实例（用于 AI 摘要），None 则用规则提取

        Returns:
            所有成功更新的 UpdateResult 列表
        """
        if not conversation_turns:
            return []

        if not self.pm._loaded:
            self.pm.load()

        if llm_provider is not None:
            extracted = self._ai_extract_preferences(conversation_turns, llm_provider)
        else:
            extracted = self._rule_extract_preferences(conversation_turns)

        if not extracted:
            return []

        # 批量应用所有变更（在内存中链式操作，最后一次写入）
        raw = self.pm._user_raw or DEFAULT_USER_MD
        results: List["UpdateResult"] = []
        changed_fields: List[str] = []

        for field, value in extracted.items():
            if field == "session_insight":
                new_raw = self._append_session_insight(raw, value)
            elif field == "frequent_cities":
                new_raw = self._upsert_section(raw, "Region Preference",
                                               f"Frequent cities: {value}")
            elif field == "inferred_domain":
                new_raw = self._upsert_section(raw, "Inferred Research Domain",
                                               f"Inferred domain: {value}")
            else:
                new_raw = self._set_markdown_field(raw, field, value)

            if new_raw != raw:
                raw = new_raw
                changed_fields.append(f"{field}={value!r}")

        if changed_fields:
            self._write(self.pm.user_path, raw)
            self.pm._user_raw = raw  # 直接更新内存，避免重复 reload
            self.pm.user = __import__(
                "geoclaw_claude.nl.profile_manager", fromlist=["parse_user"]
            ).parse_user(raw)
            results.append(UpdateResult(
                file="user.md",
                fields=changed_fields,
                message=f"[profile] user.md 已自动更新: {', '.join(changed_fields)}",
                changed=True,
            ))

        return results

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _matches(text: str, patterns: List[str]) -> bool:
        import re
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return True
        return False

    def _update_user_md(
        self,
        text: str,
        summary: Optional[str],
    ) -> "UpdateResult":
        """从用户输入提取偏好并更新 user.md。"""
        if not self.pm._loaded:
            self.pm.load()

        import re
        raw = self.pm._user_raw or DEFAULT_USER_MD
        fields_updated: List[str] = []

        # 语言偏好
        lang_m = re.search(r"(?:用|使用|偏好|language)[：: ]*(中文|英文|Chinese|English|zh|en)", text, re.IGNORECASE)
        if lang_m:
            lang_val = "zh" if lang_m.group(1).lower() in ("中文", "zh", "chinese") else "en"
            raw = self._set_markdown_field(raw, "Preferred language", lang_val)
            fields_updated.append(f"language={lang_val}")

        # 风格偏好
        style_m = re.search(r"(?:风格|style)[：: ]*(简洁|详细|专业|casual|brief|detailed|professional)", text, re.IGNORECASE)
        if style_m:
            raw = self._set_markdown_field(raw, "Communication style", style_m.group(1))
            fields_updated.append(f"style={style_m.group(1)}")

        # 工具偏好（追加到 tool_prefs）
        tool_m = re.search(r"(?:偏好|喜欢|prefer|use)\s+(\w+)\s*(?:工具|tool)?", text, re.IGNORECASE)
        if tool_m:
            tool = tool_m.group(1)
            raw = self._append_tool_pref(raw, tool)
            fields_updated.append(f"tool+={tool}")

        if fields_updated:
            self._write(self.pm.user_path, raw)
            self.pm.reload()
            return UpdateResult(
                file="user.md",
                fields=fields_updated,
                message=f"[profile] user.md 已更新: {', '.join(fields_updated)}",
                changed=True,
            )

        return UpdateResult(
            file="user.md", fields=[],
            message="[profile] 检测到更新意图，但未提取到具体字段（请更明确地描述偏好）",
            changed=False,
        )

    def _update_soul_md(
        self,
        text: str,
        summary: Optional[str],
    ) -> "UpdateResult":
        """
        尝试更新 soul.md 非安全字段。
        任何触碰安全字段的请求都会被拒绝并返回说明。
        """
        import re
        # 检查是否触碰安全字段
        for locked in _SOUL_LOCKED_SECTIONS:
            if locked.lower() in text.lower():
                return UpdateResult(
                    file="soul.md", fields=[],
                    message=(
                        f"[profile] 拒绝更新 soul.md: "
                        f"'{locked}' 是安全锁定字段，不允许通过对话修改。\n"
                        f"如需调整，请直接编辑 {self.pm.soul_path}"
                    ),
                    changed=False,
                    blocked=True,
                )

        # 仅允许修改描述性/风格字段
        if not self.pm._loaded:
            self.pm.load()
        raw = self.pm._soul_raw or DEFAULT_SOUL_MD

        # 协作哲学更新
        collab_m = re.search(r"(?:协作|collaboration|合作).*?[:：](.+)", text, re.IGNORECASE)
        if collab_m:
            new_val = collab_m.group(1).strip()
            raw = self._set_markdown_section(raw, "Collaboration Philosophy", new_val)
            self._write(self.pm.soul_path, raw)
            self.pm.reload()
            return UpdateResult(
                file="soul.md", fields=["Collaboration Philosophy"],
                message=f"[profile] soul.md Collaboration Philosophy 已更新",
                changed=True,
            )

        return UpdateResult(
            file="soul.md", fields=[],
            message="[profile] 检测到 soul.md 更新意图，但未识别到可修改的字段（安全字段不可修改）",
            changed=False,
        )

    def _ai_extract_preferences(
        self,
        turns: List[Dict[str, str]],
        llm: Any,
    ) -> Dict[str, str]:
        """使用 LLM 从对话历史中提取用户偏好字段。"""
        import json as _json

        history_text = "\n".join(
            f"{t.get('role','?')}: {t.get('content','')[:200]}"
            for t in turns[-10:]  # 只取最近 10 轮
        )
        prompt = (
            "从以下对话历史中，提取用户的偏好信息，仅输出 JSON，不要解释。\n"
            "可提取的字段（均为可选）：\n"
            "  preferred_lang: zh 或 en\n"
            "  comm_style: brief / detailed / professional / casual\n"
            "  role: 用户角色描述（如 urban planner / researcher）\n"
            "  tool_prefs: 偏好工具列表（逗号分隔）\n"
            "  output_format: 输出格式偏好（如 markdown / plain / table）\n"
            "若对话中没有相关信息，不要包含该字段。\n\n"
            f"对话历史:\n{history_text}\n\n"
            "输出 JSON（仅 JSON，无 markdown 包装）:"
        )
        try:
            resp = llm.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
            )
            if resp and resp.content:
                from geoclaw_claude.nl.llm_provider import parse_json_response
                data = parse_json_response(resp.content)
                if isinstance(data, dict):
                    return {k: str(v) for k, v in data.items() if v}
        except Exception as e:
            if self.verbose:
                print(f"  [ProfileUpdater] AI 提取失败: {e}")
        return {}

    def _rule_extract_preferences(
        self,
        turns: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """
        规则式：从对话历史推断用户偏好。

        推断维度：
          - preferred_lang  : 统计中/英文字符占比
          - frequent_cities : 对话中多次出现的城市名
          - inferred_domain : 根据操作关键词推断研究方向
          - comm_style      : 根据问题长短推断详细/简洁风格
          - session_insight : 本次对话摘要（追加到 user.md）
        """
        import re as _re
        from datetime import datetime as _dt

        user_texts = [
            t.get("content", "") for t in turns if t.get("role") == "user"
        ]
        if not user_texts:
            return {}

        full = " ".join(user_texts)
        prefs: Dict[str, str] = {}

        # 1. 语言偏好
        zh_count = len(_re.findall(r"[\u4e00-\u9fff]", full))
        en_count  = len(_re.findall(r"[a-zA-Z]+", full))
        if zh_count > en_count * 2:
            prefs["preferred_lang"] = "zh"
        elif en_count > zh_count * 2:
            prefs["preferred_lang"] = "en"

        # 2. 城市偏好（高频城市）
        CITIES = [
            "景德镇", "武汉", "北京", "上海", "广州", "深圳", "成都", "南京",
            "杭州", "西安", "重庆", "天津", "苏州", "郑州", "长沙",
            "Wuhan", "Beijing", "Shanghai", "Chengdu", "Guangzhou", "Shenzhen",
        ]
        city_counts: Dict[str, int] = {}
        for city in CITIES:
            cnt = len(_re.findall(_re.escape(city), full, _re.IGNORECASE))
            if cnt >= 2:
                city_counts[city] = cnt
        if city_counts:
            top_cities = sorted(city_counts, key=lambda c: -city_counts[c])[:3]
            prefs["frequent_cities"] = ", ".join(top_cities)

        # 3. 研究领域推断
        domain_keywords = {
            "urban planning / site selection":  ["选址", "商场", "商业", "mall", "siting"],
            "transportation / mobility":        ["路网", "公交", "地铁", "等时圈", "isochrone", "routing"],
            "environmental / ecology":          ["植被", "水体", "生态", "洪水", "NDVI", "DEM"],
            "public health / facilities":       ["医院", "学校", "卫生", "设施", "hospital"],
            "population / demographics":        ["人口", "密度", "居住", "住宅", "population"],
        }
        domain_scores: Dict[str, int] = {}
        for domain, kws in domain_keywords.items():
            score = sum(full.lower().count(kw.lower()) for kw in kws)
            if score > 0:
                domain_scores[domain] = score
        if domain_scores:
            top_domain = max(domain_scores, key=lambda d: domain_scores[d])
            if domain_scores[top_domain] >= 2:
                prefs["inferred_domain"] = top_domain

        # 4. 沟通风格（平均消息长度）
        avg_len = sum(len(t) for t in user_texts) / max(len(user_texts), 1)
        if avg_len < 12:
            prefs["comm_style"] = "brief"
        elif avg_len > 50:
            prefs["comm_style"] = "detailed"

        # 5. 会话摘要（写入 Session Insights）
        agent_texts = [t.get("content", "") for t in turns if t.get("role") == "agent"]
        ops_done = [t for t in agent_texts if any(
            kw in t for kw in ["✓", "已完成", "下载完成", "生成", "分析完成", "Done"]
        )]
        timestamp = _dt.now().strftime("%Y-%m-%d")
        summary_parts = [f"[{timestamp}]"]
        if city_counts:
            summary_parts.append(f"城市: {', '.join(top_cities)}")
        if "inferred_domain" in prefs:
            summary_parts.append(f"领域: {prefs['inferred_domain']}")
        if ops_done:
            summary_parts.append(f"完成操作: {len(ops_done)} 项")
        if len(user_texts) >= 2:
            prefs["session_insight"] = " | ".join(summary_parts)

        return prefs

    @staticmethod
    def _set_markdown_field(raw: str, field: str, value: str) -> str:
        """在 Markdown 中查找并替换 'Field: old_value' 为 'Field: new_value'。"""
        import re
        pattern = rf"(?m)^({re.escape(field)})\s*[:：]\s*.+$"
        replacement = f"{field}: {value}"
        new = re.sub(pattern, replacement, raw, count=1, flags=re.IGNORECASE)
        if new == raw:
            # 未找到，追加
            new = raw.rstrip() + f"\n{field}: {value}\n"
        return new

    @staticmethod
    def _set_markdown_section(raw: str, section: str, new_content: str) -> str:
        """替换 ## Section 下的第一段内容。"""
        import re
        pattern = rf"(## {re.escape(section)}\n)(.*?)(\n## |\Z)"
        replacement = rf"\g<1>{new_content}\n\g<3>"
        new = re.sub(pattern, replacement, raw, count=1, flags=re.DOTALL)
        return new if new != raw else raw

    @staticmethod
    def _append_tool_pref(raw: str, tool: str) -> str:
        """在 tool_prefs 列表中追加工具（避免重复）。"""
        import re
        m = re.search(r"(Tool preferences?[：:]\s*)(.+)", raw, re.IGNORECASE)
        if m:
            existing = [t.strip() for t in m.group(2).split(",")]
            if tool not in existing:
                existing.append(tool)
                return raw[:m.start(2)] + ", ".join(existing) + raw[m.end(2):]
        else:
            raw = raw.rstrip() + f"\nTool preferences: {tool}\n"
        return raw

    @staticmethod
    def _append_session_insight(raw: str, insight: str) -> str:
        """在 ## Session Insights section 中追加一条记录（保留历史，自动去重）。"""
        SECTION = "## Session Insights"
        if SECTION in raw:
            # 已有 section，先检查是否重复
            if insight in raw:
                return raw  # 已存在，不重复追加
            idx = raw.index(SECTION)
            next_sec = raw.find("\n## ", idx + len(SECTION))
            if next_sec == -1:
                return raw.rstrip() + f"\n- {insight}\n"
            else:
                return raw[:next_sec].rstrip() + f"\n- {insight}\n" + raw[next_sec:]
        else:
            return raw.rstrip() + f"\n\n{SECTION}\n- {insight}\n"

    @staticmethod
    def _upsert_section(raw: str, section_title: str, content_line: str) -> str:
        """插入或更新一个 ## section（单行内容，覆盖模式）。若内容相同则不写入。"""
        import re
        SECTION = f"## {section_title}"
        if SECTION in raw:
            # 检查内容是否已经相同
            idx = raw.index(SECTION)
            next_sec = raw.find("\n## ", idx + len(SECTION))
            existing_body = raw[idx + len(SECTION):next_sec if next_sec != -1 else len(raw)]
            if content_line in existing_body:
                return raw  # 内容相同，不更新
            pattern = rf"(## {re.escape(section_title)}\n)(.*?)(\n## |\Z)"
            replacement = rf"\g<1>{content_line}\n\g<3>"
            new = re.sub(pattern, replacement, raw, count=1, flags=re.DOTALL)
            return new if new != raw else raw
        else:
            return raw.rstrip() + f"\n\n{SECTION}\n{content_line}\n"

    @staticmethod
    def _write(path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            pass  # 写入失败静默处理（测试环境路径不存在时）


@dataclass
class UpdateResult:
    """对话更新 profile 的结果。"""
    file:    str               # "user.md" 或 "soul.md"
    fields:  List[str]         # 更新的字段列表
    message: str               # 面向用户的说明文本
    changed: bool = False      # 是否实际写入了文件
    blocked: bool = False      # 是否因安全原因被拒绝
