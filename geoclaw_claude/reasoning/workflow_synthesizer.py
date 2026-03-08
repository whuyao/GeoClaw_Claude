# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.workflow_synthesizer
=====================================
Workflow Synthesizer — 将所有推理层的输出组装为 SpatialReasoningResult。

职责：
  - 将 TaskProfile / RuleEngineOutput / ValidationResult / LLMReasoningOutput
    组装成统一的 SpatialReasoningResult 对象
  - Phase 1：根据规则层 method_candidates 生成 WorkflowPlan
  - Phase 2：优先使用 LLM 推理输出的 workflow

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    ArtifactSpec,
    CRSStatus,
    InputAssessment,
    LLMReasoningOutput,
    OutputType,
    Provenance,
    ReasoningContext,
    ReasoningSummary,
    RuleEngineOutput,
    SpatialReasoningResult,
    TaskProfile,
    TemporalStatus,
    ValidationResult,
    WorkflowPlan,
    WorkflowStep,
)

# SRE 引擎版本
_SRE_VERSION = "sre-0.2-phase2"


def synthesize_workflow(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    validation: ValidationResult,
    llm_output: Optional[LLMReasoningOutput],
) -> SpatialReasoningResult:
    """
    组装 SpatialReasoningResult。

    Args:
        ctx         : 推理上下文
        task_profile: 任务分类结果
        rule_output : 规则层输出
        validation  : 校验结果
        llm_output  : LLM 推理输出（Phase 1 为 None）

    Returns:
        SpatialReasoningResult
    """
    # 1. 输入评估
    input_assessment = _build_input_assessment(ctx, rule_output)

    # 2. 推理摘要
    reasoning_summary = _build_reasoning_summary(task_profile, rule_output, llm_output)

    # 3. 工作流计划
    workflow_plan = _build_workflow_plan(ctx, task_profile, rule_output, llm_output)

    # 4. 预期产物
    artifacts = _build_artifacts(task_profile)

    # 5. 溯源
    provenance = _build_provenance(ctx, llm_output)

    return SpatialReasoningResult(
        task_profile      = task_profile,
        input_assessment  = input_assessment,
        reasoning_summary = reasoning_summary,
        workflow_plan     = workflow_plan,
        validation        = validation,
        artifacts         = artifacts,
        provenance        = provenance,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  InputAssessment
# ══════════════════════════════════════════════════════════════════════════════

def _build_input_assessment(
    ctx: ReasoningContext,
    rule_output: RuleEngineOutput,
) -> InputAssessment:
    datasets     = ctx.datasets
    dataset_ids  = [d.id for d in datasets]

    # Extent overlap status
    from geoclaw_claude.reasoning.rule_engine import _check_extent_overlap
    extent_raw = _check_extent_overlap(datasets) if len(datasets) >= 2 else "unknown"
    extent_status_map = {
        "full_overlap":    "overlap_confirmed",
        "partial":         "overlap_confirmed",   # partial 也算可用
        "no_overlap":      "no_overlap",
        "unknown":         "unknown",
    }
    extent_status = extent_status_map.get(extent_raw, "unknown")

    # Temporal status
    temporal_ds = [d for d in datasets if d.has_temporal()]
    if len(temporal_ds) >= 2:
        temporal_status = TemporalStatus.MULTI_PERIOD
    elif len(temporal_ds) == 1:
        temporal_status = TemporalStatus.SINGLE_PERIOD
    else:
        temporal_status = TemporalStatus.NO_TEMPORAL

    # Data quality notes
    quality_notes: List[str] = []
    if any("poi" in d.id.lower() for d in datasets):
        quality_notes.append("POI 数据可能存在类别采样偏差")
    if any(not d.crs for d in datasets):
        quality_notes.append("部分数据集 CRS 未知，建议确认后再分析")

    # Missing data
    missing: List[str] = []
    for err in rule_output.violations:
        if "网络" in err.message or "network" in err.message.lower():
            missing.append("road_network_data")
        if "两期" in err.message or "multi-period" in err.message.lower():
            missing.append("multiperiod_temporal_data")

    return InputAssessment(
        datasets_used      = dataset_ids,
        crs_status         = rule_output.crs_status,
        extent_status      = extent_status,
        temporal_status    = temporal_status,
        data_quality_notes = quality_notes,
        missing_data       = list(dict.fromkeys(missing)),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ReasoningSummary
# ══════════════════════════════════════════════════════════════════════════════

def _build_reasoning_summary(
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_output: Optional[LLMReasoningOutput],
) -> ReasoningSummary:
    # Phase 2：使用 LLM 输出
    if llm_output is not None:
        return ReasoningSummary(
            primary_method             = llm_output.primary_method,
            secondary_methods          = llm_output.secondary_methods,
            method_selection_rationale = llm_output.method_rationale,
            assumptions                = llm_output.assumptions,
            limitations                = llm_output.limitations,
            uncertainty_level          = llm_output.uncertainty_level,
        )

    # Phase 1：从规则层 method_candidates 推断
    candidates = rule_output.method_candidates
    primary    = candidates[0].method_id if candidates else ""
    secondary  = [c.method_id for c in candidates[1:3]]

    # 生成简要 rationale
    rationale  = _generate_phase1_rationale(task_profile, rule_output)
    assumptions, limitations = _generate_phase1_caveats(task_profile, rule_output)

    return ReasoningSummary(
        primary_method             = primary,
        secondary_methods          = secondary,
        method_selection_rationale = rationale,
        assumptions                = assumptions,
        limitations                = limitations,
        uncertainty_level          = "medium",
    )


def _generate_phase1_rationale(
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
) -> List[str]:
    rationale = []
    task = task_profile.task_type

    if task == AnalysisIntent.COMPARISON:
        rationale.append("缓冲区聚合统计适合站点级别的空间对比分析，可解释性强")
        rationale.append("核密度估计可作为补充可视化，但不应作为主分析链")
    elif task == AnalysisIntent.ACCESSIBILITY:
        if any("network" in v.message for v in rule_output.violations):
            rationale.append("未检测到路网数据，采用欧氏距离缓冲区近似可达性")
        else:
            rationale.append("基于路网的服务区分析可更准确反映实际可达性")
    elif task == AnalysisIntent.OPTIMIZATION:
        rationale.append("加权叠加选址结合多准则评价，适合设施配置优化")
    elif task == AnalysisIntent.CLUSTERING:
        rationale.append("核密度估计适合揭示空间集聚模式和热点区域")
    elif task == AnalysisIntent.CHANGE_DETECTION:
        rationale.append("时序叠加分析可量化空间格局变化")
    else:
        rationale.append(f"基于任务类型 {task.value} 选择标准分析方法")

    return rationale


def _generate_phase1_caveats(
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
) -> tuple[List[str], List[str]]:
    assumptions = []
    limitations = []

    task = task_profile.task_type
    if task == AnalysisIntent.COMPARISON:
        assumptions.append("POI 数量/密度作为商业活跃度的空间代理指标")
        limitations.append("缓冲区半径选择影响分析结果，建议多半径敏感性测试")
        limitations.append("POI 数据可能存在类别偏差，不能直接反映实际经济产出")
    elif task == AnalysisIntent.ACCESSIBILITY:
        assumptions.append("研究区内交通网络可作为可达性计算基础")
        limitations.append("欧氏距离近似低估了实际出行时间")
    elif task == AnalysisIntent.CHANGE_DETECTION:
        assumptions.append("两期数据的时间节点具有可比性")
        limitations.append("分类误差可能传递到变化检测结果")

    return assumptions, limitations


# ══════════════════════════════════════════════════════════════════════════════
#  WorkflowPlan
# ══════════════════════════════════════════════════════════════════════════════

def _build_workflow_plan(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_output: Optional[LLMReasoningOutput],
) -> WorkflowPlan:
    # 前置条件（CRS 重投影等）
    preconditions = rule_output.preconditions

    # Phase 2：若 LLM 给出了 primary_method，用它覆盖 rule_candidates 的首选
    candidates = rule_output.method_candidates
    if llm_output is not None and llm_output.primary_method:
        candidates = _inject_llm_method(candidates, llm_output)

    steps         = _generate_steps(task_profile, candidates, ctx)
    optional_steps= _generate_optional_steps(task_profile, candidates, ctx)

    # Phase 2：将 LLM secondary_methods 加入 optional_steps（去重）
    if llm_output is not None:
        existing_optional_ids = {s.method for s in optional_steps}
        for sec_method in llm_output.secondary_methods:
            if sec_method and sec_method not in existing_optional_ids:
                optional_steps.append(WorkflowStep(
                    step_id        = f"o{len(optional_steps)+1}",
                    operation_type = "secondary_analysis",
                    method         = sec_method,
                    inputs         = [d.id for d in ctx.datasets],
                    parameters     = {},
                    expected_output= f"{sec_method}_output",
                    optional       = True,
                    notes          = "LLM 推荐的辅助分析方法",
                ))

    return WorkflowPlan(
        preconditions  = preconditions,
        steps          = steps,
        optional_steps = optional_steps,
    )


def _inject_llm_method(
    candidates: List,
    llm_output: LLMReasoningOutput,
) -> List:
    """
    将 LLM 推荐的 primary_method 注入到 candidates 首位（Phase 2）。

    若 primary_method 已在 candidates 中，则将其移到最前；
    若不在，则新建一个 MethodCandidate 插入首位。
    """
    from geoclaw_claude.reasoning.schemas import MethodCandidate

    primary = llm_output.primary_method
    # 查找是否已存在
    existing = [mc for mc in candidates if mc.method_id == primary]
    others   = [mc for mc in candidates if mc.method_id != primary]

    if existing:
        # 已存在，调整 priority=0 移到首位
        top = MethodCandidate(
            method_id   = existing[0].method_id,
            category    = existing[0].category,
            description = existing[0].description,
            priority    = 0,
        )
    else:
        # 不存在，新建一个（category 取第一个 candidate 的）
        top = MethodCandidate(
            method_id   = primary,
            category    = candidates[0].category if candidates else "unknown",
            description = f"LLM 推荐方法: {primary}",
            priority    = 0,
        )

    return [top] + others


def _generate_steps(
    task_profile: TaskProfile,
    candidates: List,
    ctx: ReasoningContext,
) -> List[WorkflowStep]:
    """根据方法候选和任务类型生成主工作流步骤"""
    steps: List[WorkflowStep] = []
    dataset_ids = [d.id for d in ctx.datasets]
    task = task_profile.task_type

    if task == AnalysisIntent.COMPARISON and candidates:
        # 步骤 1：多环缓冲区
        steps.append(WorkflowStep(
            step_id        = "s1",
            operation_type = "buffer",
            method         = "multi_ring_buffer",
            inputs         = dataset_ids[:1],   # 第一个点图层
            parameters     = {"radii": [300, 500, 800]},
            expected_output= "station_buffers",
            notes          = "缓冲半径可根据研究区尺度调整",
        ))
        # 步骤 2：空间连接统计
        steps.append(WorkflowStep(
            step_id        = "s2",
            operation_type = "spatial_join_summary",
            method         = "join_points_within_polygons",
            inputs         = ["station_buffers"] + dataset_ids[1:2],
            parameters     = {"summary_fields": ["count", "category_diversity"]},
            expected_output= "buffer_summary",
        ))
        # 步骤 3：比较排名
        steps.append(WorkflowStep(
            step_id        = "s3",
            operation_type = "comparative_analysis",
            method         = "rank_and_compare",
            inputs         = ["buffer_summary"],
            parameters     = {},
            expected_output= "comparison_table",
        ))

    elif task == AnalysisIntent.ACCESSIBILITY and candidates:
        steps.append(WorkflowStep(
            step_id        = "s1",
            operation_type = "accessibility",
            method         = candidates[0].method_id,
            inputs         = dataset_ids,
            parameters     = {"travel_time_minutes": [5, 10, 15]},
            expected_output= "service_areas",
        ))
        steps.append(WorkflowStep(
            step_id        = "s2",
            operation_type = "coverage_statistics",
            method         = "population_coverage",
            inputs         = ["service_areas"],
            parameters     = {},
            expected_output= "coverage_summary",
        ))

    elif task == AnalysisIntent.OPTIMIZATION and candidates:
        steps.append(WorkflowStep(
            step_id        = "s1",
            operation_type = "candidate_filtering",
            method         = "constrained_candidate_filter",
            inputs         = dataset_ids,
            parameters     = {},
            expected_output= "candidate_points",
        ))
        steps.append(WorkflowStep(
            step_id        = "s2",
            operation_type = "site_scoring",
            method         = "weighted_overlay",
            inputs         = ["candidate_points"],
            parameters     = {"weights": {}},
            expected_output= "scored_candidates",
        ))

    elif task == AnalysisIntent.CLUSTERING and candidates:
        steps.append(WorkflowStep(
            step_id        = "s1",
            operation_type = "density_estimation",
            method         = "kernel_density_estimation",
            inputs         = dataset_ids,
            parameters     = {"bandwidth": "auto"},
            expected_output= "density_surface",
        ))

    elif task == AnalysisIntent.CHANGE_DETECTION and candidates:
        steps.append(WorkflowStep(
            step_id        = "s1",
            operation_type = "temporal_overlay",
            method         = "temporal_overlay",
            inputs         = dataset_ids,
            parameters     = {},
            expected_output= "change_layer",
        ))

    elif task == AnalysisIntent.SUMMARIZATION and candidates:
        steps.append(WorkflowStep(
            step_id        = "s1",
            operation_type = "zonal_statistics",
            method         = "zonal_statistics",
            inputs         = dataset_ids,
            parameters     = {"stats": ["mean", "sum", "count"]},
            expected_output= "zonal_summary",
        ))

    else:
        # 通用兜底
        if candidates:
            steps.append(WorkflowStep(
                step_id        = "s1",
                operation_type = candidates[0].category,
                method         = candidates[0].method_id,
                inputs         = dataset_ids,
                parameters     = {},
                expected_output= "analysis_result",
            ))

    # 最后一步：制图输出（若用户要求地图）
    if OutputType.MAP in task_profile.output_intent:
        steps.append(WorkflowStep(
            step_id        = f"s{len(steps)+1}",
            operation_type = "cartography",
            method         = "static_map_render",
            inputs         = [steps[-1].expected_output] if steps else dataset_ids,
            parameters     = {"style": "choropleth"},
            expected_output= "output_map.png",
        ))

    return steps


def _generate_optional_steps(
    task_profile: TaskProfile,
    candidates: List,
    ctx: ReasoningContext,
) -> List[WorkflowStep]:
    """生成可选补充步骤"""
    optional: List[WorkflowStep] = []
    dataset_ids = [d.id for d in ctx.datasets]
    task = task_profile.task_type

    # COMPARISON：可选核密度对比
    if task == AnalysisIntent.COMPARISON:
        optional.append(WorkflowStep(
            step_id        = "o1",
            operation_type = "density_visualization",
            method         = "kernel_density_estimation",
            inputs         = dataset_ids,
            parameters     = {},
            expected_output= "density_surface_optional",
            optional       = True,
            notes          = "可视化补充，非主分析链",
        ))

    # ACCESSIBILITY：可选交互式地图
    if OutputType.MAP in task_profile.output_intent:
        optional.append(WorkflowStep(
            step_id        = "o2",
            operation_type = "interactive_map",
            method         = "folium_interactive_map",
            inputs         = [],
            parameters     = {},
            expected_output= "interactive_map.html",
            optional       = True,
            notes          = "可选交互式地图输出",
        ))

    return optional


# ══════════════════════════════════════════════════════════════════════════════
#  Artifacts
# ══════════════════════════════════════════════════════════════════════════════

def _build_artifacts(task_profile: TaskProfile) -> List[ArtifactSpec]:
    artifacts: List[ArtifactSpec] = []
    task = task_profile.task_type

    # GeoFile
    artifact_names = {
        AnalysisIntent.COMPARISON:       "analysis_buffers.gpkg",
        AnalysisIntent.ACCESSIBILITY:    "service_areas.gpkg",
        AnalysisIntent.OPTIMIZATION:     "candidate_sites.gpkg",
        AnalysisIntent.CLUSTERING:       "density_surface.tif",
        AnalysisIntent.CHANGE_DETECTION: "change_layer.gpkg",
        AnalysisIntent.SUMMARIZATION:    "zonal_summary.gpkg",
    }
    geofile_name = artifact_names.get(task, "analysis_result.gpkg")
    artifacts.append(ArtifactSpec(type="vector", name=geofile_name))

    # Table
    if task in (AnalysisIntent.COMPARISON, AnalysisIntent.SUMMARIZATION,
                AnalysisIntent.OPTIMIZATION):
        artifacts.append(ArtifactSpec(type="table", name="analysis_summary.csv"))

    # Map
    if OutputType.MAP in task_profile.output_intent:
        artifacts.append(ArtifactSpec(type="map", name="analysis_map.png"))

    # Report
    if OutputType.REPORT in task_profile.output_intent:
        artifacts.append(ArtifactSpec(type="report", name="analysis_report.md"))

    return artifacts


# ══════════════════════════════════════════════════════════════════════════════
#  Provenance
# ══════════════════════════════════════════════════════════════════════════════

def _build_provenance(
    ctx: ReasoningContext,
    llm_output: Optional[LLMReasoningOutput],
) -> Provenance:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return Provenance(
        engine_version      = _SRE_VERSION,
        reasoning_timestamp = ts,
        source_query        = ctx.query,
        rule_sets_used      = ["geo_rules_v1"],
        llm_model           = (llm_output.raw_response or "")[:20] if llm_output else None,
    )
