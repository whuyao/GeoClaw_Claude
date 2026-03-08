# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.uncertainty_assessor
==============================================
Phase 3：高级地理推理增强模块。

实现文档 Phase 3 目标：
  1. uncertainty_score 量化（0-1 浮点数，Rule-based）
  2. parameter_sensitivity_hints（关键参数敏感性说明）
  3. exploratory vs causal 分析模式区分
  4. MAUP 风险评估增强
  5. scale_effects_notes（尺度效应说明）

设计原则：
  - 纯 Rule-based，不调用 LLM，保证离线稳定
  - 输出结果注入 ReasoningSummary（由 workflow_synthesizer 调用）
  - Phase 2 LLMReasoningOutput 可选，有时进一步细化评估

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    AnalysisMode,
    GeoEntityType,
    LLMReasoningOutput,
    ParameterSensitivityHint,
    ReasoningContext,
    RuleEngineOutput,
    TaskProfile,
    TemporalStatus,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  输出结构
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class UncertaintyAssessment:
    """Phase 3 不确定性评估结果，注入 ReasoningSummary"""
    uncertainty_score:       float                         = -1.0
    analysis_mode:           str                           = AnalysisMode.UNKNOWN.value
    parameter_sensitivity:   List[ParameterSensitivityHint] = field(default_factory=list)
    maup_risk:               str                           = "unknown"
    scale_effects_notes:     List[str]                     = field(default_factory=list)
    uncertainty_components:  dict                          = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
#  主接口
# ══════════════════════════════════════════════════════════════════════════════

def assess_uncertainty(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_output: Optional[LLMReasoningOutput] = None,
) -> UncertaintyAssessment:
    """
    Phase 3 不确定性评估主函数。

    Args:
        ctx          : 推理上下文
        task_profile : 任务分类结果
        rule_output  : 规则层输出
        llm_output   : LLM 推理输出（可选，用于进一步细化）

    Returns:
        UncertaintyAssessment
    """
    result = UncertaintyAssessment()

    # 1. 分析模式识别
    result.analysis_mode = _classify_analysis_mode(ctx, task_profile, llm_output)

    # 2. 不确定性评分
    score_components = _compute_uncertainty_components(ctx, task_profile, rule_output, llm_output)
    result.uncertainty_score = _aggregate_uncertainty_score(score_components)
    result.uncertainty_components = score_components

    # 3. 参数敏感性说明
    result.parameter_sensitivity = _build_parameter_sensitivity(
        task_profile, rule_output, llm_output
    )

    # 4. MAUP 风险评估
    result.maup_risk = _assess_maup_risk(ctx, task_profile)

    # 5. 尺度效应说明
    result.scale_effects_notes = _build_scale_effects_notes(ctx, task_profile, rule_output)

    logger.info(
        f"UncertaintyAssessor: mode={result.analysis_mode}, "
        f"score={result.uncertainty_score:.2f}, maup={result.maup_risk}"
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  1. 分析模式识别（exploratory vs causal）
# ══════════════════════════════════════════════════════════════════════════════

# 探索性关键词
_EXPLORATORY_KEYWORDS = [
    "探索", "发现", "规律", "初步", "试探", "看看", "了解", "概况",
    "explore", "discover", "pattern", "preliminary", "initial", "overview",
]

# 因果/验证性关键词
_CAUSAL_KEYWORDS = [
    "影响", "因果", "原因", "导致", "效应", "控制变量", "因素", "机制",
    "cause", "effect", "impact", "causal", "confound", "mechanism", "driver",
]

_CONFIRMATORY_KEYWORDS = [
    "验证", "证明", "检验", "假设", "显著性", "回归",
    "verify", "validate", "test", "hypothesis", "significance", "regression",
]

_DESCRIPTIVE_KEYWORDS = [
    "描述", "展示", "可视化", "地图", "分布", "概述", "汇报",
    "describe", "visualize", "display", "map", "distribution", "summary",
]


def _classify_analysis_mode(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    llm_output: Optional[LLMReasoningOutput],
) -> str:
    """规则推断分析模式（exploratory/confirmatory/causal/descriptive）"""
    query_lower = (ctx.query or "").lower()

    # 优先级：causal > confirmatory > exploratory > descriptive
    causal_score = sum(1 for kw in _CAUSAL_KEYWORDS if kw.lower() in query_lower)
    confirm_score = sum(1 for kw in _CONFIRMATORY_KEYWORDS if kw.lower() in query_lower)
    explore_score = sum(1 for kw in _EXPLORATORY_KEYWORDS if kw.lower() in query_lower)
    describ_score = sum(1 for kw in _DESCRIPTIVE_KEYWORDS if kw.lower() in query_lower)

    # 任务意图补充：change_detection / prediction → exploratory / causal
    task = task_profile.task_type
    if task == AnalysisIntent.CHANGE_DETECTION:
        explore_score += 1
    elif task == AnalysisIntent.PREDICTION:
        causal_score += 1
    elif task in [AnalysisIntent.SUMMARIZATION, AnalysisIntent.COMPARISON]:
        describ_score += 1
    elif task == AnalysisIntent.EXPLANATION:
        causal_score += 1

    # LLM 输出辅助
    if llm_output:
        rationale_text = " ".join(llm_output.method_rationale + [llm_output.explanation]).lower()
        if any(kw in rationale_text for kw in ["causal", "因果", "confound", "regression"]):
            causal_score += 2
        if any(kw in rationale_text for kw in ["exploratory", "探索", "pattern", "initial"]):
            explore_score += 1

    scores = {
        AnalysisMode.CAUSAL.value:        causal_score,
        AnalysisMode.CONFIRMATORY.value:  confirm_score,
        AnalysisMode.EXPLORATORY.value:   explore_score,
        AnalysisMode.DESCRIPTIVE.value:   describ_score,
    }

    best_mode = max(scores, key=scores.get)
    # 如果都是 0，默认 exploratory（最保守的假设）
    if scores[best_mode] == 0:
        return AnalysisMode.EXPLORATORY.value

    return best_mode


# ══════════════════════════════════════════════════════════════════════════════
#  2. 不确定性评分量化
# ══════════════════════════════════════════════════════════════════════════════

def _compute_uncertainty_components(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_output: Optional[LLMReasoningOutput],
) -> dict:
    """
    计算各维度不确定性分量（0-1）。

    维度：
      data_quality     — 数据质量不确定性
      method_choice    — 方法选择不确定性（参数敏感性）
      spatial_scale    — 空间尺度不确定性（MAUP/分辨率）
      temporal         — 时序不确定性
      model_assumptions — 模型假设不确定性（因果推断 vs 探索）
    """
    components = {}

    # ── 数据质量 ──────────────────────────────────────────────────────────────
    data_score = 0.0
    ds_list = ctx.datasets
    if any(not d.crs for d in ds_list):
        data_score += 0.3
    if any(d.is_geographic_crs() for d in ds_list):
        data_score += 0.2
    if any("poi" in d.id.lower() for d in ds_list):
        data_score += 0.2  # POI 数据采样偏差
    if any(not d.attributes for d in ds_list):
        data_score += 0.1
    components["data_quality"] = min(data_score, 1.0)

    # ── 方法选择 ──────────────────────────────────────────────────────────────
    method_score = 0.0
    task = task_profile.task_type
    # 高参数敏感度任务
    if task in [AnalysisIntent.CLUSTERING, AnalysisIntent.CHANGE_DETECTION]:
        method_score += 0.4
    elif task in [AnalysisIntent.ACCESSIBILITY, AnalysisIntent.OPTIMIZATION]:
        method_score += 0.3
    elif task == AnalysisIntent.COMPARISON:
        method_score += 0.2
    # CRS 问题增加方法不确定性
    from geoclaw_claude.reasoning.schemas import CRSStatus
    if rule_output.crs_status == CRSStatus.NEEDS_REPROJECTION:
        method_score += 0.1
    if rule_output.crs_status == CRSStatus.CRS_MISMATCH:
        method_score += 0.2
    # 候选方法多 → 方法选择不确定性高
    if len(rule_output.method_candidates) >= 4:
        method_score += 0.15
    components["method_choice"] = min(method_score, 1.0)

    # ── 空间尺度 ──────────────────────────────────────────────────────────────
    scale_score = 0.0
    if any(isinstance(e, str) and "region" in e.lower()
           for e in [str(e) for e in task_profile.entities]):
        scale_score += 0.3  # 行政区分析 → MAUP
    if task in [AnalysisIntent.CLUSTERING, AnalysisIntent.SUMMARIZATION]:
        scale_score += 0.2
    # 多个 extent 大小差异大 → 尺度不匹配
    extents = [d.extent for d in ds_list if d.extent and len(d.extent) == 4]
    if len(extents) >= 2:
        areas = [(e[2]-e[0])*(e[3]-e[1]) for e in extents]
        if areas and max(areas) / max(min(areas), 1e-9) > 10:
            scale_score += 0.2
    components["spatial_scale"] = min(scale_score, 1.0)

    # ── 时序 ──────────────────────────────────────────────────────────────────
    temporal_score = 0.0
    temporal_ds = [d for d in ds_list if d.has_temporal()]
    if task == AnalysisIntent.CHANGE_DETECTION:
        if len(temporal_ds) < 2:
            temporal_score += 0.5  # 变化检测但单期数据
        else:
            temporal_score += 0.1
    elif len(temporal_ds) == 1:
        temporal_score += 0.1
    components["temporal"] = min(temporal_score, 1.0)

    # ── 模型假设 ──────────────────────────────────────────────────────────────
    model_score = 0.0
    analysis_mode = _classify_analysis_mode(ctx, task_profile, llm_output)
    if analysis_mode == AnalysisMode.CAUSAL.value:
        model_score = 0.6  # 因果推断假设风险最高
    elif analysis_mode == AnalysisMode.CONFIRMATORY.value:
        model_score = 0.3
    elif analysis_mode == AnalysisMode.EXPLORATORY.value:
        model_score = 0.15
    else:
        model_score = 0.05
    components["model_assumptions"] = model_score

    return components


def _aggregate_uncertainty_score(components: dict) -> float:
    """
    将分量聚合为综合不确定性得分（0-1）。

    加权平均：
      data_quality     × 0.25
      method_choice    × 0.25
      spatial_scale    × 0.20
      temporal         × 0.15
      model_assumptions × 0.15
    """
    weights = {
        "data_quality":      0.25,
        "method_choice":     0.25,
        "spatial_scale":     0.20,
        "temporal":          0.15,
        "model_assumptions": 0.15,
    }
    total = sum(components.get(k, 0.0) * w for k, w in weights.items())
    return round(min(total, 1.0), 3)


def uncertainty_score_to_level(score: float) -> str:
    """将数值评分转换为语言标签"""
    if score < 0:
        return "unknown"
    if score < 0.25:
        return "low"
    if score < 0.55:
        return "medium"
    return "high"


# ══════════════════════════════════════════════════════════════════════════════
#  3. 参数敏感性说明
# ══════════════════════════════════════════════════════════════════════════════

def _build_parameter_sensitivity(
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_output: Optional[LLMReasoningOutput],
) -> List[ParameterSensitivityHint]:
    """
    为分析任务中的关键参数生成敏感性说明。

    覆盖：缓冲半径、带宽、覆盖半径、权重、时间间隔、出行时间、分辨率
    """
    hints: List[ParameterSensitivityHint] = []
    task = task_profile.task_type

    # 主方法（来自 LLM 或 rule_output）
    primary_method = ""
    if llm_output and llm_output.primary_method:
        primary_method = llm_output.primary_method.lower()
    elif rule_output.method_candidates:
        primary_method = rule_output.method_candidates[0].method_id.lower()

    # ── 缓冲区相关 ─────────────────────────────────────────────────────────────
    if any(kw in primary_method for kw in ["buffer", "ring", "缓冲"]):
        hints.append(ParameterSensitivityHint(
            parameter_name  = "buffer_radius_m",
            sensitivity     = "high",
            description     = "缓冲半径是缓冲区分析中最敏感的参数，直接决定哪些要素被纳入统计范围。不同半径（如300m vs 800m）可能导致结论截然不同。",
            suggested_range = "步行可达建议100-800m；驾车建议1000-5000m；具体参考研究区域尺度",
            method_id       = primary_method,
        ))

    # ── 核密度带宽 ─────────────────────────────────────────────────────────────
    if any(kw in primary_method for kw in ["kernel", "density", "kde", "核密度"]):
        hints.append(ParameterSensitivityHint(
            parameter_name  = "bandwidth_m",
            sensitivity     = "high",
            description     = "核函数带宽控制密度曲面的平滑程度。带宽过小导致过拟合，带宽过大丢失局部特征。",
            suggested_range = "通常取研究区最小可辨识特征尺度的1-3倍；Silverman's rule of thumb 可作参考",
            method_id       = primary_method,
        ))

    # ── 可达性半径 ─────────────────────────────────────────────────────────────
    if task == AnalysisIntent.ACCESSIBILITY or any(
            kw in primary_method for kw in ["service_area", "isochrone", "catchment", "2sfca"]):
        hints.append(ParameterSensitivityHint(
            parameter_name  = "catchment_radius_m",
            sensitivity     = "high",
            description     = "可达性分析的搜索半径/时间阈值决定服务覆盖范围的定义。不同阈值对应不同出行行为假设。",
            suggested_range = "步行15min ≈ 1200m；骑车15min ≈ 4000m；驾车15min ≈ 8000m（建议基于当地出行调查校准）",
            method_id       = primary_method,
        ))

    # ── 2SFCA 专项 ────────────────────────────────────────────────────────────
    if "2sfca" in primary_method or "fca" in primary_method:
        hints.append(ParameterSensitivityHint(
            parameter_name  = "decay_function",
            sensitivity     = "medium",
            description     = "2SFCA 衰减函数选择（Gaussian/Linear/Step）会影响近处需求点的权重分配方式，进而影响可达性指数排名。",
            suggested_range = "推荐 Gaussian 衰减（更符合实际出行行为）；Step 函数最简单但忽略连续性",
            method_id       = primary_method,
        ))

    # ── 加权叠加权重 ──────────────────────────────────────────────────────────
    if any(kw in primary_method for kw in ["weighted", "overlay", "weight", "加权"]):
        hints.append(ParameterSensitivityHint(
            parameter_name  = "criterion_weights",
            sensitivity     = "high",
            description     = "加权叠加中各因子权重主观性强，权重调整可能大幅改变选址结果。建议进行权重敏感性分析（如改变主要因子权重 ±0.1 观察结果变化）。",
            suggested_range = "主导因子权重建议不超过0.5；建议层次分析法（AHP）辅助确定权重",
            method_id       = primary_method,
        ))

    # ── 聚类参数 ──────────────────────────────────────────────────────────────
    if task == AnalysisIntent.CLUSTERING or any(
            kw in primary_method for kw in ["cluster", "dbscan", "kmeans"]):
        hints.append(ParameterSensitivityHint(
            parameter_name  = "cluster_parameters",
            sensitivity     = "high",
            description     = "聚类分析的关键参数（k值/eps/MinPts）对结果影响显著。建议通过轮廓系数/肘部法则选择最优参数，并报告参数敏感性。",
            suggested_range = "K-means 通常 k=3-8；DBSCAN 的 eps 建议基于 k-distance 图确定",
            method_id       = primary_method,
        ))

    # ── 变化检测阈值 ──────────────────────────────────────────────────────────
    if task == AnalysisIntent.CHANGE_DETECTION or any(
            kw in primary_method for kw in ["change", "diff", "threshold"]):
        hints.append(ParameterSensitivityHint(
            parameter_name  = "change_threshold",
            sensitivity     = "medium",
            description     = "变化检测阈值决定何种幅度的变化被认为是真实变化。阈值过低导致噪声被误判为变化；阈值过高遗漏小幅真实变化。",
            suggested_range = "建议基于背景噪声水平（如标准差的1-2倍）确定；影像变化检测通常 NDVI 差值 > 0.1",
            method_id       = primary_method,
        ))

    # ── 出行时间/速度 ─────────────────────────────────────────────────────────
    if any(kw in primary_method for kw in ["travel", "walk", "isochrone", "network"]):
        hints.append(ParameterSensitivityHint(
            parameter_name  = "travel_speed",
            sensitivity     = "medium",
            description     = "出行速度假设影响等时线范围。不同人群（老人/儿童/健康成人）步行速度差异显著（0.8-1.5 m/s）。",
            suggested_range = "步行均值 1.2 m/s（4.3 km/h）；老人/障碍人士建议 0.8 m/s",
            method_id       = primary_method,
        ))

    return hints


# ══════════════════════════════════════════════════════════════════════════════
#  4. MAUP 风险评估
# ══════════════════════════════════════════════════════════════════════════════

def _assess_maup_risk(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
) -> str:
    """
    评估可变面积单元问题（MAUP）风险等级。

    返回: "low" / "medium" / "high" / "not_applicable"
    """
    task = task_profile.task_type
    query_lower = (ctx.query or "").lower()

    # 不适用场景：轨迹/点级别分析、栅格分析
    entity_vals = [e.value if hasattr(e, "value") else str(e) for e in task_profile.entities]
    if GeoEntityType.TRAJECTORY.value in entity_vals:
        return "not_applicable"
    if all(ds.type == "raster" for ds in ctx.datasets) if ctx.datasets else False:
        return "not_applicable"

    # 高风险：行政区聚合 + 比较/汇总任务
    high_risk_keywords = [
        "行政区", "街道", "社区", "镇", "县", "省", "市辖区",
        "administrative", "district", "township", "county", "zone",
    ]
    if any(kw in query_lower for kw in high_risk_keywords):
        if task in [AnalysisIntent.COMPARISON, AnalysisIntent.SUMMARIZATION,
                    AnalysisIntent.CLUSTERING]:
            return "high"
        return "medium"

    # 中风险：多边形聚合
    poly_entities = [GeoEntityType.POLYGON.value, GeoEntityType.REGION.value]
    if any(e in entity_vals for e in poly_entities):
        if task in [AnalysisIntent.COMPARISON, AnalysisIntent.SUMMARIZATION]:
            return "medium"

    return "low"


# ══════════════════════════════════════════════════════════════════════════════
#  5. 尺度效应说明
# ══════════════════════════════════════════════════════════════════════════════

def _build_scale_effects_notes(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
) -> List[str]:
    """生成尺度效应相关注意事项列表"""
    notes: List[str] = []
    maup_risk = _assess_maup_risk(ctx, task_profile)

    # MAUP 说明
    if maup_risk == "high":
        notes.append(
            "⚠ MAUP（可变面积单元问题）高风险：本分析基于行政区等面状单元进行聚合，"
            "结果对分区方案的选择高度敏感。建议（1）检验不同分区粒度的结果稳定性；"
            "（2）在报告中明确说明聚合单元的选择依据。"
        )
    elif maup_risk == "medium":
        notes.append(
            "注意 MAUP（可变面积单元问题）：本分析涉及面状聚合，结果可能随区划方案不同而变化。"
            "建议在结论部分说明此局限性。"
        )

    # 尺度不匹配
    extents = [d.extent for d in ctx.datasets if d.extent and len(d.extent) == 4]
    if len(extents) >= 2:
        areas = [(e[2]-e[0])*(e[3]-e[1]) for e in extents]
        if max(areas) / max(min(areas), 1e-9) > 5:
            notes.append(
                "数据集空间范围差异较大，请确认各图层的研究区覆盖范围一致，"
                "避免边缘效应影响分析结果。"
            )

    # 分辨率说明（栅格）
    raster_ds = [d for d in ctx.datasets if d.type == "raster" and d.resolution]
    resolutions = [d.resolution for d in raster_ds]
    if len(set(resolutions)) > 1:
        notes.append(
            f"检测到多个分辨率不同的栅格数据集（{resolutions}）。"
            "叠加分析前需统一分辨率，并注意重采样方法对结果的影响。"
        )

    # 探索性分析提示
    analysis_mode = _classify_analysis_mode(ctx, task_profile, None)
    if analysis_mode == AnalysisMode.EXPLORATORY.value:
        notes.append(
            "本分析为探索性分析：结果用于发现空间规律和生成假设，"
            "不宜直接作为因果结论或政策依据。后续建议通过统计检验验证重要发现。"
        )
    elif analysis_mode == AnalysisMode.CAUSAL.value:
        notes.append(
            "⚠ 因果推断警告：GIS 空间分析本身无法直接建立因果关系。"
            "若研究目标是因果推断，需要控制空间自相关、混淆变量等问题，"
            "建议结合地理加权回归（GWR）或双重差分（DID）等因果识别方法。"
        )

    # 任务特定说明
    task = task_profile.task_type
    if task == AnalysisIntent.CHANGE_DETECTION:
        notes.append(
            "变化检测结论的可靠性取决于两期数据的可比性（传感器一致性、"
            "时相接近程度、辐射定标标准化）。建议在结论中注明数据来源和预处理方法。"
        )

    return notes
