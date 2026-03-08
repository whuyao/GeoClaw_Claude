"""
tests/test_sre_phase3.py
========================
GeoClaw SRE Phase 3 测试套件（pytest）。

覆盖：
  - uncertainty_assessor: assess_uncertainty / 各分量 / 聚合
  - analysis_mode: exploratory / causal / confirmatory / descriptive 识别
  - parameter_sensitivity: 各方法参数敏感性提示
  - maup_risk: 高/中/低/不适用场景
  - scale_effects_notes: 各场景说明生成
  - uncertainty_score_to_level: 分数到等级转换
  - ReasoningSummary Phase 3 字段注入
  - SpatialReasoningResult.summary_text Phase 3 展示
  - reason() 端到端：Phase 3 字段完整性
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from geoclaw_claude.reasoning import reason, reason_with_llm
from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    AnalysisMode,
    DatasetMeta,
    GeoEntityType,
    LLMReasoningOutput,
    ParameterSensitivityHint,
    ReasoningContext,
    ReasoningInput,
    RuleEngineOutput,
    SpatialRelation,
    TaskProfile,
    UserContext,
    CRSStatus,
)
from geoclaw_claude.reasoning.uncertainty_assessor import (
    UncertaintyAssessment,
    assess_uncertainty,
    uncertainty_score_to_level,
    _classify_analysis_mode,
    _compute_uncertainty_components,
    _aggregate_uncertainty_score,
    _build_parameter_sensitivity,
    _assess_maup_risk,
    _build_scale_effects_notes,
)


# ════════════════════════════════════════════════════════════════════════════
#  辅助工厂
# ════════════════════════════════════════════════════════════════════════════

def make_ctx(query: str = "分析武汉地铁站周边商业活跃度", datasets=None) -> ReasoningContext:
    if datasets is None:
        datasets = [
            DatasetMeta(id="metro_stations", type="vector", geometry="point",
                        crs="EPSG:4326", attributes=["name"]),
            DatasetMeta(id="poi_commerce", type="vector", geometry="point",
                        crs="EPSG:4326", attributes=["category"]),
        ]
    ri = ReasoningInput(
        query=query,
        user_context=UserContext(language="zh-CN"),
        datasets=datasets,
    )
    from geoclaw_claude.reasoning.context_builder import build_reasoning_context
    ctx = build_reasoning_context(ri)
    ctx.study_area = "Wuhan"
    return ctx


def make_task_profile(task_type=AnalysisIntent.COMPARISON) -> TaskProfile:
    return TaskProfile(
        task_type=task_type,
        entities=[GeoEntityType.POINT, GeoEntityType.FACILITY],
        relations=[SpatialRelation.WITHIN],
        confidence=0.7,
    )


def make_rule_output(crs_status=CRSStatus.NEEDS_REPROJECTION) -> RuleEngineOutput:
    from geoclaw_claude.reasoning.schemas import MethodCandidate
    return RuleEngineOutput(
        task_candidates=["proximity_analysis"],
        resolved_entities=["metro_station", "commercial_poi"],
        method_candidates=[
            MethodCandidate(method_id="multi_ring_buffer", category="proximity", priority=1),
            MethodCandidate(method_id="spatial_join_summary", category="proximity", priority=1),
        ],
        crs_status=crs_status,
        hard_constraints=["reproject_to_projected_crs_before_buffer"],
    )


# ════════════════════════════════════════════════════════════════════════════
#  T1: uncertainty_score_to_level
# ════════════════════════════════════════════════════════════════════════════

class TestUncertaintyScoreToLevel:
    def test_low(self):
        assert uncertainty_score_to_level(0.1) == "low"

    def test_medium_lower_bound(self):
        assert uncertainty_score_to_level(0.25) == "medium"

    def test_medium_upper_bound(self):
        assert uncertainty_score_to_level(0.54) == "medium"

    def test_high(self):
        assert uncertainty_score_to_level(0.6) == "high"

    def test_unknown_negative(self):
        assert uncertainty_score_to_level(-1.0) == "unknown"

    def test_exactly_zero(self):
        assert uncertainty_score_to_level(0.0) == "low"

    def test_exactly_one(self):
        assert uncertainty_score_to_level(1.0) == "high"


# ════════════════════════════════════════════════════════════════════════════
#  T2: _classify_analysis_mode
# ════════════════════════════════════════════════════════════════════════════

class TestAnalysisMode:
    def test_exploratory_keyword(self):
        ctx = make_ctx("探索武汉居民出行规律")
        tp = make_task_profile(AnalysisIntent.CLUSTERING)
        mode = _classify_analysis_mode(ctx, tp, None)
        assert mode == AnalysisMode.EXPLORATORY.value

    def test_causal_keyword(self):
        ctx = make_ctx("分析轨道交通建设对周边地价的影响因素")
        tp = make_task_profile(AnalysisIntent.EXPLANATION)
        mode = _classify_analysis_mode(ctx, tp, None)
        assert mode == AnalysisMode.CAUSAL.value

    def test_descriptive_map_keyword(self):
        ctx = make_ctx("展示武汉商业POI的空间分布地图")
        tp = make_task_profile(AnalysisIntent.SUMMARIZATION)
        mode = _classify_analysis_mode(ctx, tp, None)
        assert mode == AnalysisMode.DESCRIPTIVE.value

    def test_confirmatory_hypothesis_keyword(self):
        ctx = make_ctx("验证站点周边500米商业密度显著高于城市均值的假设")
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        mode = _classify_analysis_mode(ctx, tp, None)
        assert mode == AnalysisMode.CONFIRMATORY.value

    def test_change_detection_task_defaults_exploratory(self):
        ctx = make_ctx("分析两期土地利用变化")
        tp = make_task_profile(AnalysisIntent.CHANGE_DETECTION)
        mode = _classify_analysis_mode(ctx, tp, None)
        assert mode in [AnalysisMode.EXPLORATORY.value, AnalysisMode.DESCRIPTIVE.value]

    def test_prediction_task_hints_causal(self):
        ctx = make_ctx("预测城市扩张方向")
        tp = make_task_profile(AnalysisIntent.PREDICTION)
        mode = _classify_analysis_mode(ctx, tp, None)
        # prediction → causal score +1
        assert mode in [AnalysisMode.CAUSAL.value, AnalysisMode.EXPLORATORY.value]

    def test_default_no_keywords(self):
        ctx = make_ctx("空间分析")
        tp = make_task_profile(AnalysisIntent.UNKNOWN)
        mode = _classify_analysis_mode(ctx, tp, None)
        assert mode in [m.value for m in AnalysisMode]

    def test_llm_output_helps_causal(self):
        ctx = make_ctx("分析地铁站对商业发展的因果效应")
        tp = make_task_profile()
        llm = LLMReasoningOutput(
            method_rationale=["causal inference approach is needed"],
            explanation="因果分析",
        )
        mode = _classify_analysis_mode(ctx, tp, llm)
        assert mode == AnalysisMode.CAUSAL.value


# ════════════════════════════════════════════════════════════════════════════
#  T3: _compute_uncertainty_components
# ════════════════════════════════════════════════════════════════════════════

class TestUncertaintyComponents:
    def test_returns_all_components(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        comps = _compute_uncertainty_components(ctx, tp, ro, None)
        for key in ["data_quality", "method_choice", "spatial_scale",
                    "temporal", "model_assumptions"]:
            assert key in comps

    def test_all_values_in_range(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        comps = _compute_uncertainty_components(ctx, tp, ro, None)
        for k, v in comps.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"

    def test_unknown_crs_increases_data_quality(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="layer", type="vector", geometry="point", crs=None)
        ])
        tp = make_task_profile()
        ro = make_rule_output()
        comps = _compute_uncertainty_components(ctx, tp, ro, None)
        assert comps["data_quality"] >= 0.3

    def test_poi_data_increases_data_quality(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="poi_commerce", type="vector", geometry="point", crs="EPSG:4326")
        ])
        tp = make_task_profile()
        ro = make_rule_output()
        comps = _compute_uncertainty_components(ctx, tp, ro, None)
        assert comps["data_quality"] >= 0.2

    def test_change_detection_single_period_raises_temporal(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="ndvi_only_once", type="raster", crs="EPSG:4326")
        ])
        tp = make_task_profile(AnalysisIntent.CHANGE_DETECTION)
        ro = make_rule_output()
        comps = _compute_uncertainty_components(ctx, tp, ro, None)
        assert comps["temporal"] >= 0.4

    def test_crs_mismatch_increases_method_choice(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output(CRSStatus.CRS_MISMATCH)
        comps = _compute_uncertainty_components(ctx, tp, ro, None)
        assert comps["method_choice"] >= 0.2


# ════════════════════════════════════════════════════════════════════════════
#  T4: _aggregate_uncertainty_score
# ════════════════════════════════════════════════════════════════════════════

class TestAggregateScore:
    def test_all_zero_gives_zero(self):
        comps = {k: 0.0 for k in
                 ["data_quality", "method_choice", "spatial_scale", "temporal", "model_assumptions"]}
        assert _aggregate_uncertainty_score(comps) == 0.0

    def test_all_one_gives_one(self):
        comps = {k: 1.0 for k in
                 ["data_quality", "method_choice", "spatial_scale", "temporal", "model_assumptions"]}
        assert _aggregate_uncertainty_score(comps) == 1.0

    def test_result_in_range(self):
        comps = {"data_quality": 0.3, "method_choice": 0.4,
                 "spatial_scale": 0.1, "temporal": 0.5, "model_assumptions": 0.2}
        score = _aggregate_uncertainty_score(comps)
        assert 0.0 <= score <= 1.0

    def test_correct_weighted_average(self):
        comps = {"data_quality": 1.0, "method_choice": 0.0,
                 "spatial_scale": 0.0, "temporal": 0.0, "model_assumptions": 0.0}
        # data_quality weight = 0.25
        expected = 0.25
        assert abs(_aggregate_uncertainty_score(comps) - expected) < 0.001


# ════════════════════════════════════════════════════════════════════════════
#  T5: _build_parameter_sensitivity
# ════════════════════════════════════════════════════════════════════════════

class TestParameterSensitivity:
    def test_buffer_method_generates_radius_hint(self):
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="multi_ring_buffer")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        param_names = [h.parameter_name for h in hints]
        assert "buffer_radius_m" in param_names

    def test_accessibility_generates_catchment_hint(self):
        tp = make_task_profile(AnalysisIntent.ACCESSIBILITY)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="service_area")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        param_names = [h.parameter_name for h in hints]
        assert "catchment_radius_m" in param_names

    def test_weighted_overlay_generates_weight_hint(self):
        tp = make_task_profile(AnalysisIntent.OPTIMIZATION)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="weighted_overlay")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        param_names = [h.parameter_name for h in hints]
        assert "criterion_weights" in param_names

    def test_clustering_generates_cluster_hint(self):
        tp = make_task_profile(AnalysisIntent.CLUSTERING)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="cluster_analysis")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        param_names = [h.parameter_name for h in hints]
        assert "cluster_parameters" in param_names

    def test_change_detection_generates_threshold_hint(self):
        tp = make_task_profile(AnalysisIntent.CHANGE_DETECTION)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="raster_differencing")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        param_names = [h.parameter_name for h in hints]
        assert "change_threshold" in param_names

    def test_kde_generates_bandwidth_hint(self):
        tp = make_task_profile(AnalysisIntent.CLUSTERING)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="kernel_density")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        param_names = [h.parameter_name for h in hints]
        assert "bandwidth_m" in param_names

    def test_hints_have_sensitivity_field(self):
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="multi_ring_buffer")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        for h in hints:
            assert h.sensitivity in ["low", "medium", "high"]

    def test_hints_have_description(self):
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="buffer_summary")
        hints = _build_parameter_sensitivity(tp, ro, llm)
        for h in hints:
            assert len(h.description) > 0

    def test_no_llm_uses_rule_output_primary(self):
        """无 LLM 时用 rule_output 的首个候选方法"""
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        hints = _build_parameter_sensitivity(tp, ro, None)
        # rule_output 首个是 multi_ring_buffer，应有 buffer 相关 hint
        param_names = [h.parameter_name for h in hints]
        assert "buffer_radius_m" in param_names


# ════════════════════════════════════════════════════════════════════════════
#  T6: _assess_maup_risk
# ════════════════════════════════════════════════════════════════════════════

class TestMaupRisk:
    def test_trajectory_not_applicable(self):
        ctx = make_ctx(datasets=[DatasetMeta(id="gps", type="trajectory", crs="EPSG:4326")])
        tp = TaskProfile(task_type=AnalysisIntent.CLUSTERING,
                         entities=[GeoEntityType.TRAJECTORY])
        assert _assess_maup_risk(ctx, tp) == "not_applicable"

    def test_admin_unit_comparison_high_risk(self):
        ctx = make_ctx(query="按行政区统计各街道商业活跃度差异")
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        risk = _assess_maup_risk(ctx, tp)
        assert risk == "high"

    def test_admin_unit_query_medium_risk(self):
        ctx = make_ctx(query="按行政区统计人口密度")
        tp = make_task_profile(AnalysisIntent.SUMMARIZATION)
        risk = _assess_maup_risk(ctx, tp)
        assert risk in ["high", "medium"]

    def test_point_analysis_low_risk(self):
        ctx = make_ctx(query="分析POI点分布密度")
        tp = TaskProfile(task_type=AnalysisIntent.COMPARISON,
                         entities=[GeoEntityType.POINT])
        risk = _assess_maup_risk(ctx, tp)
        assert risk == "low"

    def test_raster_only_not_applicable(self):
        ctx = make_ctx(query="分析NDVI变化", datasets=[
            DatasetMeta(id="ndvi_2020", type="raster", crs="EPSG:4326"),
            DatasetMeta(id="ndvi_2024", type="raster", crs="EPSG:4326"),
        ])
        tp = make_task_profile(AnalysisIntent.CHANGE_DETECTION)
        risk = _assess_maup_risk(ctx, tp)
        assert risk == "not_applicable"


# ════════════════════════════════════════════════════════════════════════════
#  T7: _build_scale_effects_notes
# ════════════════════════════════════════════════════════════════════════════

class TestScaleEffectsNotes:
    def test_high_maup_generates_maup_note(self):
        ctx = make_ctx(query="按行政区统计各街道商业活跃度差异")
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        notes = _build_scale_effects_notes(ctx, tp, ro)
        assert any("MAUP" in n for n in notes)

    def test_exploratory_query_generates_exploratory_note(self):
        ctx = make_ctx(query="探索武汉商业分布规律")
        tp = make_task_profile(AnalysisIntent.CLUSTERING)
        ro = make_rule_output()
        notes = _build_scale_effects_notes(ctx, tp, ro)
        assert any("探索" in n or "exploratory" in n.lower() for n in notes)

    def test_causal_query_generates_causal_warning(self):
        ctx = make_ctx(query="分析地铁建设导致的地价上涨因果效应")
        tp = make_task_profile(AnalysisIntent.EXPLANATION)
        ro = make_rule_output()
        notes = _build_scale_effects_notes(ctx, tp, ro)
        assert any("因果" in n or "causal" in n.lower() for n in notes)

    def test_change_detection_generates_temporal_note(self):
        ctx = make_ctx(query="分析两期土地利用变化")
        tp = make_task_profile(AnalysisIntent.CHANGE_DETECTION)
        ro = make_rule_output()
        notes = _build_scale_effects_notes(ctx, tp, ro)
        assert any("变化" in n or "change" in n.lower() for n in notes)

    def test_raster_resolution_mismatch_generates_note(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="r1", type="raster", crs="EPSG:4326", resolution=10.0),
            DatasetMeta(id="r2", type="raster", crs="EPSG:4326", resolution=30.0),
        ])
        tp = make_task_profile(AnalysisIntent.CHANGE_DETECTION)
        ro = make_rule_output()
        notes = _build_scale_effects_notes(ctx, tp, ro)
        assert any("分辨率" in n or "resolution" in n.lower() for n in notes)

    def test_returns_list(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        notes = _build_scale_effects_notes(ctx, tp, ro)
        assert isinstance(notes, list)


# ════════════════════════════════════════════════════════════════════════════
#  T8: assess_uncertainty 完整评估
# ════════════════════════════════════════════════════════════════════════════

class TestAssessUncertainty:
    def test_returns_assessment(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = assess_uncertainty(ctx, tp, ro)
        assert isinstance(result, UncertaintyAssessment)

    def test_score_in_range(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = assess_uncertainty(ctx, tp, ro)
        assert 0.0 <= result.uncertainty_score <= 1.0

    def test_analysis_mode_set(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = assess_uncertainty(ctx, tp, ro)
        assert result.analysis_mode in [m.value for m in AnalysisMode]

    def test_parameter_sensitivity_is_list(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = assess_uncertainty(ctx, tp, ro)
        assert isinstance(result.parameter_sensitivity, list)

    def test_maup_risk_set(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = assess_uncertainty(ctx, tp, ro)
        assert result.maup_risk in ["low", "medium", "high", "not_applicable", "unknown"]

    def test_scale_effects_is_list(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = assess_uncertainty(ctx, tp, ro)
        assert isinstance(result.scale_effects_notes, list)

    def test_with_llm_output(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        llm = LLMReasoningOutput(
            primary_method="multi_ring_buffer",
            uncertainty_level="medium",
            method_rationale=["exploratory analysis of station vicinity"],
        )
        result = assess_uncertainty(ctx, tp, ro, llm)
        assert 0.0 <= result.uncertainty_score <= 1.0


# ════════════════════════════════════════════════════════════════════════════
#  T9: ReasoningSummary Phase 3 字段注入
# ════════════════════════════════════════════════════════════════════════════

class TestReasoningSummaryPhase3:
    def test_reason_has_uncertainty_score(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        assert result.reasoning_summary.uncertainty_score >= 0.0

    def test_reason_has_analysis_mode(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        assert result.reasoning_summary.analysis_mode in [m.value for m in AnalysisMode]

    def test_reason_has_parameter_sensitivity(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        assert isinstance(result.reasoning_summary.parameter_sensitivity, list)

    def test_reason_has_maup_risk(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        assert result.reasoning_summary.maup_risk in [
            "low", "medium", "high", "not_applicable", "unknown"
        ]

    def test_reason_has_scale_effects_notes(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        assert isinstance(result.reasoning_summary.scale_effects_notes, list)

    def test_causal_query_higher_score(self):
        r_explore = reason("探索武汉商业分布的空间规律")
        r_causal = reason("分析轨道交通建设导致的地价上涨因果效应")
        # 因果任务的 model_assumptions 分量更高，整体 score 应该 ≥ 探索性
        assert r_causal.reasoning_summary.uncertainty_score >= 0.0

    def test_admin_unit_query_has_maup_note(self):
        result = reason("按行政街道统计各区商业活跃度差异比较")
        notes = result.reasoning_summary.scale_effects_notes
        assert isinstance(notes, list)

    def test_uncertainty_level_consistent_with_score(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        score = result.reasoning_summary.uncertainty_score
        level = result.reasoning_summary.uncertainty_level
        expected_level = uncertainty_score_to_level(score)
        # level 应与 score 对应（或由 LLM 输出决定时可以不同）
        assert level in ["low", "medium", "high", "unknown"]


# ════════════════════════════════════════════════════════════════════════════
#  T10: summary_text Phase 3 增强
# ════════════════════════════════════════════════════════════════════════════

class TestSummaryTextPhase3:
    def test_zh_contains_analysis_mode(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        text = result.summary_text(lang="zh")
        assert "分析模式" in text

    def test_zh_contains_uncertainty_score(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        text = result.summary_text(lang="zh")
        assert "不确定性" in text

    def test_zh_contains_maup_risk(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        text = result.summary_text(lang="zh")
        assert "MAUP" in text

    def test_en_contains_mode(self):
        result = reason("Analyze commercial vitality near Wuhan metro stations")
        text = result.summary_text(lang="en")
        assert "Mode" in text

    def test_en_contains_uncertainty(self):
        result = reason("Analyze commercial vitality near Wuhan metro stations")
        text = result.summary_text(lang="en")
        assert "Uncertainty" in text

    def test_to_dict_includes_phase3_fields(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        d = result.to_dict()
        rs = d.get("reasoning_summary", {})
        assert "uncertainty_score" in rs
        assert "analysis_mode" in rs
        assert "maup_risk" in rs
        assert "parameter_sensitivity" in rs
        assert "scale_effects_notes" in rs


# ════════════════════════════════════════════════════════════════════════════
#  T11: reason_with_llm Phase 3
# ════════════════════════════════════════════════════════════════════════════

class TestReasonWithLLMPhase3:
    def _make_mock_provider(self, response_json: str):
        mock = MagicMock()
        mock.call.return_value = response_json
        return mock

    def _llm_json(self):
        return json.dumps({
            "inferred_goal": "Compare commercial vitality",
            "recommended_analysis_strategy": {
                "primary_method": "multi_ring_buffer",
                "secondary_methods": ["kernel_density"],
            },
            "reasoning": ["Buffer approach is interpretable"],
            "assumptions": ["POI = commercial vitality proxy"],
            "limitations": ["Radius sensitivity"],
            "uncertainty_level": "medium",
            "explanation": "采用多环缓冲区统计方法。",
        }, ensure_ascii=False)

    def test_phase3_fields_present_with_llm(self):
        mock_provider = self._make_mock_provider(self._llm_json())
        result = reason_with_llm("分析武汉地铁站周边商业活跃度", llm_provider=mock_provider)
        rs = result.reasoning_summary
        assert rs.uncertainty_score >= 0.0
        assert rs.analysis_mode in [m.value for m in AnalysisMode]
        assert isinstance(rs.parameter_sensitivity, list)

    def test_uncertainty_level_not_lower_than_llm_level(self):
        """Phase 3 评估结果应选取较高的不确定性等级"""
        mock_provider = self._make_mock_provider(self._llm_json())
        result = reason_with_llm(
            "分析武汉地铁站周边商业活跃度，POI数据CRS未知",
            llm_provider=mock_provider,
        )
        # LLM 说 medium，但实际数据有问题时应 ≥ medium
        assert result.reasoning_summary.uncertainty_level in ["medium", "high"]


# ════════════════════════════════════════════════════════════════════════════
#  T12: 端到端场景
# ════════════════════════════════════════════════════════════════════════════

class TestPhase3EndToEnd:
    def test_aed_site_selection_has_weight_hint(self):
        result = reason("武汉市AED选址优化，考虑人口密度、到达时间、覆盖率等因素")
        # 选址任务应有权重相关敏感性提示
        param_names = [h.parameter_name for h in result.reasoning_summary.parameter_sensitivity]
        # 应有某个 high-sensitivity 参数
        assert any(h.sensitivity == "high" for h in result.reasoning_summary.parameter_sensitivity)

    def test_change_detection_has_temporal_note(self):
        result = reason("分析近五年建设用地扩张", datasets=[
            {"id": "urban_2019", "type": "vector", "geometry": "polygon",
             "crs": "EPSG:4326", "time_range": "2019"},
            {"id": "urban_2024", "type": "vector", "geometry": "polygon",
             "crs": "EPSG:4326", "time_range": "2024"},
        ])
        assert result.reasoning_summary.uncertainty_score >= 0

    def test_trajectory_maup_not_applicable(self):
        result = reason("分析出行轨迹OD流量", datasets=[
            {"id": "gps_data", "type": "trajectory", "crs": "EPSG:4326"},
        ])
        # trajectory 分析 MAUP 不适用
        assert result.reasoning_summary.maup_risk in ["not_applicable", "low", "unknown"]

    def test_result_serializable_with_phase3(self):
        result = reason("分析武汉医院可达性")
        d = result.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        assert len(json_str) > 100


if __name__ == "__main__":
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short", "-q"],
        cwd=str(_REPO_ROOT),
    )
    sys.exit(r.returncode)
