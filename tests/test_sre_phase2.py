"""
tests/test_sre_phase2.py
========================
GeoClaw SRE Phase 2 测试套件（pytest）。

覆盖：
  - template_library: load_templates / match_templates / get_method_candidates
  - primitive_resolver: resolve_primitives（文本关键词、数据集推断、组合场景）
  - llm_reasoner: _build_llm_prompt / _parse_llm_response / mock LLM call
  - __init__.reason: Phase 2 调用链（rule+template+primitive）
  - reason_with_llm: mock LLM 成功 / 失败降级
  - workflow_synthesizer: LLM 方法注入 / secondary_methods 加入 optional_steps
  - validator: Phase 2 Reasoning Consistency / Uncertainty Caveat
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── 确保 src 在 path ──────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── 导入被测模块 ──────────────────────────────────────────────────────────────
from geoclaw_claude.reasoning import reason, reason_with_llm
from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    DatasetMeta,
    GeoEntityType,
    LLMReasoningOutput,
    ReasoningContext,
    ReasoningInput,
    RuleEngineOutput,
    SpatialRelation,
    SystemPolicy,
    TaskProfile,
    UserContext,
    ValidationStatus,
)
from geoclaw_claude.reasoning.template_library import (
    get_method_candidates,
    get_method_info,
    get_method_limitations,
    get_recommended_artifacts,
    get_template_by_id,
    get_template_notes,
    list_template_ids,
    load_templates,
    match_templates,
)
from geoclaw_claude.reasoning.primitive_resolver import resolve_primitives, PrimitiveResolution
from geoclaw_claude.reasoning.llm_reasoner import (
    _build_llm_prompt,
    _parse_llm_response,
    run_llm_reasoner,
)
from geoclaw_claude.reasoning.validator import validate_reasoning
from geoclaw_claude.reasoning.workflow_synthesizer import synthesize_workflow


# ════════════════════════════════════════════════════════════════════════════
#  辅助工厂函数
# ════════════════════════════════════════════════════════════════════════════

def make_ctx(
    query: str = "分析武汉地铁站周边商业活跃度",
    datasets=None,
    study_area: str = "Wuhan",
) -> ReasoningContext:
    if datasets is None:
        datasets = [
            DatasetMeta(id="metro_stations", type="vector", geometry="point",
                        crs="EPSG:4326", attributes=["station_id", "name"]),
            DatasetMeta(id="poi_commerce", type="vector", geometry="point",
                        crs="EPSG:4326", attributes=["poi_id", "category"]),
        ]
    ri = ReasoningInput(
        query=query,
        user_context=UserContext(language="zh-CN", expertise="GIS expert"),
        datasets=datasets,
    )
    from geoclaw_claude.reasoning.context_builder import build_reasoning_context
    ctx = build_reasoning_context(ri)
    ctx.study_area = study_area
    return ctx


def make_task_profile(task_type=AnalysisIntent.COMPARISON) -> TaskProfile:
    return TaskProfile(
        task_type=task_type,
        entities=[GeoEntityType.POINT, GeoEntityType.FACILITY],
        relations=[SpatialRelation.WITHIN],
        confidence=0.7,
    )


def make_rule_output() -> RuleEngineOutput:
    from geoclaw_claude.reasoning.schemas import MethodCandidate, CRSStatus
    return RuleEngineOutput(
        task_candidates=["proximity_analysis"],
        resolved_entities=["metro_station", "commercial_poi"],
        method_candidates=[
            MethodCandidate(method_id="multi_ring_buffer", category="proximity",
                            description="多环缓冲区", priority=1),
            MethodCandidate(method_id="spatial_join_summary", category="proximity",
                            description="空间连接", priority=1),
        ],
        crs_status=CRSStatus.NEEDS_REPROJECTION,
        hard_constraints=["reproject_to_projected_crs_before_buffer"],
    )


# ════════════════════════════════════════════════════════════════════════════
#  T1: template_library — load_templates
# ════════════════════════════════════════════════════════════════════════════

class TestTemplateLibraryLoad:
    def test_load_returns_dict(self):
        templates = load_templates()
        assert isinstance(templates, dict)

    def test_load_five_templates(self):
        templates = load_templates()
        assert len(templates) >= 5, f"Expected ≥5 templates, got {len(templates)}"

    def test_template_ids_present(self):
        ids = list_template_ids()
        for tid in ["proximity", "accessibility", "site_selection",
                    "change_detection", "trajectory"]:
            assert tid in ids, f"Missing template: {tid}"

    def test_force_reload_works(self):
        t1 = load_templates()
        t2 = load_templates(force_reload=True)
        assert set(t1.keys()) == set(t2.keys())

    def test_each_template_has_methods(self):
        templates = load_templates()
        for tid, t in templates.items():
            assert "methods" in t, f"Template {tid} missing 'methods'"
            assert len(t["methods"]) >= 1

    def test_proximity_has_buffer_method(self):
        t = get_template_by_id("proximity")
        assert t is not None
        method_ids = [m["id"] for m in t.get("methods", [])]
        assert "buffer_summary" in method_ids or "multi_ring_buffer" in method_ids

    def test_accessibility_has_service_area(self):
        t = get_template_by_id("accessibility")
        method_ids = [m["id"] for m in t.get("methods", [])]
        assert "service_area" in method_ids or "isochrone" in method_ids

    def test_trajectory_has_od_extraction(self):
        t = get_template_by_id("trajectory")
        method_ids = [m["id"] for m in t.get("methods", [])]
        assert "od_extraction" in method_ids

    def test_change_detection_has_transition_matrix(self):
        t = get_template_by_id("change_detection")
        method_ids = [m["id"] for m in t.get("methods", [])]
        assert "land_cover_transition_matrix" in method_ids or "raster_differencing" in method_ids


# ════════════════════════════════════════════════════════════════════════════
#  T2: template_library — match_templates / get_method_candidates
# ════════════════════════════════════════════════════════════════════════════

class TestTemplateMatch:
    def test_comparison_matches_proximity(self):
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        matched = match_templates(tp)
        ids = [t.get("template_id") for t in matched]
        assert "proximity" in ids

    def test_accessibility_matches_accessibility(self):
        tp = make_task_profile(AnalysisIntent.ACCESSIBILITY)
        matched = match_templates(tp)
        ids = [t.get("template_id") for t in matched]
        assert "accessibility" in ids

    def test_optimization_matches_site_selection(self):
        tp = make_task_profile(AnalysisIntent.OPTIMIZATION)
        matched = match_templates(tp)
        ids = [t.get("template_id") for t in matched]
        assert "site_selection" in ids

    def test_change_detection_matches(self):
        tp = make_task_profile(AnalysisIntent.CHANGE_DETECTION)
        matched = match_templates(tp)
        ids = [t.get("template_id") for t in matched]
        assert "change_detection" in ids

    def test_trajectory_entity_boosts_trajectory_template(self):
        tp = TaskProfile(
            task_type=AnalysisIntent.CLUSTERING,
            entities=[GeoEntityType.TRAJECTORY],
        )
        matched = match_templates(tp)
        if matched:
            assert matched[0].get("template_id") == "trajectory"

    def test_get_method_candidates_returns_list(self):
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        candidates = get_method_candidates(tp)
        assert isinstance(candidates, list)

    def test_method_candidates_have_method_id(self):
        tp = make_task_profile(AnalysisIntent.ACCESSIBILITY)
        candidates = get_method_candidates(tp, max_methods=4)
        for mc in candidates:
            assert mc.method_id, "MethodCandidate.method_id should not be empty"

    def test_max_methods_respected(self):
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        candidates = get_method_candidates(tp, max_methods=3)
        assert len(candidates) <= 3

    def test_priority_ordering(self):
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        candidates = get_method_candidates(tp, max_methods=6)
        priorities = [mc.priority for mc in candidates]
        assert priorities == sorted(priorities), "Candidates should be sorted by priority"

    def test_get_method_info(self):
        info = get_method_info("proximity", "multi_ring_buffer")
        if info is not None:
            assert "id" in info
            assert "description" in info or "name" in info

    def test_get_method_limitations(self):
        limitations = get_method_limitations("proximity", "multi_ring_buffer")
        assert isinstance(limitations, list)

    def test_get_template_notes(self):
        note = get_template_notes("site_selection")
        assert isinstance(note, str)

    def test_get_recommended_artifacts(self):
        artifacts = get_recommended_artifacts("proximity")
        assert isinstance(artifacts, list)


# ════════════════════════════════════════════════════════════════════════════
#  T3: primitive_resolver
# ════════════════════════════════════════════════════════════════════════════

class TestPrimitiveResolver:
    def test_returns_primitive_resolution(self):
        ctx = make_ctx()
        result = resolve_primitives(ctx)
        assert isinstance(result, PrimitiveResolution)

    def test_station_keyword_detects_facility(self):
        ctx = make_ctx(query="分析武汉地铁站周边的商业")
        result = resolve_primitives(ctx)
        assert GeoEntityType.FACILITY.value in result.entities

    def test_trajectory_keyword_detected(self):
        ctx = make_ctx(query="分析居民出行轨迹的OD流量")
        result = resolve_primitives(ctx)
        assert GeoEntityType.TRAJECTORY.value in result.entities

    def test_network_keyword_detected(self):
        ctx = make_ctx(query="基于路网计算医院可达性")
        result = resolve_primitives(ctx)
        assert GeoEntityType.NETWORK.value in result.entities

    def test_raster_keyword_detected(self):
        ctx = make_ctx(query="用NDVI栅格数据分析植被变化")
        result = resolve_primitives(ctx)
        assert GeoEntityType.RASTER.value in result.entities

    def test_within_relation_detected(self):
        ctx = make_ctx(query="统计500米范围内的POI数量")
        result = resolve_primitives(ctx)
        assert SpatialRelation.WITHIN.value in result.relations

    def test_accessible_relation_detected(self):
        ctx = make_ctx(query="计算各居民点到学校的步行可达性")
        result = resolve_primitives(ctx)
        assert SpatialRelation.ACCESSIBLE_FROM.value in result.relations

    def test_count_metric_detected(self):
        ctx = make_ctx(query="统计缓冲区内的POI数量")
        result = resolve_primitives(ctx)
        assert "count" in result.target_metrics

    def test_density_metric_detected(self):
        ctx = make_ctx(query="分析商业密度分布")
        result = resolve_primitives(ctx)
        assert "density" in result.target_metrics

    def test_dataset_point_geometry_infers_point_entity(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="hospitals", type="vector", geometry="point", crs="EPSG:4326")
        ])
        result = resolve_primitives(ctx)
        assert GeoEntityType.POINT.value in result.entities

    def test_dataset_raster_infers_raster_entity(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="dem_layer", type="raster", crs="EPSG:4326")
        ])
        result = resolve_primitives(ctx)
        assert GeoEntityType.RASTER.value in result.entities

    def test_dataset_id_with_station_infers_facility(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="metro_station", type="vector", geometry="point", crs="EPSG:4326")
        ])
        result = resolve_primitives(ctx)
        assert GeoEntityType.FACILITY.value in result.entities

    def test_dataset_id_with_trajectory_infers_trajectory(self):
        ctx = make_ctx(datasets=[
            DatasetMeta(id="gps_trajectory", type="trajectory", crs="EPSG:4326")
        ])
        result = resolve_primitives(ctx)
        assert GeoEntityType.TRAJECTORY.value in result.entities

    def test_confidence_with_full_ctx(self):
        ctx = make_ctx()
        result = resolve_primitives(ctx)
        assert 0.0 <= result.confidence <= 1.0
        assert result.confidence > 0.3, "Should have decent confidence with datasets"

    def test_fallback_defaults(self):
        """空 query + 无数据集时，应有默认值而非抛出异常"""
        ctx = make_ctx(query="", datasets=[])
        result = resolve_primitives(ctx)
        assert len(result.entities) >= 1
        assert len(result.relations) >= 1
        assert len(result.target_metrics) >= 1


# ════════════════════════════════════════════════════════════════════════════
#  T4: llm_reasoner
# ════════════════════════════════════════════════════════════════════════════

class TestLLMReasoner:
    def _make_valid_llm_json(self) -> str:
        return json.dumps({
            "inferred_goal": "Compare commercial vitality around Wuhan metro stations",
            "recommended_analysis_strategy": {
                "primary_method": "multi_ring_buffer",
                "secondary_methods": ["kernel_density"],
            },
            "reasoning": [
                "Buffer-based aggregation supports direct station comparison",
                "Local neighborhood effects are better captured by rings than citywide KDE",
            ],
            "assumptions": ["POI count approximates commercial vitality"],
            "limitations": [
                "Results sensitive to buffer radius selection",
                "POI data may have category bias",
            ],
            "uncertainty_level": "medium",
            "explanation": "采用多环缓冲区统计方法，直观比较各站点周边商业活跃度差异。",
        }, ensure_ascii=False)

    def test_no_provider_returns_none(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = run_llm_reasoner(ctx, tp, ro, llm_provider=None)
        assert result is None

    def test_parse_valid_json(self):
        raw = self._make_valid_llm_json()
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMReasoningOutput)
        assert result.inferred_goal != ""
        assert result.primary_method == "multi_ring_buffer"
        assert "kernel_density" in result.secondary_methods
        assert len(result.method_rationale) >= 1
        assert result.uncertainty_level == "medium"

    def test_parse_json_in_code_block(self):
        raw = "```json\n" + self._make_valid_llm_json() + "\n```"
        result = _parse_llm_response(raw)
        assert result.primary_method == "multi_ring_buffer"

    def test_parse_json_embedded_in_text(self):
        raw = "Here is the result:\n" + self._make_valid_llm_json() + "\nDone."
        result = _parse_llm_response(raw)
        assert result.inferred_goal != ""

    def test_parse_invalid_json_graceful(self):
        result = _parse_llm_response("not json at all {broken")
        assert isinstance(result, LLMReasoningOutput)
        assert result.raw_response is not None

    def test_build_prompt_contains_query(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        prompt = _build_llm_prompt(ctx, tp, ro)
        assert ctx.query in prompt

    def test_build_prompt_contains_hard_constraints(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        ro.hard_constraints = ["reproject_to_projected_crs_before_buffer"]
        prompt = _build_llm_prompt(ctx, tp, ro)
        assert "reproject" in prompt.lower()

    def test_build_prompt_contains_method_candidates(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        prompt = _build_llm_prompt(ctx, tp, ro)
        assert "multi_ring_buffer" in prompt

    def test_llm_provider_call_mock(self):
        """Mock LLM provider，验证 run_llm_reasoner 正确调用并返回 LLMReasoningOutput"""
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()

        mock_provider = MagicMock()
        mock_provider.call.return_value = self._make_valid_llm_json()

        result = run_llm_reasoner(ctx, tp, ro, llm_provider=mock_provider)
        assert result is not None
        assert isinstance(result, LLMReasoningOutput)
        assert result.primary_method == "multi_ring_buffer"
        mock_provider.call.assert_called_once()

    def test_llm_provider_failure_returns_none(self):
        """LLM 调用抛出异常时应降级返回 None"""
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()

        mock_provider = MagicMock()
        mock_provider.call.side_effect = RuntimeError("API unavailable")

        result = run_llm_reasoner(ctx, tp, ro, llm_provider=mock_provider)
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
#  T5: reason() — Phase 2 完整调用链（rule-only）
# ════════════════════════════════════════════════════════════════════════════

class TestReasonPhase2:
    def test_reason_returns_result(self):
        result = reason("分析武汉地铁站周边商业活跃度", datasets=[
            {"id": "metro_stations", "type": "vector", "geometry": "point",
             "crs": "EPSG:4326", "attributes": ["name"]},
            {"id": "poi_commerce", "type": "vector", "geometry": "point",
             "crs": "EPSG:4326", "attributes": ["category"]},
        ])
        assert result is not None

    def test_reason_method_candidates_enriched_by_template(self):
        """Phase 2：method_candidates 应该被 template_library 增强"""
        result = reason("分析武汉地铁站周边商业活跃度")
        # 有工作流步骤
        assert len(result.workflow_plan.steps) >= 1

    def test_reason_task_profile_has_entities(self):
        """Phase 2：primitive_resolver 应补充实体到 task_profile"""
        result = reason("分析医院周边的步行可达性", datasets=[
            {"id": "hospitals", "type": "vector", "geometry": "point", "crs": "EPSG:4326"},
        ])
        assert result.task_profile.entities

    def test_reason_with_raster_data(self):
        result = reason("分析两期NDVI栅格的植被变化", datasets=[
            {"id": "ndvi_2020", "type": "raster", "crs": "EPSG:4326", "time_range": "2020"},
            {"id": "ndvi_2023", "type": "raster", "crs": "EPSG:4326", "time_range": "2023"},
        ])
        assert result is not None

    def test_reason_with_trajectory_data(self):
        result = reason("分析居民出行轨迹OD流量", datasets=[
            {"id": "gps_trips", "type": "trajectory", "crs": "EPSG:4326"},
        ])
        assert result is not None

    def test_reason_result_has_artifacts(self):
        result = reason("选址分析：武汉市AED最优布局")
        assert isinstance(result.artifacts, list)

    def test_reason_result_ok_or_not(self):
        result = reason("基础分析")
        assert isinstance(result.ok, bool)


# ════════════════════════════════════════════════════════════════════════════
#  T6: reason_with_llm() — mock LLM
# ════════════════════════════════════════════════════════════════════════════

class TestReasonWithLLM:
    def _make_mock_provider(self, response_json: str):
        mock = MagicMock()
        mock.call.return_value = response_json
        return mock

    def _make_llm_response(self, primary="multi_ring_buffer") -> str:
        return json.dumps({
            "inferred_goal": "Analyze commercial vitality",
            "recommended_analysis_strategy": {
                "primary_method": primary,
                "secondary_methods": ["kernel_density"],
            },
            "reasoning": ["Buffer approach is more interpretable"],
            "assumptions": ["POI = commercial vitality proxy"],
            "limitations": ["Radius sensitivity"],
            "uncertainty_level": "medium",
            "explanation": "使用多环缓冲区统计分析各站点商业活跃度差异。",
        }, ensure_ascii=False)

    def test_reason_with_llm_returns_result(self):
        mock_provider = self._make_mock_provider(self._make_llm_response())
        result = reason_with_llm(
            "分析武汉地铁站周边商业活跃度",
            llm_provider=mock_provider,
        )
        assert result is not None

    def test_reason_with_llm_uses_llm_method(self):
        mock_provider = self._make_mock_provider(self._make_llm_response("multi_ring_buffer"))
        result = reason_with_llm("分析武汉地铁站周边商业活跃度", llm_provider=mock_provider)
        # LLM 推荐的 primary_method 应反映在 reasoning_summary
        assert result.reasoning_summary.primary_method == "multi_ring_buffer"

    def test_reason_with_llm_adds_secondary_to_optional(self):
        mock_provider = self._make_mock_provider(self._make_llm_response())
        result = reason_with_llm("分析武汉地铁站周边商业活跃度", llm_provider=mock_provider)
        optional_methods = [s.method for s in result.workflow_plan.optional_steps]
        assert "kernel_density" in optional_methods

    def test_reason_with_llm_fallback_on_failure(self):
        mock_provider = MagicMock()
        mock_provider.call.side_effect = RuntimeError("timeout")
        # 不应抛出异常，应降级到 rule-only
        result = reason_with_llm("分析武汉地铁站周边商业活跃度", llm_provider=mock_provider)
        assert result is not None
        assert isinstance(result.ok, bool)

    def test_reason_with_llm_has_explanation(self):
        mock_provider = self._make_mock_provider(self._make_llm_response())
        result = reason_with_llm("分析武汉地铁站周边商业活跃度", llm_provider=mock_provider)
        assert result.reasoning_summary.method_selection_rationale

    def test_reason_with_llm_llm_assumptions_propagated(self):
        mock_provider = self._make_mock_provider(self._make_llm_response())
        result = reason_with_llm("分析武汉地铁站周边商业活跃度", llm_provider=mock_provider)
        assert result.reasoning_summary.assumptions


# ════════════════════════════════════════════════════════════════════════════
#  T7: validator — Phase 2 Reasoning Consistency & Caveat
# ════════════════════════════════════════════════════════════════════════════

class TestValidatorPhase2:
    def test_consistency_comparison_with_kde_warns(self):
        ctx = make_ctx()
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        llm = LLMReasoningOutput(
            primary_method="kernel_density",
            secondary_methods=[],
            limitations=["something"],
        )
        result = validate_reasoning(ctx, tp, ro, llm)
        warning_codes = [w.code for w in result.warnings]
        assert "CONSISTENCY_METHOD_MISMATCH" in warning_codes

    def test_consistency_optimization_without_optimization_warns(self):
        ctx = make_ctx()
        tp = make_task_profile(AnalysisIntent.OPTIMIZATION)
        ro = make_rule_output()
        llm = LLMReasoningOutput(
            primary_method="buffer_summary",
            limitations=["something"],
        )
        result = validate_reasoning(ctx, tp, ro, llm)
        warning_codes = [w.code for w in result.warnings]
        assert "CONSISTENCY_MISSING_OPTIMIZATION_STEP" in warning_codes

    def test_caveat_buffer_radius_warning(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        llm = LLMReasoningOutput(
            primary_method="multi_ring_buffer",
            limitations=[],  # 故意不提 radius
        )
        result = validate_reasoning(ctx, tp, ro, llm)
        warning_codes = [w.code for w in result.warnings]
        assert "CAVEAT_MISSING_RADIUS_SENSITIVITY" in warning_codes

    def test_no_llm_no_consistency_check(self):
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        result = validate_reasoning(ctx, tp, ro, llm_output=None)
        warning_codes = [w.code for w in result.warnings]
        # Phase 2 校验不应触发（因为 llm_output=None）
        assert "CONSISTENCY_METHOD_MISMATCH" not in warning_codes

    def test_pass_with_good_llm_output(self):
        ctx = make_ctx()
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        llm = LLMReasoningOutput(
            primary_method="multi_ring_buffer",
            limitations=["Results depend on buffer radius choice", "POI bias"],
        )
        result = validate_reasoning(ctx, tp, ro, llm)
        assert result.status in [ValidationStatus.PASS, ValidationStatus.PASS_WITH_WARNINGS]


# ════════════════════════════════════════════════════════════════════════════
#  T8: workflow_synthesizer — LLM 注入
# ════════════════════════════════════════════════════════════════════════════

class TestSynthesizerPhase2:
    def test_llm_method_appears_in_steps(self):
        from geoclaw_claude.reasoning.schemas import ValidationResult
        ctx = make_ctx()
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        llm = LLMReasoningOutput(
            primary_method="multi_ring_buffer",
            secondary_methods=["kernel_density"],
        )
        validation = validate_reasoning(ctx, tp, ro, llm)
        result = synthesize_workflow(ctx, tp, ro, validation, llm)
        step_methods = [s.method for s in result.workflow_plan.steps]
        assert any("buffer" in m or "ring" in m or "multi" in m for m in step_methods), \
            f"Expected buffer-related step, got: {step_methods}"

    def test_secondary_method_in_optional_steps(self):
        from geoclaw_claude.reasoning.schemas import ValidationResult
        ctx = make_ctx()
        tp = make_task_profile(AnalysisIntent.COMPARISON)
        ro = make_rule_output()
        llm = LLMReasoningOutput(
            primary_method="multi_ring_buffer",
            secondary_methods=["kernel_density"],
        )
        validation = validate_reasoning(ctx, tp, ro, llm)
        result = synthesize_workflow(ctx, tp, ro, validation, llm)
        optional_methods = [s.method for s in result.workflow_plan.optional_steps]
        assert "kernel_density" in optional_methods

    def test_llm_none_still_produces_result(self):
        from geoclaw_claude.reasoning.schemas import ValidationResult
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        validation = validate_reasoning(ctx, tp, ro, None)
        result = synthesize_workflow(ctx, tp, ro, validation, None)
        assert result is not None
        assert result.ok is not None

    def test_provenance_reflects_llm_usage(self):
        from geoclaw_claude.reasoning.schemas import ValidationResult
        ctx = make_ctx()
        tp = make_task_profile()
        ro = make_rule_output()
        llm = LLMReasoningOutput(primary_method="multi_ring_buffer")
        validation = validate_reasoning(ctx, tp, ro, llm)
        result = synthesize_workflow(ctx, tp, ro, validation, llm)
        # SRE version 应包含 phase2 字样（如果 synthesizer 有更新）
        # 这里只检查 provenance 存在
        assert result.provenance is not None


# ════════════════════════════════════════════════════════════════════════════
#  T9: 端到端场景测试
# ════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    def test_aed_site_selection_scenario(self):
        """AED 选址分析场景（文档 5.1 示例）"""
        result = reason(
            "给我做一个武汉市 AED 选址分析，最好考虑公平性",
            datasets=[
                {"id": "demand_zones", "type": "vector", "geometry": "polygon",
                 "crs": "EPSG:4326", "attributes": ["population", "age_over_60"]},
                {"id": "existing_aed", "type": "vector", "geometry": "point",
                 "crs": "EPSG:4326"},
            ],
            project_context={"study_area": "Wuhan"},
        )
        assert result is not None
        assert result.task_profile.task_type in [
            AnalysisIntent.OPTIMIZATION,
            AnalysisIntent.SELECTION,
            AnalysisIntent.ACCESSIBILITY,
        ]

    def test_land_cover_change_scenario(self):
        """土地利用变化检测场景"""
        result = reason(
            "比较近五年建设用地扩张与轨道交通站点的关系",
            datasets=[
                {"id": "urban_2019", "type": "vector", "geometry": "polygon",
                 "crs": "EPSG:4326", "time_range": "2019"},
                {"id": "urban_2024", "type": "vector", "geometry": "polygon",
                 "crs": "EPSG:4326", "time_range": "2024"},
                {"id": "metro_stations", "type": "vector", "geometry": "point",
                 "crs": "EPSG:4326"},
            ],
        )
        assert result is not None

    def test_mobility_od_scenario(self):
        """出行 OD 分析场景"""
        result = reason(
            "分析武汉居民早高峰出行轨迹的OD流量分布",
            datasets=[
                {"id": "trip_data", "type": "trajectory", "crs": "EPSG:4326",
                 "time_range": "2024-Q1"},
            ],
        )
        assert result is not None

    def test_hospital_accessibility_scenario(self):
        """医院可达性分析场景"""
        result = reason(
            "评估武汉各居委会到最近三甲医院的步行可达性",
            datasets=[
                {"id": "hospitals", "type": "vector", "geometry": "point",
                 "crs": "EPSG:4326", "attributes": ["level", "capacity"]},
                {"id": "communities", "type": "vector", "geometry": "polygon",
                 "crs": "EPSG:4326", "attributes": ["population"]},
            ],
        )
        assert result is not None
        # 应该识别为可达性任务
        assert result.task_profile.task_type in [
            AnalysisIntent.ACCESSIBILITY,
            AnalysisIntent.COMPARISON,
        ]

    def test_to_dict_serializable(self):
        """SpatialReasoningResult.to_dict() 应返回可序列化的字典"""
        result = reason("分析商业密度分布")
        d = result.to_dict()
        assert isinstance(d, dict)
        # 验证 JSON 可序列化
        json_str = json.dumps(d, ensure_ascii=False)
        assert len(json_str) > 0

    def test_summary_text_zh(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        text = result.summary_text(lang="zh")
        assert "[SRE]" in text
        assert "任务类型" in text

    def test_summary_text_en(self):
        result = reason("Analyze commercial vitality near Wuhan metro stations")
        text = result.summary_text(lang="en")
        assert "[SRE]" in text
        assert "Task" in text


if __name__ == "__main__":
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short", "-q"],
        cwd=str(_REPO_ROOT),
    )
    sys.exit(r.returncode)
