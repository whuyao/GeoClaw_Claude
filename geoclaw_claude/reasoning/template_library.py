# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.template_library
==========================================
方法模板库（Phase 2）。

负责：
  1. 加载 templates/*.yaml 所有方法模板
  2. 根据任务类型（AnalysisIntent）和数据条件匹配最适合的模板
  3. 从匹配模板中提取推荐方法列表（MethodCandidate）

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    GeoEntityType,
    MethodCandidate,
    ReasoningContext,
    TaskProfile,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_INTENT_TO_TEMPLATES: Dict[str, List[str]] = {
    AnalysisIntent.SELECTION.value:        ["site_selection", "proximity"],
    AnalysisIntent.COMPARISON.value:       ["proximity", "accessibility", "change_detection"],
    AnalysisIntent.CLUSTERING.value:       ["trajectory", "proximity"],
    AnalysisIntent.ACCESSIBILITY.value:    ["accessibility", "proximity"],
    AnalysisIntent.OPTIMIZATION.value:     ["site_selection", "accessibility"],
    AnalysisIntent.CHANGE_DETECTION.value: ["change_detection"],
    AnalysisIntent.PREDICTION.value:       ["change_detection", "trajectory"],
    AnalysisIntent.EXPLANATION.value:      ["accessibility", "proximity"],
    AnalysisIntent.SUMMARIZATION.value:    ["proximity", "trajectory"],
    AnalysisIntent.UNKNOWN.value:          ["proximity"],
}

_ENTITY_TEMPLATE_AFFINITY: Dict[str, str] = {
    GeoEntityType.TRAJECTORY.value: "trajectory",
    GeoEntityType.NETWORK.value:    "accessibility",
    GeoEntityType.FACILITY.value:   "accessibility",
    GeoEntityType.RASTER.value:     "change_detection",
}

_TEMPLATE_CACHE: Dict[str, dict] = {}


def load_templates(force_reload: bool = False) -> Dict[str, dict]:
    """加载 templates/*.yaml，返回 {template_id: template_dict}，结果缓存。"""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE and not force_reload:
        return _TEMPLATE_CACHE

    templates: Dict[str, dict] = {}
    if not _TEMPLATES_DIR.exists():
        logger.warning(f"Templates directory not found: {_TEMPLATES_DIR}")
        return templates

    for yaml_file in sorted(_TEMPLATES_DIR.glob("*.yaml")):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            template_id = data.get("template_id", yaml_file.stem)
            templates[template_id] = data
            logger.debug(f"Loaded template: {template_id}")
        except Exception as e:
            logger.warning(f"Failed to load template {yaml_file.name}: {e}")

    _TEMPLATE_CACHE = templates
    logger.info(f"Template library: {len(templates)} templates loaded.")
    return templates


def match_templates(
    task_profile: TaskProfile,
    ctx: Optional[ReasoningContext] = None,
) -> List[dict]:
    """根据 TaskProfile 匹配最适合的模板列表（有序，最相关在前）。"""
    templates = load_templates()
    if not templates:
        return []

    candidate_ids: List[str] = []
    for intent in [task_profile.task_type] + task_profile.subtask_types:
        intent_val = intent.value if hasattr(intent, "value") else str(intent)
        for tid in _INTENT_TO_TEMPLATES.get(intent_val, []):
            if tid not in candidate_ids:
                candidate_ids.append(tid)

    entity_boost: List[str] = []
    for ent in task_profile.entities:
        ent_val = ent.value if hasattr(ent, "value") else str(ent)
        boosted = _ENTITY_TEMPLATE_AFFINITY.get(ent_val)
        if boosted and boosted not in entity_boost:
            entity_boost.append(boosted)

    reordered: List[str] = []
    for tid in entity_boost:
        if tid in candidate_ids and tid not in reordered:
            reordered.append(tid)
    for tid in candidate_ids:
        if tid not in reordered:
            reordered.append(tid)

    if ctx is not None:
        data_types = {ds.type for ds in ctx.datasets} if ctx.datasets else set()
        if data_types == {"raster"} and "trajectory" in reordered:
            reordered.remove("trajectory")
        if "trajectory" in data_types and "trajectory" not in reordered:
            reordered.insert(0, "trajectory")

    return [templates[tid] for tid in reordered if tid in templates]


def get_method_candidates(
    task_profile: TaskProfile,
    ctx: Optional[ReasoningContext] = None,
    max_methods: int = 6,
) -> List[MethodCandidate]:
    """从匹配模板中提取推荐 MethodCandidate 列表，按 priority 排序。"""
    matched_templates = match_templates(task_profile, ctx)
    if not matched_templates:
        return []

    candidates: List[Tuple[int, MethodCandidate]] = []
    seen_ids: set = set()

    for template in matched_templates:
        template_id = template.get("template_id", "unknown")
        for method in template.get("methods", []):
            method_id = method.get("id", "")
            if not method_id or method_id in seen_ids:
                continue
            seen_ids.add(method_id)
            candidates.append((
                method.get("priority", 99),
                MethodCandidate(
                    method_id=method_id,
                    category=template_id,
                    description=method.get("description", method.get("name", "")),
                    priority=method.get("priority", 99),
                ),
            ))

    candidates.sort(key=lambda x: x[0])
    return [mc for _, mc in candidates[:max_methods]]


def get_template_by_id(template_id: str) -> Optional[dict]:
    """获取指定 ID 的模板字典"""
    return load_templates().get(template_id)


def list_template_ids() -> List[str]:
    """列出所有已加载的模板 ID"""
    return list(load_templates().keys())


def get_method_info(template_id: str, method_id: str) -> Optional[dict]:
    """获取指定模板中某方法的完整信息"""
    template = get_template_by_id(template_id)
    if not template:
        return None
    for method in template.get("methods", []):
        if method.get("id") == method_id:
            return method
    return None


def get_method_limitations(template_id: str, method_id: str) -> List[str]:
    """获取指定方法的局限说明列表"""
    info = get_method_info(template_id, method_id)
    return info.get("limitations", []) if info else []


def get_template_notes(template_id: str) -> str:
    """获取模板注意事项"""
    t = get_template_by_id(template_id)
    return t.get("notes", "") if t else ""


def get_recommended_artifacts(template_id: str) -> List[dict]:
    """获取模板推荐的输出产物"""
    t = get_template_by_id(template_id)
    return t.get("recommended_output_artifacts", []) if t else []
