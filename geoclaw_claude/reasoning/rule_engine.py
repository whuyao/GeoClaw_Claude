# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.rule_engine
=====================================
GIS 硬规则引擎（Rule Layer）。

职责（文档第四章）：
  1. 加载 rules/*.yaml 规则库
  2. 对 ReasoningContext + TaskProfile 逐条进行确定性校验
  3. 检测 CRS / 几何 / 时序 / 尺度 / 安全 五类问题
  4. 输出 RuleEngineOutput（constraints, violations, method_candidates, preconditions）

Phase 1 实现：
  纯 Python 条件判断（不依赖 LLM）。
  规则条件通过 _RuleConditionEvaluator 评估，
  每条规则的 condition 字符串映射到对应的 Python 评估函数。

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    CRSStatus,
    GeoEntityType,
    MethodCandidate,
    ReasoningContext,
    RuleEngineOutput,
    RuleViolation,
    SpatialRelation,
    TaskProfile,
    TemporalStatus,
)


# ── 规则文件位置 ───────────────────────────────────────────────────────────────
_RULES_DIR = Path(__file__).parent / "rules"

_RULE_FILES = [
    ("crs",      "crs_rules.yaml"),
    ("topology", "topology_rules.yaml"),
    ("temporal", "temporal_rules.yaml"),
    ("scale",    "scale_rules.yaml"),
    ("safety",   "safety_rules.yaml"),
]

# ── 方法候选模板（Phase 1 内嵌，Phase 2 迁入 template_library）────────────────
_INTENT_TO_METHODS: Dict[str, List[MethodCandidate]] = {
    AnalysisIntent.COMPARISON.value: [
        MethodCandidate("multi_ring_buffer_summary", "proximity",
                        "多环缓冲区统计，适合站点周边对比分析", priority=1),
        MethodCandidate("spatial_join_summary",      "proximity",
                        "空间连接统计（count / diversity）", priority=2),
        MethodCandidate("kernel_density_estimation", "clustering",
                        "核密度估计（可视化对比）", priority=3),
    ],
    AnalysisIntent.ACCESSIBILITY.value: [
        MethodCandidate("service_area_analysis",     "accessibility",
                        "服务范围分析（等时圈）", priority=1),
        MethodCandidate("network_shortest_path",     "accessibility",
                        "网络最短路径可达性", priority=2),
        MethodCandidate("euclidean_distance_buffer", "proximity",
                        "欧氏距离缓冲区（近似可达性）", priority=3),
    ],
    AnalysisIntent.OPTIMIZATION.value: [
        MethodCandidate("weighted_overlay",          "site_selection",
                        "加权叠加选址", priority=1),
        MethodCandidate("coverage_optimization",     "site_selection",
                        "覆盖率最大化选址", priority=2),
        MethodCandidate("constrained_candidate_filter", "site_selection",
                        "约束条件候选点过滤", priority=3),
    ],
    AnalysisIntent.CLUSTERING.value: [
        MethodCandidate("kernel_density_estimation", "clustering",
                        "核密度估计（热点可视化）", priority=1),
        MethodCandidate("spatial_join_summary",      "proximity",
                        "空间聚合统计", priority=2),
    ],
    AnalysisIntent.CHANGE_DETECTION.value: [
        MethodCandidate("raster_differencing",       "change_detection",
                        "栅格差值变化检测", priority=1),
        MethodCandidate("temporal_overlay",          "change_detection",
                        "时序叠加分析", priority=2),
        MethodCandidate("land_cover_transition_matrix", "change_detection",
                        "土地覆盖转移矩阵", priority=3),
    ],
    AnalysisIntent.SUMMARIZATION.value: [
        MethodCandidate("zonal_statistics",          "summarization",
                        "分区统计（均值/总量/多样性）", priority=1),
        MethodCandidate("spatial_join_summary",      "proximity",
                        "空间连接聚合", priority=2),
    ],
    AnalysisIntent.SELECTION.value: [
        MethodCandidate("attribute_filter",          "selection",
                        "属性过滤筛选", priority=1),
        MethodCandidate("spatial_query",             "selection",
                        "空间查询（within / intersects）", priority=2),
    ],
}


def run_rule_engine(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
) -> RuleEngineOutput:
    """
    运行 GIS 硬规则引擎。

    Args:
        ctx          : 预处理后的推理上下文
        task_profile : 任务类型识别结果

    Returns:
        RuleEngineOutput — 约束、违规、方法候选、前置条件
    """
    out = RuleEngineOutput()

    # ── 1. CRS 评估 ──────────────────────────────────────────────────────────
    crs_status, crs_violations, crs_preconditions = _evaluate_crs(ctx, task_profile)
    out.crs_status    = crs_status
    out.violations   += crs_violations
    out.preconditions+= crs_preconditions

    # ── 2. 几何/拓扑规则 ─────────────────────────────────────────────────────
    topo_violations, topo_constraints = _evaluate_topology(ctx, task_profile)
    out.violations   += topo_violations
    out.hard_constraints += topo_constraints

    # ── 3. 时序规则 ──────────────────────────────────────────────────────────
    temp_violations, temp_constraints = _evaluate_temporal(ctx, task_profile)
    out.violations   += temp_violations
    out.hard_constraints += temp_constraints

    # ── 4. 尺度规则 ──────────────────────────────────────────────────────────
    scale_warnings = _evaluate_scale(ctx, task_profile)
    out.warnings     += scale_warnings

    # ── 5. 安全规则 ──────────────────────────────────────────────────────────
    safety_violations = _evaluate_safety(ctx)
    out.violations   += safety_violations

    # ── 6. hard_constraints 从 violations(error) 汇总 ────────────────────────
    for v in out.violations:
        if v.severity == "error" and v.rule_id not in out.hard_constraints:
            out.hard_constraints.append(v.rule_id)

    # ── 7. CRS 前置条件加入 hard_constraints ─────────────────────────────────
    for pc in crs_preconditions:
        key = pc.get("constraint_key")
        if key and key not in out.hard_constraints:
            out.hard_constraints.append(key)

    # ── 8. 方法候选 ──────────────────────────────────────────────────────────
    out.method_candidates = _select_method_candidates(task_profile)

    # ── 9. 任务候选列表 ──────────────────────────────────────────────────────
    out.task_candidates = [task_profile.task_type.value] + [
        s.value for s in task_profile.subtask_types
    ]

    # ── 10. 解析实体/关系/指标 ───────────────────────────────────────────────
    out.resolved_entities   = [e.value for e in task_profile.entities]
    out.resolved_relations  = [r.value for r in task_profile.relations]
    out.target_metrics      = _infer_target_metrics(task_profile)

    return out


# ══════════════════════════════════════════════════════════════════════════════
#  CRS 评估
# ══════════════════════════════════════════════════════════════════════════════

def _evaluate_crs(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
) -> tuple[CRSStatus, List[RuleViolation], List[Dict[str, Any]]]:
    """评估 CRS 状态并生成重投影前置条件"""
    violations:   List[RuleViolation]    = []
    preconditions: List[Dict[str, Any]]  = []
    datasets      = ctx.datasets

    if not datasets:
        return CRSStatus.UNKNOWN, violations, preconditions

    # 检测地理坐标系 / CRS 不一致
    crs_list       = [d.crs for d in datasets if d.crs]
    geo_crs_datasets = [d for d in datasets if d.crs and d.is_geographic_crs()]
    unknown_crs_ds   = [d for d in datasets if not d.crs]

    crs_status = CRSStatus.OK

    # 未知 CRS
    if unknown_crs_ds:
        crs_status = CRSStatus.UNKNOWN
        violations.append(RuleViolation(
            rule_id    = "CRS_UNKNOWN_WARN",
            rule_set   = "crs",
            severity   = "warning",
            message    = f"数据集 {[d.id for d in unknown_crs_ds]} CRS 未知",
            dataset_id = ",".join(d.id for d in unknown_crs_ds),
        ))

    # CRS 不一致（多图层）
    unique_crs = set(c.upper() for c in crs_list if c)
    if len(unique_crs) > 1:
        crs_status = CRSStatus.CRS_MISMATCH
        violations.append(RuleViolation(
            rule_id  = "CRS_MISMATCH_BEFORE_OVERLAY",
            rule_set = "crs",
            severity = "error",
            message  = f"多图层 CRS 不一致：{list(unique_crs)}，叠加分析前需统一",
        ))
        # 前置条件：统一 CRS
        target_crs = ctx.project_context.default_crs or "EPSG:4547"
        for d in datasets:
            if d.crs and d.crs.upper() != target_crs.upper():
                preconditions.append({
                    "action": "reproject_layer",
                    "target": d.id,
                    "from_crs": d.crs,
                    "to_crs": target_crs,
                    "constraint_key": "unify_crs_before_overlay",
                })

    # 地理坐标系 + 需要距离/面积计算
    needs_metric = _task_needs_metric_crs(task_profile)
    if geo_crs_datasets and needs_metric:
        crs_status = CRSStatus.NEEDS_REPROJECTION
        for d in geo_crs_datasets:
            violations.append(RuleViolation(
                rule_id    = "CRS_BUFFER_REQUIRES_PROJECTED",
                rule_set   = "crs",
                severity   = "error",
                message    = f"数据集 {d.id} 为地理坐标系 ({d.crs})，距离/缓冲区分析前需投影",
                dataset_id = d.id,
            ))
            target_crs = ctx.project_context.default_crs or "EPSG:4547"
            preconditions.append({
                "action": "reproject_layer",
                "target": d.id,
                "from_crs": d.crs,
                "to_crs": target_crs,
                "constraint_key": "reproject_to_projected_crs_before_buffer",
            })

    return crs_status, violations, preconditions


def _task_needs_metric_crs(tp: TaskProfile) -> bool:
    """判断任务是否需要投影坐标系"""
    metric_intents = {
        AnalysisIntent.COMPARISON, AnalysisIntent.ACCESSIBILITY,
        AnalysisIntent.OPTIMIZATION, AnalysisIntent.CLUSTERING,
        AnalysisIntent.SUMMARIZATION,
    }
    if tp.task_type in metric_intents:
        return True
    metric_relations = {SpatialRelation.NEAREST, SpatialRelation.WITHIN,
                        SpatialRelation.ACCESSIBLE_FROM}
    if any(r in metric_relations for r in tp.relations):
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  几何 / 拓扑规则
# ══════════════════════════════════════════════════════════════════════════════

def _evaluate_topology(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
) -> tuple[List[RuleViolation], List[str]]:
    violations: List[RuleViolation] = []
    constraints: List[str]          = []

    datasets = ctx.datasets
    has_network = any(
        d.type.lower() in ("network", "graph") or
        (d.geometry or "").lower() in ("linestring", "multilinestring")
        for d in datasets
    )
    is_network_task = task_profile.task_type == AnalysisIntent.ACCESSIBILITY or \
        any(r == SpatialRelation.ACCESSIBLE_FROM for r in task_profile.relations)

    # 网络分析缺少网络数据
    if is_network_task and not has_network:
        violations.append(RuleViolation(
            rule_id  = "TOPO_NETWORK_REQUIRES_NETWORK_DATA",
            rule_set = "topology",
            severity = "warning",   # warning（可降级为欧氏距离）
            message  = "网络可达性分析未检测到路网数据，将降级为欧氏距离缓冲区近似",
        ))

    # 空间范围重叠检查（多图层时）
    if len(datasets) >= 2:
        overlap_status = _check_extent_overlap(datasets)
        if overlap_status == "no_overlap":
            violations.append(RuleViolation(
                rule_id  = "TOPO_EXTENT_NO_OVERLAP",
                rule_set = "topology",
                severity = "error",
                message  = "图层空间范围无重叠，叠加分析结果将为空",
            ))
            constraints.append("validate_extent_overlap")
        elif overlap_status == "partial":
            violations.append(RuleViolation(
                rule_id  = "TOPO_EXTENT_PARTIAL_OVERLAP",
                rule_set = "topology",
                severity = "warning",
                message  = "图层空间范围部分重叠，结果仅覆盖重叠区域",
            ))

    return violations, constraints


def _check_extent_overlap(datasets) -> str:
    """
    简单检查多个数据集的 extent 是否有重叠。
    返回: 'full_overlap' / 'partial' / 'no_overlap' / 'unknown'
    """
    extents = [d.extent for d in datasets if d.extent and len(d.extent) == 4]
    if len(extents) < 2:
        return "unknown"

    def overlaps(e1, e2):
        # [min_lng, min_lat, max_lng, max_lat]
        return not (e1[2] < e2[0] or e2[2] < e1[0] or
                    e1[3] < e2[1] or e2[3] < e1[1])

    all_overlap = all(
        overlaps(extents[i], extents[j])
        for i in range(len(extents))
        for j in range(i+1, len(extents))
    )
    if all_overlap:
        return "partial"   # 不做完全包含判断，统一返回 partial
    return "no_overlap"


# ══════════════════════════════════════════════════════════════════════════════
#  时序规则
# ══════════════════════════════════════════════════════════════════════════════

def _evaluate_temporal(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
) -> tuple[List[RuleViolation], List[str]]:
    violations: List[RuleViolation] = []
    constraints: List[str]          = []

    if task_profile.task_type != AnalysisIntent.CHANGE_DETECTION:
        return violations, constraints

    temporal_datasets = [d for d in ctx.datasets if d.has_temporal()]
    if len(temporal_datasets) < 2:
        violations.append(RuleViolation(
            rule_id  = "TEMPORAL_CHANGE_REQUIRES_MULTIPERIOD",
            rule_set = "temporal",
            severity = "error",
            message  = "变化检测需要至少两期数据，当前数据不满足",
        ))
        constraints.append("provide_multiperiod_data_for_change_detection")

    return violations, constraints


# ══════════════════════════════════════════════════════════════════════════════
#  尺度规则（返回 warnings 字符串列表）
# ══════════════════════════════════════════════════════════════════════════════

def _evaluate_scale(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
) -> List[str]:
    warnings: List[str] = []

    intents = {task_profile.task_type} | set(task_profile.subtask_types)

    if AnalysisIntent.COMPARISON in intents or AnalysisIntent.SUMMARIZATION in intents:
        warnings.append("result_may_be_sensitive_to_zone_definition (MAUP)")

    # buffer 相关
    if AnalysisIntent.COMPARISON in intents or AnalysisIntent.ACCESSIBILITY in intents:
        warnings.append("result_sensitive_to_buffer_radius")

    return warnings


# ══════════════════════════════════════════════════════════════════════════════
#  安全规则
# ══════════════════════════════════════════════════════════════════════════════

def _evaluate_safety(ctx: ReasoningContext) -> List[RuleViolation]:
    violations: List[RuleViolation] = []
    policy = ctx.system_policy

    if not policy.allow_unregistered_tools:
        # 仅记录策略状态，具体工具注册校验由执行层完成
        pass

    if policy.readonly_inputs:
        # 只读策略：若数据集被标记为 writable=True 则忽略，readonly 策略优先
        writable_inputs = [d for d in ctx.datasets if d.writable]
        if writable_inputs:
            violations.append(RuleViolation(
                rule_id  = "SAFETY_READONLY_INPUT",
                rule_set = "safety",
                severity = "warning",
                message  = f"系统策略要求只读，但数据集 {[d.id for d in writable_inputs]} 标记为可写",
            ))

    return violations


# ══════════════════════════════════════════════════════════════════════════════
#  方法候选选择
# ══════════════════════════════════════════════════════════════════════════════

def _select_method_candidates(task_profile: TaskProfile) -> List[MethodCandidate]:
    candidates: List[MethodCandidate] = []
    seen: set = set()

    for intent in [task_profile.task_type] + list(task_profile.subtask_types):
        for mc in _INTENT_TO_METHODS.get(intent.value, []):
            if mc.method_id not in seen:
                candidates.append(mc)
                seen.add(mc.method_id)

    return sorted(candidates, key=lambda x: x.priority)


def _infer_target_metrics(task_profile: TaskProfile) -> List[str]:
    metrics_map = {
        AnalysisIntent.COMPARISON.value:       ["count", "density", "diversity"],
        AnalysisIntent.ACCESSIBILITY.value:    ["travel_time", "coverage_ratio"],
        AnalysisIntent.CLUSTERING.value:       ["density", "hotspot_score"],
        AnalysisIntent.OPTIMIZATION.value:     ["coverage", "weighted_score"],
        AnalysisIntent.CHANGE_DETECTION.value: ["area_change", "change_rate"],
        AnalysisIntent.SUMMARIZATION.value:    ["mean", "sum", "count"],
    }
    return metrics_map.get(task_profile.task_type.value, [])
