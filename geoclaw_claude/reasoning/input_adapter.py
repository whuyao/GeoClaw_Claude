# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.input_adapter
=====================================
原始输入 → ReasoningInput 标准化适配器。

职责：
  1. 接受多种形式的输入（dict / dataclass / GeoAgent context）
  2. 统一转换为 ReasoningInput 对象
  3. 与现有 user.md / soul.md ProfileManager 对接
  4. 对接现有 GeoLayer / GeoClawProject（可选）

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from geoclaw_claude.reasoning.schemas import (
    DatasetMeta,
    PlannerHints,
    ProjectContext,
    ReasoningInput,
    SystemPolicy,
    UserContext,
)


# ── 语言代码映射 ───────────────────────────────────────────────────────────────
_LANG_MAP: Dict[str, str] = {
    "zh": "zh-CN", "zh-cn": "zh-CN", "chinese": "zh-CN", "中文": "zh-CN",
    "en": "en-US", "en-us": "en-US", "english": "en-US",
    "auto": "auto",
}


def build_reasoning_input(
    query: str,
    datasets: Optional[List[Union[dict, DatasetMeta]]] = None,
    user_context: Optional[Union[dict, UserContext]] = None,
    project_context: Optional[Union[dict, ProjectContext]] = None,
    planner_hints: Optional[Union[dict, PlannerHints]] = None,
    system_policy: Optional[Union[dict, SystemPolicy]] = None,
) -> ReasoningInput:
    """
    构建标准化的 ReasoningInput。

    Args:
        query           : 用户自然语言查询（必填）
        datasets        : 数据集元信息列表（dict 或 DatasetMeta）
        user_context    : 用户上下文（dict 或 UserContext）
        project_context : 项目上下文（dict 或 ProjectContext）
        planner_hints   : Planner 提示（dict 或 PlannerHints）
        system_policy   : 系统策略（dict 或 SystemPolicy）

    Returns:
        ReasoningInput — 标准化输入对象
    """
    return ReasoningInput(
        query           = query.strip(),
        datasets        = _build_datasets(datasets or []),
        user_context    = _build_user_context(user_context),
        project_context = _build_project_context(project_context),
        planner_hints   = _build_planner_hints(planner_hints),
        system_policy   = _build_system_policy(system_policy),
    )


def from_agent_context(
    query: str,
    agent_context: Dict[str, Any],
    datasets: Optional[List[Union[dict, DatasetMeta]]] = None,
) -> ReasoningInput:
    """
    从 GeoAgent._build_context() 的输出构建 ReasoningInput。

    与现有 GeoAgent 的对接入口：
      agent_context 通常包含:
        soul_system_prompt, user_profile_hint,
        available_layers, current_city 等

    Args:
        query         : 用户查询
        agent_context : GeoAgent._build_context() 返回的字典
        datasets      : 可选附加数据集元信息

    Returns:
        ReasoningInput
    """
    # 从 agent_context 提取用户偏好
    user_hint = agent_context.get("user_profile_hint", "")
    lang = _extract_lang_from_hint(user_hint)

    user_ctx = UserContext(
        language  = lang,
        expertise = _extract_expertise_from_hint(user_hint),
    )

    # 从 available_layers 构建数据集列表（若未显式传入）
    if datasets is None:
        layer_names = agent_context.get("available_layers", [])
        if isinstance(layer_names, str):
            layer_names = [n.strip() for n in layer_names.split(",") if n.strip()]
        datasets = [
            DatasetMeta(id=name, type="vector")
            for name in layer_names
        ]

    # 从 current_city / study_area 提取研究区
    study_area = (
        agent_context.get("current_city")
        or agent_context.get("study_area")
    )
    proj_ctx = ProjectContext(study_area=study_area)

    return ReasoningInput(
        query           = query.strip(),
        datasets        = _build_datasets(datasets),
        user_context    = user_ctx,
        project_context = proj_ctx,
    )


def from_profile_manager(
    query: str,
    profile_manager: Any,     # ProfileManager 实例，避免循环导入
    datasets: Optional[List[Union[dict, DatasetMeta]]] = None,
) -> ReasoningInput:
    """
    从 ProfileManager 中读取 soul/user 配置构建 ReasoningInput。

    Args:
        query           : 用户查询
        profile_manager : geoclaw_claude.nl.profile_manager.ProfileManager 实例
        datasets        : 可选数据集元信息列表

    Returns:
        ReasoningInput
    """
    summary = profile_manager.summary() if hasattr(profile_manager, "summary") else {}
    lang_raw  = summary.get("user_lang", "zh")
    lang      = _LANG_MAP.get(lang_raw.lower(), lang_raw)
    role      = summary.get("user_role", "general")

    # 从 soul 提取系统策略
    soul = getattr(profile_manager, "soul", None)
    policy_kwargs: Dict[str, Any] = {}
    if soul:
        safety_rules = getattr(soul, "safety_rules", [])
        rules_lower = [r.lower() for r in safety_rules]
        if any("overwrite" in r for r in rules_lower):
            policy_kwargs["readonly_inputs"] = True

    user_ctx = UserContext(
        language  = lang,
        expertise = _map_role_to_expertise(role),
    )

    return ReasoningInput(
        query           = query.strip(),
        datasets        = _build_datasets(datasets or []),
        user_context    = user_ctx,
        system_policy   = SystemPolicy(**policy_kwargs),
    )


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────

def _build_datasets(
    raw: List[Union[dict, DatasetMeta]],
) -> List[DatasetMeta]:
    result = []
    for item in raw:
        if isinstance(item, DatasetMeta):
            result.append(item)
        elif isinstance(item, dict):
            result.append(_dict_to_dataset(item))
        # 忽略其他类型
    return result


def _dict_to_dataset(d: dict) -> DatasetMeta:
    return DatasetMeta(
        id          = str(d.get("id") or d.get("name") or "dataset"),
        type        = d.get("type", "vector"),
        geometry    = d.get("geometry") or d.get("geometry_type"),
        crs         = d.get("crs") or d.get("epsg"),
        extent      = d.get("extent") or d.get("bbox"),
        time_range  = d.get("time_range") or d.get("time"),
        resolution  = d.get("resolution"),
        attributes  = d.get("attributes") or d.get("fields") or [],
        path        = d.get("path") or d.get("file"),
        writable    = bool(d.get("writable", False)),
        extra       = {k: v for k, v in d.items()
                       if k not in {"id","name","type","geometry","geometry_type",
                                    "crs","epsg","extent","bbox","time_range","time",
                                    "resolution","attributes","fields","path","file","writable"}},
    )


def _build_user_context(raw: Optional[Union[dict, UserContext]]) -> UserContext:
    if raw is None:
        return UserContext()
    if isinstance(raw, UserContext):
        return raw
    lang_raw = raw.get("language") or raw.get("lang") or "zh-CN"
    lang = _LANG_MAP.get(lang_raw.lower(), lang_raw)
    return UserContext(
        language          = lang,
        expertise         = raw.get("expertise") or raw.get("level") or "general",
        tool_preference   = raw.get("tool_preference") or raw.get("tools") or [],
        output_preference = raw.get("output_preference") or raw.get("output") or [],
        extra             = {k: v for k, v in raw.items()
                             if k not in {"language","lang","expertise","level",
                                          "tool_preference","tools","output_preference","output"}},
    )


def _build_project_context(raw: Optional[Union[dict, ProjectContext]]) -> ProjectContext:
    if raw is None:
        return ProjectContext()
    if isinstance(raw, ProjectContext):
        return raw
    return ProjectContext(
        study_area    = raw.get("study_area") or raw.get("area"),
        default_crs   = raw.get("default_crs") or raw.get("crs"),
        analysis_goal = raw.get("analysis_goal") or raw.get("goal"),
        extra         = {k: v for k, v in raw.items()
                         if k not in {"study_area","area","default_crs","crs",
                                      "analysis_goal","goal"}},
    )


def _build_planner_hints(raw: Optional[Union[dict, PlannerHints]]) -> PlannerHints:
    if raw is None:
        return PlannerHints()
    if isinstance(raw, PlannerHints):
        return raw
    return PlannerHints(
        candidate_task_type = raw.get("candidate_task_type") or raw.get("task_type"),
        candidate_methods   = raw.get("candidate_methods") or raw.get("methods") or [],
        extra               = {k: v for k, v in raw.items()
                                if k not in {"candidate_task_type","task_type",
                                             "candidate_methods","methods"}},
    )


def _build_system_policy(raw: Optional[Union[dict, SystemPolicy]]) -> SystemPolicy:
    if raw is None:
        return SystemPolicy()
    if isinstance(raw, SystemPolicy):
        return raw
    return SystemPolicy(
        readonly_inputs          = bool(raw.get("readonly_inputs", True)),
        require_output_workspace = bool(raw.get("require_output_workspace", True)),
        allow_unregistered_tools = bool(raw.get("allow_unregistered_tools", False)),
        extra                    = {k: v for k, v in raw.items()
                                    if k not in {"readonly_inputs","require_output_workspace",
                                                 "allow_unregistered_tools"}},
    )


def _extract_lang_from_hint(hint: str) -> str:
    hint_l = hint.lower()
    if "preferred language: zh" in hint_l or "language: zh" in hint_l:
        return "zh-CN"
    if "preferred language: en" in hint_l or "language: en" in hint_l:
        return "en-US"
    return "zh-CN"   # 默认中文


def _extract_expertise_from_hint(hint: str) -> str:
    hint_l = hint.lower()
    if "expert" in hint_l or "researcher" in hint_l:
        return "GIS expert"
    if "intermediate" in hint_l:
        return "intermediate"
    if "beginner" in hint_l:
        return "beginner"
    return "general"


def _map_role_to_expertise(role: str) -> str:
    role_l = role.lower()
    if "researcher" in role_l or "analyst" in role_l or "expert" in role_l:
        return "GIS expert"
    if "student" in role_l or "beginner" in role_l:
        return "beginner"
    return "general"
