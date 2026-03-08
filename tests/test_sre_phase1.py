"""
tests/test_sre_phase1.py
=======================
GeoClaw v3.0.0-alpha — Spatial Reasoning Engine Phase 1 完整测试套件

覆盖范围：
  T01-T06  schemas.py        数据类与枚举
  T07-T12  input_adapter.py  输入标准化
  T13-T18  context_builder.py 预处理层
  T19-T27  task_typer.py     任务类型识别
  T28-T38  rule_engine.py    规则层
  T39-T46  validator.py      校验层
  T47-T52  workflow_synthesizer.py 工作流组装
  T53-T58  __init__.reason() 端到端集成
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent, GeoEntityType, SpatialRelation, OutputType,
    CRSStatus, ValidationStatus, TemporalStatus,
    DatasetMeta, UserContext, ProjectContext, PlannerHints, SystemPolicy,
    ReasoningInput, ReasoningContext,
    RuleEngineOutput, RuleViolation, MethodCandidate,
    ValidationResult, ValidationWarning,
    TaskProfile, InputAssessment, ReasoningSummary,
    WorkflowStep, WorkflowPlan, ArtifactSpec, Provenance,
    SpatialReasoningResult, LLMReasoningOutput,
)
from geoclaw_claude.reasoning.input_adapter import (
    build_reasoning_input, from_agent_context,
)
from geoclaw_claude.reasoning.context_builder import build_reasoning_context
from geoclaw_claude.reasoning.task_typer import classify_task
from geoclaw_claude.reasoning.rule_engine import run_rule_engine
from geoclaw_claude.reasoning.validator import validate_reasoning
from geoclaw_claude.reasoning.workflow_synthesizer import synthesize_workflow
from geoclaw_claude.reasoning import reason


# ══════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def wuhan_datasets():
    return [
        DatasetMeta(
            id="metro_stations", type="vector", geometry="point",
            crs="EPSG:4326",
            extent=[113.7, 29.9, 115.1, 31.4],
            attributes=["station_id", "name", "line"],
        ),
        DatasetMeta(
            id="poi_commerce", type="vector", geometry="point",
            crs="EPSG:4326",
            extent=[113.8, 29.95, 115.0, 31.3],
            time_range="2025",
            attributes=["poi_id", "category", "name"],
        ),
    ]

@pytest.fixture
def wuhan_input(wuhan_datasets):
    return build_reasoning_input(
        query="分析武汉地铁站周边商业活跃度差异，并输出地图和摘要",
        datasets=wuhan_datasets,
        user_context={"language": "zh-CN", "expertise": "GIS expert",
                      "output_preference": ["map", "summary"]},
        project_context={"study_area": "武汉", "default_crs": "EPSG:4547",
                         "analysis_goal": "urban commercial vitality"},
        system_policy={"readonly_inputs": True},
    )

@pytest.fixture
def wuhan_ctx(wuhan_input):
    return build_reasoning_context(wuhan_input)

@pytest.fixture
def wuhan_task(wuhan_ctx):
    return classify_task(wuhan_ctx)

@pytest.fixture
def wuhan_rule(wuhan_ctx, wuhan_task):
    return run_rule_engine(wuhan_ctx, wuhan_task)


# ══════════════════════════════════════════════════════════════════════════════
#  T01-T06  schemas.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSchemas:
    def test_T01_enums_have_expected_values(self):
        assert AnalysisIntent.COMPARISON.value == "comparison"
        assert GeoEntityType.TRAJECTORY.value  == "trajectory"
        assert SpatialRelation.NEAREST.value   == "nearest"
        assert OutputType.MAP.value            == "map"
        assert ValidationStatus.FAIL.value     == "fail"

    def test_T02_dataset_meta_is_geographic_crs(self):
        d = DatasetMeta(id="x", crs="EPSG:4326")
        assert d.is_geographic_crs() is True
        d2 = DatasetMeta(id="y", crs="EPSG:4547")
        assert d2.is_geographic_crs() is False

    def test_T03_dataset_meta_no_crs_not_geographic(self):
        d = DatasetMeta(id="z")
        assert d.is_geographic_crs() is False

    def test_T04_dataset_meta_has_temporal(self):
        d = DatasetMeta(id="a", time_range="2024")
        assert d.has_temporal() is True
        d2 = DatasetMeta(id="b")
        assert d2.has_temporal() is False

    def test_T05_spatial_reasoning_result_ok_property(self):
        r = SpatialReasoningResult()
        assert r.ok is True   # 默认 PASS
        r.validation.status = ValidationStatus.FAIL
        r.validation.blocking_errors = ["error"]
        assert r.ok is False

    def test_T06_spatial_reasoning_result_to_dict(self):
        r = SpatialReasoningResult()
        d = r.to_dict()
        assert isinstance(d, dict)
        assert "task_profile" in d
        assert "workflow_plan" in d
        assert "validation" in d

    def test_T06b_summary_text(self):
        r = SpatialReasoningResult()
        text = r.summary_text(lang="zh")
        assert "[SRE]" in text
        text_en = r.summary_text(lang="en")
        assert "Task:" in text_en


# ══════════════════════════════════════════════════════════════════════════════
#  T07-T12  input_adapter.py
# ══════════════════════════════════════════════════════════════════════════════

class TestInputAdapter:
    def test_T07_build_from_dicts(self):
        ri = build_reasoning_input(
            query="test query",
            datasets=[{"id": "ds1", "type": "vector", "crs": "EPSG:4326"}],
            user_context={"language": "zh"},
        )
        assert ri.query == "test query"
        assert len(ri.datasets) == 1
        assert ri.datasets[0].id == "ds1"
        assert ri.user_context.language == "zh-CN"

    def test_T08_build_from_dataclass(self, wuhan_datasets):
        ri = build_reasoning_input(
            query="test",
            datasets=wuhan_datasets,
        )
        assert len(ri.datasets) == 2
        assert isinstance(ri.datasets[0], DatasetMeta)

    def test_T09_language_normalization(self):
        ri = build_reasoning_input("q", user_context={"language": "chinese"})
        assert ri.user_context.language == "zh-CN"
        ri2 = build_reasoning_input("q", user_context={"language": "english"})
        assert ri2.user_context.language == "en-US"

    def test_T10_default_system_policy(self):
        ri = build_reasoning_input("q")
        assert ri.system_policy.readonly_inputs is True
        assert ri.system_policy.allow_unregistered_tools is False

    def test_T11_from_agent_context(self):
        agent_ctx = {
            "user_profile_hint": "preferred language: zh",
            "available_layers": "stations, poi",
            "current_city": "武汉",
        }
        ri = from_agent_context("分析武汉地铁站", agent_ctx)
        assert ri.user_context.language == "zh-CN"
        assert ri.project_context.study_area == "武汉"
        assert len(ri.datasets) == 2

    def test_T12_query_is_stripped(self):
        ri = build_reasoning_input("  test  ")
        assert ri.query == "test"


# ══════════════════════════════════════════════════════════════════════════════
#  T13-T18  context_builder.py
# ══════════════════════════════════════════════════════════════════════════════

class TestContextBuilder:
    def test_T13_builds_context_from_input(self, wuhan_input):
        ctx = build_reasoning_context(wuhan_input)
        assert ctx.query == wuhan_input.query
        assert ctx.normalized_language == "zh"

    def test_T14_geo_terms_extracted(self, wuhan_ctx):
        assert "武汉" in wuhan_ctx.geo_terms

    def test_T15_study_area_from_query(self, wuhan_ctx):
        assert wuhan_ctx.study_area == "武汉"

    def test_T16_dataset_ids_populated(self, wuhan_ctx):
        assert "metro_stations" in wuhan_ctx.dataset_ids
        assert "poi_commerce"    in wuhan_ctx.dataset_ids

    def test_T17_time_range_from_dataset(self, wuhan_ctx):
        # poi_commerce 有 time_range="2025"
        assert wuhan_ctx.time_range is not None

    def test_T18_english_query_context(self):
        ri = build_reasoning_input(
            query="analyze accessibility in London",
            user_context={"language": "en"},
        )
        ctx = build_reasoning_context(ri)
        assert ctx.normalized_language == "en"
        assert "london" in [t.lower() for t in ctx.geo_terms]


# ══════════════════════════════════════════════════════════════════════════════
#  T19-T27  task_typer.py
# ══════════════════════════════════════════════════════════════════════════════

class TestTaskTyper:
    def test_T19_wuhan_metro_is_comparison(self, wuhan_task):
        assert wuhan_task.task_type == AnalysisIntent.COMPARISON

    def test_T20_confidence_is_reasonable(self, wuhan_task):
        assert 0.0 < wuhan_task.confidence <= 1.0

    def test_T21_entities_include_point(self, wuhan_task):
        assert GeoEntityType.POINT in wuhan_task.entities

    def test_T22_output_map_detected(self, wuhan_task):
        assert OutputType.MAP in wuhan_task.output_intent

    def test_T23_accessibility_query(self):
        ri  = build_reasoning_input(
            "分析各医院的15分钟步行可达性范围",
            datasets=[DatasetMeta(id="hospitals", type="vector", geometry="point",
                                  crs="EPSG:4326")],
        )
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        assert task.task_type == AnalysisIntent.ACCESSIBILITY

    def test_T24_change_detection_query(self):
        ri  = build_reasoning_input("比较近五年建设用地扩张变化")
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        assert task.task_type == AnalysisIntent.CHANGE_DETECTION

    def test_T25_optimization_query(self):
        ri  = build_reasoning_input("做一个学校 AED 最优选址分析")
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        assert task.task_type == AnalysisIntent.OPTIMIZATION

    def test_T26_domain_urban_computing(self, wuhan_task):
        assert wuhan_task.domain == "urban_computing"

    def test_T27_unknown_for_empty_query(self):
        ri  = build_reasoning_input("hello world")
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        # 无地理关键词，可能是 UNKNOWN 或置信度极低
        assert task.confidence <= 0.5 or task.task_type == AnalysisIntent.UNKNOWN


# ══════════════════════════════════════════════════════════════════════════════
#  T28-T38  rule_engine.py
# ══════════════════════════════════════════════════════════════════════════════

class TestRuleEngine:
    def test_T28_crs_needs_reprojection_for_wuhan(self, wuhan_rule):
        assert wuhan_rule.crs_status == CRSStatus.NEEDS_REPROJECTION

    def test_T29_has_preconditions_for_reprojection(self, wuhan_rule):
        assert len(wuhan_rule.preconditions) > 0
        actions = [p["action"] for p in wuhan_rule.preconditions]
        assert "reproject_layer" in actions

    def test_T30_hard_constraints_contain_crs_rule(self, wuhan_rule):
        constraints_str = " ".join(wuhan_rule.hard_constraints)
        assert "reproject" in constraints_str.lower() or "crs" in constraints_str.lower()

    def test_T31_method_candidates_not_empty(self, wuhan_rule):
        assert len(wuhan_rule.method_candidates) > 0

    def test_T32_primary_method_is_buffer_for_comparison(self, wuhan_rule):
        assert wuhan_rule.method_candidates[0].method_id == "multi_ring_buffer_summary"

    def test_T33_target_metrics_for_comparison(self, wuhan_rule):
        assert "count" in wuhan_rule.target_metrics
        assert "density" in wuhan_rule.target_metrics

    def test_T34_crs_ok_when_projected(self):
        ri = build_reasoning_input(
            "分析武汉商业密度",
            datasets=[DatasetMeta(id="d1", crs="EPSG:4547", geometry="point")],
        )
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        rule = run_rule_engine(ctx, task)
        # 投影坐标系，不应有 NEEDS_REPROJECTION
        crs_errors = [v for v in rule.violations
                      if v.rule_id == "CRS_BUFFER_REQUIRES_PROJECTED"]
        assert len(crs_errors) == 0

    def test_T35_crs_mismatch_detected(self):
        ri = build_reasoning_input(
            "叠加分析",
            datasets=[
                DatasetMeta(id="a", crs="EPSG:4326", geometry="point"),
                DatasetMeta(id="b", crs="EPSG:4547", geometry="polygon"),
            ],
        )
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        rule = run_rule_engine(ctx, task)
        assert rule.crs_status == CRSStatus.CRS_MISMATCH

    def test_T36_change_detection_no_multiperiod_is_error(self):
        ri = build_reasoning_input(
            "比较近五年建设用地扩张变化",
            datasets=[DatasetMeta(id="land", type="raster", time_range=None)],
        )
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        rule = run_rule_engine(ctx, task)
        error_ids = [v.rule_id for v in rule.violations if v.severity == "error"]
        assert "TEMPORAL_CHANGE_REQUIRES_MULTIPERIOD" in error_ids

    def test_T37_scale_warnings_for_comparison(self, wuhan_rule):
        # 缓冲区半径敏感性警告
        assert any("buffer_radius" in w for w in wuhan_rule.warnings)

    def test_T38_safety_readonly_check(self, wuhan_rule):
        # 默认无 writable 数据集，不应有安全警告
        safety_violations = [v for v in wuhan_rule.violations if v.rule_set == "safety"]
        assert len(safety_violations) == 0


# ══════════════════════════════════════════════════════════════════════════════
#  T39-T46  validator.py
# ══════════════════════════════════════════════════════════════════════════════

class TestValidator:
    def test_T39_wuhan_validation_pass_with_warnings(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        # CRS error → 应该是 FAIL 或 PASS_WITH_WARNINGS
        # （取决于 CRS_BUFFER 是 error，所以是 FAIL）
        assert val.status in (ValidationStatus.FAIL, ValidationStatus.PASS_WITH_WARNINGS)

    def test_T40_blocking_errors_when_crs_error(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        # EPSG:4326 + buffer → CRS error → blocking
        if val.status == ValidationStatus.FAIL:
            assert len(val.blocking_errors) > 0

    def test_T41_warnings_contain_buffer_sensitivity(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        warning_codes = [w.code for w in val.warnings]
        assert "BUFFER_RADIUS_SENSITIVITY" in warning_codes

    def test_T42_required_preconditions_populated(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        assert len(val.required_preconditions) > 0

    def test_T43_policy_compliance_keys(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        assert "readonly_inputs"       in val.policy_compliance
        assert "workspace_output_only" in val.policy_compliance

    def test_T44_pass_when_no_violations(self):
        ri   = build_reasoning_input(
            "统计各区域面积",
            datasets=[DatasetMeta(id="zones", crs="EPSG:4547",
                                  geometry="polygon",
                                  extent=[113.0, 29.0, 116.0, 32.0])],
        )
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        rule = run_rule_engine(ctx, task)
        val  = validate_reasoning(ctx, task, rule, None)
        # 投影坐标 + polygon → 应该不是 FAIL
        assert val.status != ValidationStatus.FAIL

    def test_T45_feasibility_accessibility_no_network_warning(self):
        ri = build_reasoning_input(
            "分析医院15分钟步行可达性",
            datasets=[DatasetMeta(id="hospitals", crs="EPSG:4547", geometry="point")],
        )
        ctx  = build_reasoning_context(ri)
        task = classify_task(ctx)
        rule = run_rule_engine(ctx, task)
        val  = validate_reasoning(ctx, task, rule, None)
        codes = [w.code for w in val.warnings]
        assert "ACCESSIBILITY_NO_NETWORK_DATA" in codes

    def test_T46_validation_result_passed_property(self):
        val = ValidationResult(status=ValidationStatus.PASS)
        assert val.passed is True
        val2 = ValidationResult(status=ValidationStatus.FAIL)
        assert val2.passed is False


# ══════════════════════════════════════════════════════════════════════════════
#  T47-T52  workflow_synthesizer.py
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkflowSynthesizer:
    def test_T47_synthesize_returns_result(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val    = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        result = synthesize_workflow(wuhan_ctx, wuhan_task, wuhan_rule, val, None)
        assert isinstance(result, SpatialReasoningResult)

    def test_T48_workflow_has_steps(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val    = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        result = synthesize_workflow(wuhan_ctx, wuhan_task, wuhan_rule, val, None)
        assert len(result.workflow_plan.steps) > 0

    def test_T49_workflow_preconditions_include_reprojection(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val    = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        result = synthesize_workflow(wuhan_ctx, wuhan_task, wuhan_rule, val, None)
        actions = [p.get("action") for p in result.workflow_plan.preconditions]
        assert "reproject_layer" in actions

    def test_T50_artifacts_include_map(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val    = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        result = synthesize_workflow(wuhan_ctx, wuhan_task, wuhan_rule, val, None)
        types  = [a.type for a in result.artifacts]
        assert "map" in types

    def test_T51_provenance_set(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val    = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        result = synthesize_workflow(wuhan_ctx, wuhan_task, wuhan_rule, val, None)
        assert result.provenance.engine_version.startswith("sre-0.")
        assert wuhan_ctx.query in result.provenance.source_query

    def test_T52_reasoning_summary_has_primary_method(self, wuhan_ctx, wuhan_task, wuhan_rule):
        val    = validate_reasoning(wuhan_ctx, wuhan_task, wuhan_rule, None)
        result = synthesize_workflow(wuhan_ctx, wuhan_task, wuhan_rule, val, None)
        assert result.reasoning_summary.primary_method != ""


# ══════════════════════════════════════════════════════════════════════════════
#  T53-T58  端到端集成  reason()
# ══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    def test_T53_reason_returns_result(self):
        result = reason("分析武汉地铁站周边商业活跃度")
        assert isinstance(result, SpatialReasoningResult)

    def test_T54_reason_with_full_context(self):
        result = reason(
            query    = "分析武汉地铁站周边商业活跃度差异，输出地图和摘要",
            datasets = [
                {"id": "metro", "type": "vector", "geometry": "point",
                 "crs": "EPSG:4326", "extent": [113.7,29.9,115.1,31.4]},
                {"id": "poi",   "type": "vector", "geometry": "point",
                 "crs": "EPSG:4326", "extent": [113.8,29.95,115.0,31.3],
                 "time_range": "2025"},
            ],
            user_context    = {"language": "zh-CN", "expertise": "GIS expert"},
            project_context = {"study_area": "武汉", "default_crs": "EPSG:4547"},
        )
        assert result.task_profile.task_type == AnalysisIntent.COMPARISON
        assert len(result.workflow_plan.steps) > 0

    def test_T55_reason_accessibility(self):
        result = reason(
            "分析各医院的15分钟步行可达性",
            datasets=[{"id": "hospitals", "crs": "EPSG:4547", "geometry": "point"}],
        )
        assert result.task_profile.task_type == AnalysisIntent.ACCESSIBILITY

    def test_T56_reason_change_detection_fails_without_data(self):
        result = reason("比较近五年建设用地扩张变化")
        # 没有时序数据，预期有 warning 或 error
        assert result.has_warnings or not result.ok

    def test_T57_reason_summary_text_works(self):
        result = reason("分析武汉商业密度")
        text = result.summary_text()
        assert "[SRE]" in text

    def test_T58_to_dict_is_serializable(self):
        import json
        result = reason(
            "分析武汉地铁站周边商业活跃度",
            datasets=[{"id": "metro", "crs": "EPSG:4326", "geometry": "point"}],
        )
        d = result.to_dict()
        # 应该能 JSON 序列化
        json_str = json.dumps(d, ensure_ascii=False)
        assert "task_profile" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
