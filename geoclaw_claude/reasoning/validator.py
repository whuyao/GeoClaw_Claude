# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.validator
=====================================
校验层（Validation Layer）。

Phase 1 实现两类校验（文档第六章）：
  6.1 Constraint Validation  — 硬约束违规检查
  6.2 Data Feasibility       — 数据能否支持推荐方法

Phase 2 将增加：
  6.3 Reasoning Consistency  — LLM 方法选择与任务目标一致性
  6.4 Uncertainty & Caveat   — 局限说明完整性

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    GeoEntityType,
    LLMReasoningOutput,
    ReasoningContext,
    RuleEngineOutput,
    SpatialRelation,
    TaskProfile,
    ValidationResult,
    ValidationStatus,
    ValidationWarning,
)


def validate_reasoning(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_output: Optional[LLMReasoningOutput],
) -> ValidationResult:
    """
    执行完整校验流程，返回 ValidationResult。

    Phase 1：Constraint Validation + Data Feasibility Validation
    Phase 2：+Reasoning Consistency + Uncertainty Caveat（当 llm_output 非 None 时启用）

    Args:
        ctx         : 推理上下文
        task_profile: 任务类型识别结果
        rule_output : 规则层输出
        llm_output  : LLM 推理输出（Phase 1 为 None）

    Returns:
        ValidationResult
    """
    blocking_errors:     List[str]                = []
    warnings:            List[ValidationWarning]  = []
    required_precond:    List[str]                = []
    revisions_applied:   List[str]                = []

    # ── 6.1 Constraint Validation ─────────────────────────────────────────────
    _validate_constraints(rule_output, blocking_errors, warnings, required_precond)

    # ── 6.2 Data Feasibility Validation ──────────────────────────────────────
    _validate_data_feasibility(ctx, task_profile, rule_output,
                               blocking_errors, warnings)

    # ── 6.3 Reasoning Consistency（Phase 2，llm_output 有值时执行）─────────────
    if llm_output is not None:
        _validate_reasoning_consistency(task_profile, llm_output,
                                        warnings, revisions_applied)

    # ── 6.4 Uncertainty & Caveat（Phase 2）────────────────────────────────────
    if llm_output is not None:
        _validate_uncertainty_caveat(task_profile, rule_output, llm_output, warnings)

    # ── 自动修正：将 CRS preconditions 加入 required_preconditions ─────────────
    for pc in rule_output.preconditions:
        desc = f"{pc.get('action','?')}({pc.get('target','?')} → {pc.get('to_crs','?')})"
        if desc not in required_precond:
            required_precond.append(desc)
            if pc.get("constraint_key") == "reproject_to_projected_crs_before_buffer":
                revisions_applied.append(
                    f"buffer_operation_requires_reprojection_of_{pc.get('target','?')}")

    # ── 策略合规状态 ────────────────────────────────────────────────────────
    policy = ctx.system_policy
    policy_compliance = {
        "readonly_inputs":          policy.readonly_inputs,
        "workspace_output_only":    policy.require_output_workspace,
        "registered_tools_only":    not policy.allow_unregistered_tools,
    }

    # ── 最终状态 ────────────────────────────────────────────────────────────
    if blocking_errors:
        status = ValidationStatus.FAIL
    elif warnings:
        status = ValidationStatus.PASS_WITH_WARNINGS
    else:
        status = ValidationStatus.PASS

    return ValidationResult(
        status                = status,
        blocking_errors       = blocking_errors,
        warnings              = warnings,
        required_preconditions= required_precond,
        revisions_applied     = revisions_applied,
        policy_compliance     = policy_compliance,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  6.1 Constraint Validation
# ══════════════════════════════════════════════════════════════════════════════

def _validate_constraints(
    rule_output: RuleEngineOutput,
    blocking_errors: List[str],
    warnings: List[ValidationWarning],
    required_precond: List[str],
) -> None:
    """将规则层 violations 转化为 blocking_errors 或 warnings"""
    for v in rule_output.violations:
        if v.severity == "error":
            blocking_errors.append(f"[{v.rule_id}] {v.message}")
        elif v.severity == "warning":
            warnings.append(ValidationWarning(
                code    = v.rule_id,
                message = v.message,
                detail  = f"rule_set={v.rule_set}",
            ))

    # 尺度警告
    for w in rule_output.warnings:
        if "MAUP" in w:
            warnings.append(ValidationWarning(
                code    = "MAUP_WARNING",
                message = "行政区聚合分析可能受 MAUP 影响，结果对分区方案敏感",
                detail  = w,
            ))
        elif "buffer_radius" in w:
            warnings.append(ValidationWarning(
                code    = "BUFFER_RADIUS_SENSITIVITY",
                message = "缓冲区分析结果对缓冲半径选择较敏感",
                detail  = w,
            ))


# ══════════════════════════════════════════════════════════════════════════════
#  6.2 Data Feasibility Validation
# ══════════════════════════════════════════════════════════════════════════════

def _validate_data_feasibility(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    blocking_errors: List[str],
    warnings: List[ValidationWarning],
) -> None:
    """检查当前数据是否能够支持推荐方法"""
    datasets   = ctx.datasets
    task_type  = task_profile.task_type

    dataset_types = {d.type.lower() for d in datasets}
    geom_types    = {(d.geometry or "").lower() for d in datasets}

    # 可达性分析：推荐 network，缺少时降级
    if task_type == AnalysisIntent.ACCESSIBILITY:
        has_network = (
            "network" in dataset_types or
            "linestring" in geom_types or
            "multilinestring" in geom_types
        )
        if not has_network:
            warnings.append(ValidationWarning(
                code    = "ACCESSIBILITY_NO_NETWORK_DATA",
                message = "推荐网络可达性分析，但未提供路网数据，将降级为欧氏距离近似",
                detail  = "Provide a road network dataset for accurate accessibility analysis",
            ))

    # 变化检测：需要多期数据
    if task_type == AnalysisIntent.CHANGE_DETECTION:
        temporal_ds = [d for d in datasets if d.has_temporal()]
        if len(temporal_ds) < 2:
            blocking_errors.append(
                "[FEASIBILITY_CHANGE_DETECTION] 变化检测需要至少两期时序数据，当前数据不足"
            )

    # 分区统计：需要 polygon
    if task_type in (AnalysisIntent.SUMMARIZATION, AnalysisIntent.COMPARISON):
        if "polygon" not in geom_types and "multipolygon" not in geom_types:
            # 若有 point + point，可用缓冲区生成 polygon，不阻断
            warnings.append(ValidationWarning(
                code    = "FEASIBILITY_NO_POLYGON_ZONE",
                message = "未检测到面要素（polygon）。若需分区统计，将使用缓冲区生成统计单元",
                detail  = "Buffer zones will be auto-generated from point layers",
            ))

    # 选址优化：需要至少一个 point/polygon 候选层
    if task_type == AnalysisIntent.OPTIMIZATION:
        if not datasets:
            blocking_errors.append(
                "[FEASIBILITY_SITE_SELECTION] 选址分析需要候选设施点或研究区数据"
            )


# ══════════════════════════════════════════════════════════════════════════════
#  6.3 Reasoning Consistency（Phase 2，预留接口）
# ══════════════════════════════════════════════════════════════════════════════

def _validate_reasoning_consistency(
    task_profile: TaskProfile,
    llm_output: LLMReasoningOutput,
    warnings: List[ValidationWarning],
    revisions_applied: List[str],
) -> None:
    """
    检查 LLM 选择的方法是否与任务目标一致（文档 6.3）。
    Phase 2 实现，Phase 1 中 llm_output 为 None，不会进入此函数。
    """
    # 用户要比较站点周边差异，但 LLM 选了 citywide KDE 作为主方法
    if (task_profile.task_type == AnalysisIntent.COMPARISON and
            "kernel_density" in llm_output.primary_method.lower() and
            "buffer" not in llm_output.primary_method.lower()):
        warnings.append(ValidationWarning(
            code    = "CONSISTENCY_METHOD_MISMATCH",
            message = "任务目标是比较各站点差异，但主方法为全局核密度，建议改为缓冲区统计",
        ))
        revisions_applied.append("suggest_buffer_summary_as_primary_method")

    # 用户要选址优化，但 workflow 只有 buffer
    if (task_profile.task_type == AnalysisIntent.OPTIMIZATION and
            "optimization" not in llm_output.primary_method.lower() and
            "allocation" not in llm_output.primary_method.lower()):
        warnings.append(ValidationWarning(
            code    = "CONSISTENCY_MISSING_OPTIMIZATION_STEP",
            message = "选址任务未包含优化/评分环节，结果仅为可视化",
        ))


# ══════════════════════════════════════════════════════════════════════════════
#  6.4 Uncertainty & Caveat（Phase 2，预留接口）
# ══════════════════════════════════════════════════════════════════════════════

def _validate_uncertainty_caveat(
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_output: LLMReasoningOutput,
    warnings: List[ValidationWarning],
) -> None:
    """
    检查是否补充了必要的局限说明（文档 6.4）。
    Phase 2 实现。
    """
    limitations_text = " ".join(llm_output.limitations).lower()

    # 缓冲区分析：是否说明了半径敏感性
    if ("buffer" in llm_output.primary_method.lower() and
            "radius" not in limitations_text and "半径" not in limitations_text):
        warnings.append(ValidationWarning(
            code    = "CAVEAT_MISSING_RADIUS_SENSITIVITY",
            message = "缓冲区分析应说明半径选择对结果的影响",
        ))

    # POI 数据：是否提示偏差
    datasets_ids = " ".join(rule_output.resolved_entities).lower()
    if ("poi" in datasets_ids and
            "bias" not in limitations_text and "偏差" not in limitations_text):
        warnings.append(ValidationWarning(
            code    = "CAVEAT_MISSING_POI_BIAS",
            message = "POI 数据分析应提示数据采样偏差可能影响结果",
        ))
