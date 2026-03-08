# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.schemas
=====================================
SRE 所有数据类定义。

层次：
  输入层  → ReasoningInput
  预处理  → ReasoningContext
  规则层  → RuleEngineOutput
  LLM层   → LLMReasoningOutput（Phase 2，此处预留）
  校验层  → ValidationResult
  输出层  → SpatialReasoningResult（含 7 个子 Schema）

枚举：
  AnalysisIntent   — 9 种分析意图
  GeoEntityType    — 10 种地理实体类型
  SpatialRelation  — 9 种空间关系
  OutputType       — 6 种输出类型
  CRSStatus        — CRS 评估状态
  ValidationStatus — 校验结果状态

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ══════════════════════════════════════════════════════════════════════════════
#  枚举
# ══════════════════════════════════════════════════════════════════════════════

class AnalysisIntent(str, Enum):
    """9 种分析意图（文档 4.1）"""
    SELECTION        = "selection"
    COMPARISON       = "comparison"
    CLUSTERING       = "clustering"
    ACCESSIBILITY    = "accessibility"
    OPTIMIZATION     = "optimization"
    CHANGE_DETECTION = "change_detection"
    PREDICTION       = "prediction"
    EXPLANATION      = "explanation"
    SUMMARIZATION    = "summarization"
    UNKNOWN          = "unknown"


class GeoEntityType(str, Enum):
    """10 种地理实体类型（文档 4.1）"""
    POINT      = "point"
    LINE       = "line"
    POLYGON    = "polygon"
    RASTER     = "raster"
    GRID       = "grid"
    TRAJECTORY = "trajectory"
    NETWORK    = "network"
    REGION     = "region"
    FACILITY   = "facility"
    EVENT      = "event"


class SpatialRelation(str, Enum):
    """9 种空间关系（文档 4.1）"""
    WITHIN          = "within"
    INTERSECTS      = "intersects"
    CONTAINS        = "contains"
    OVERLAPS        = "overlaps"
    NEAREST         = "nearest"
    UPSTREAM        = "upstream"
    DOWNSTREAM      = "downstream"
    ACCESSIBLE_FROM = "accessible_from"
    CO_LOCATED_WITH = "co_located_with"


class OutputType(str, Enum):
    """6 种输出类型（文档 4.1）"""
    MAP            = "map"
    TABLE          = "table"
    REPORT         = "report"
    GEOFILE        = "geofile"
    WORKFLOW       = "workflow"
    DASHBOARD_SPEC = "dashboard_spec"


class CRSStatus(str, Enum):
    """CRS 评估状态"""
    OK                  = "ok"                   # 所有图层 CRS 一致且适合分析
    NEEDS_REPROJECTION  = "needs_reprojection"    # 地理坐标系，需投影
    CRS_MISMATCH        = "crs_mismatch"          # 多图层 CRS 不一致
    UNKNOWN             = "unknown"               # CRS 未知


class ValidationStatus(str, Enum):
    """校验结果状态（文档 6.5）"""
    PASS          = "pass"               # 无任何问题
    PASS_WITH_WARNINGS = "pass_with_warnings"  # 通过但有警告
    FAIL          = "fail"               # 存在阻断性错误


class TemporalStatus(str, Enum):
    """时序数据状态"""
    SINGLE_PERIOD  = "single_period_analysis"
    MULTI_PERIOD   = "multi_period_available"
    NO_TEMPORAL    = "no_temporal_info"
    MISMATCH       = "temporal_mismatch"


# ══════════════════════════════════════════════════════════════════════════════
#  输入 Schema  →  ReasoningInput
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DatasetMeta:
    """
    单个数据集的元信息（文档 1.2 C 部分）。

    Attributes:
        id          : 数据集标识符（在本次任务中引用用）
        type        : 数据类型：vector / raster / trajectory / network
        geometry    : 几何类型：point / linestring / polygon / multipolygon 等
        crs         : EPSG 字符串，如 "EPSG:4326"
        extent      : 空间范围 [min_lng, min_lat, max_lng, max_lat]
        time_range  : 时间范围（字符串描述或 None）
        resolution  : 栅格分辨率（矢量为 None）
        attributes  : 字段名列表
        path        : 本地文件路径（可选）
        writable    : 是否可写（默认 False，原始数据应为只读）
        extra       : 其他元信息
    """
    id:         str
    type:       str                          = "vector"
    geometry:   Optional[str]               = None
    crs:        Optional[str]               = None
    extent:     Optional[List[float]]       = None
    time_range: Optional[str]               = None
    resolution: Optional[float]             = None
    attributes: List[str]                   = field(default_factory=list)
    path:       Optional[str]               = None
    writable:   bool                        = False
    extra:      Dict[str, Any]              = field(default_factory=dict)

    def is_geographic_crs(self) -> bool:
        """判断是否为地理坐标系（非投影）"""
        if not self.crs:
            return False
        crs_upper = self.crs.upper()
        # 常见地理坐标系 EPSG
        geographic_epsg = {"4326", "4490", "4269", "4267", "4258"}
        for code in geographic_epsg:
            if code in crs_upper:
                return True
        return False

    def has_temporal(self) -> bool:
        return self.time_range is not None and self.time_range.strip() != ""


@dataclass
class UserContext:
    """用户偏好上下文（文档 1.2 B 部分）"""
    language:           str        = "zh-CN"
    expertise:          str        = "general"    # beginner / intermediate / expert / GIS expert
    tool_preference:    List[str]  = field(default_factory=list)
    output_preference:  List[str]  = field(default_factory=list)   # OutputType strings
    extra:              Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectContext:
    """项目级上下文（文档 1.2 B 部分）"""
    study_area:      Optional[str]  = None
    default_crs:     Optional[str]  = None
    analysis_goal:   Optional[str]  = None
    extra:           Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerHints:
    """上游 Planner 的初步猜测（文档 1.2 D 部分）"""
    candidate_task_type: Optional[str]    = None
    candidate_methods:   List[str]        = field(default_factory=list)
    extra:               Dict[str, Any]   = field(default_factory=dict)


@dataclass
class SystemPolicy:
    """系统级安全策略（文档 1.2 E 部分 / soul.md）"""
    readonly_inputs:           bool = True
    require_output_workspace:  bool = True
    allow_unregistered_tools:  bool = False
    extra:                     Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningInput:
    """
    SRE 标准化输入对象（文档 1.2）。

    由 InputAdapter 从原始用户请求组装而成，
    是进入 SRE 各子层的统一入口。
    """
    query:           str
    user_context:    UserContext      = field(default_factory=UserContext)
    project_context: ProjectContext   = field(default_factory=ProjectContext)
    datasets:        List[DatasetMeta]= field(default_factory=list)
    planner_hints:   PlannerHints     = field(default_factory=PlannerHints)
    system_policy:   SystemPolicy     = field(default_factory=SystemPolicy)


# ══════════════════════════════════════════════════════════════════════════════
#  预处理层  →  ReasoningContext
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ReasoningContext:
    """
    经预处理后的标准化推理上下文（文档 1.3）。

    在 ReasoningInput 基础上补充了：
      - 标准化语言代码
      - 抽取的地理术语
      - 歧义标记
      - 对齐后的研究区 / 时间范围
    """
    # 原始输入（保留引用）
    source:             ReasoningInput

    # 预处理结果
    normalized_language: str               = "zh"
    geo_terms:           List[str]          = field(default_factory=list)   # 抽取到的地理实体词
    ambiguities:         List[str]          = field(default_factory=list)   # 歧义点描述
    study_area:          Optional[str]      = None
    time_range:          Optional[str]      = None
    dataset_ids:         List[str]          = field(default_factory=list)

    # 快捷访问
    @property
    def query(self) -> str:
        return self.source.query

    @property
    def datasets(self) -> List[DatasetMeta]:
        return self.source.datasets

    @property
    def user_context(self) -> UserContext:
        return self.source.user_context

    @property
    def project_context(self) -> ProjectContext:
        return self.source.project_context

    @property
    def system_policy(self) -> SystemPolicy:
        return self.source.system_policy

    @property
    def planner_hints(self) -> PlannerHints:
        return self.source.planner_hints


# ══════════════════════════════════════════════════════════════════════════════
#  任务分类结果  →  TaskProfile
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TaskProfile:
    """
    任务分类结果（文档 7.2 A）。

    由 TaskTyper 生成，描述任务被识别成什么类型。
    """
    task_type:      AnalysisIntent         = AnalysisIntent.UNKNOWN
    subtask_types:  List[AnalysisIntent]   = field(default_factory=list)
    entities:       List[GeoEntityType]    = field(default_factory=list)
    relations:      List[SpatialRelation]  = field(default_factory=list)
    domain:         str                    = "general"
    analysis_goal:  Optional[str]          = None
    output_intent:  List[OutputType]       = field(default_factory=list)
    confidence:     float                  = 0.0    # 0-1 分类置信度


# ══════════════════════════════════════════════════════════════════════════════
#  规则层输出  →  RuleEngineOutput
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RuleViolation:
    """单条规则违反记录"""
    rule_id:    str
    rule_set:   str                # crs / topology / temporal / scale / safety
    severity:   str                # error / warning / info
    message:    str
    dataset_id: Optional[str] = None


@dataclass
class MethodCandidate:
    """规则层推荐的分析方法候选"""
    method_id:   str
    category:    str               # proximity / accessibility / site_selection / ...
    description: str               = ""
    priority:    int               = 1    # 越小越优先


@dataclass
class RuleEngineOutput:
    """
    规则层处理结果（文档 4.4）。

    供 LLM 层和校验层消费。
    """
    task_candidates:     List[str]            = field(default_factory=list)
    resolved_entities:   List[str]            = field(default_factory=list)
    resolved_relations:  List[str]            = field(default_factory=list)
    target_metrics:      List[str]            = field(default_factory=list)
    hard_constraints:    List[str]            = field(default_factory=list)   # 必须执行的前置操作
    method_candidates:   List[MethodCandidate]= field(default_factory=list)
    violations:          List[RuleViolation]  = field(default_factory=list)
    warnings:            List[str]            = field(default_factory=list)
    crs_status:          CRSStatus            = CRSStatus.UNKNOWN
    preconditions:       List[Dict[str,Any]]  = field(default_factory=list)  # 具体前置操作步骤


# ══════════════════════════════════════════════════════════════════════════════
#  LLM 层输出（Phase 2 预留）  →  LLMReasoningOutput
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LLMReasoningOutput:
    """
    LLM Geo Reasoner 输出（文档 5.5）。
    Phase 2 实现，Phase 1 中传入 None。
    """
    inferred_goal:         str                 = ""
    primary_method:        str                 = ""
    secondary_methods:     List[str]           = field(default_factory=list)
    method_rationale:      List[str]           = field(default_factory=list)
    assumptions:           List[str]           = field(default_factory=list)
    limitations:           List[str]           = field(default_factory=list)
    explanation:           str                 = ""
    uncertainty_level:     str                 = "unknown"   # low / medium / high / unknown
    raw_response:          Optional[str]       = None


# ══════════════════════════════════════════════════════════════════════════════
#  校验层输出  →  ValidationResult
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ValidationWarning:
    """单条校验警告"""
    code:    str
    message: str
    detail:  str = ""


@dataclass
class ValidationResult:
    """
    校验层结果（文档 6.5 / 7.2 E）。
    """
    status:               ValidationStatus          = ValidationStatus.PASS
    blocking_errors:      List[str]                  = field(default_factory=list)
    warnings:             List[ValidationWarning]    = field(default_factory=list)
    required_preconditions: List[str]                = field(default_factory=list)
    revisions_applied:    List[str]                  = field(default_factory=list)
    policy_compliance:    Dict[str, bool]            = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status != ValidationStatus.FAIL


# ══════════════════════════════════════════════════════════════════════════════
#  SpatialReasoningResult 的子 Schema
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class InputAssessment:
    """输入数据与上下文的适配情况（文档 7.2 B）"""
    datasets_used:       List[str]   = field(default_factory=list)
    crs_status:          CRSStatus   = CRSStatus.UNKNOWN
    extent_status:       str         = "unknown"    # overlap_confirmed / no_overlap / unknown
    temporal_status:     TemporalStatus = TemporalStatus.NO_TEMPORAL
    data_quality_notes:  List[str]   = field(default_factory=list)
    missing_data:        List[str]   = field(default_factory=list)


@dataclass
class ParameterSensitivityHint:
    """单个参数的敏感性说明（Phase 3）"""
    parameter_name:  str    # 参数名称，如 "buffer_radius_m"
    sensitivity:     str    # low / medium / high
    description:     str    # 敏感性说明
    suggested_range: str    = ""  # 建议取值范围，如 "300–800m"
    method_id:       str    = ""  # 所属方法 ID


# ── Phase 3：分析模式枚举 ─────────────────────────────────────────────────────

class AnalysisMode(str, Enum):
    """分析模式（Phase 3：exploratory vs causal 区分）"""
    EXPLORATORY   = "exploratory"    # 探索性：发现规律、生成假设
    CONFIRMATORY  = "confirmatory"   # 验证性：检验已有假设
    CAUSAL        = "causal"         # 因果推断：控制混淆变量
    DESCRIPTIVE   = "descriptive"    # 描述性：空间模式概述
    UNKNOWN       = "unknown"


@dataclass
class ReasoningSummary:
    """方法选择与理由（文档 7.2 C，Phase 3 扩展）"""
    primary_method:             str           = ""
    secondary_methods:          List[str]     = field(default_factory=list)
    method_selection_rationale: List[str]     = field(default_factory=list)
    assumptions:                List[str]     = field(default_factory=list)
    limitations:                List[str]     = field(default_factory=list)
    uncertainty_level:          str           = "unknown"   # low / medium / high / unknown
    # Phase 3 新增
    uncertainty_score:          float         = -1.0        # 0-1，-1 表示未评估
    analysis_mode:              str           = "unknown"   # exploratory / confirmatory / causal / descriptive
    parameter_sensitivity:      List["ParameterSensitivityHint"] = field(default_factory=list)
    maup_risk:                  str           = "unknown"   # low / medium / high / not_applicable
    scale_effects_notes:        List[str]     = field(default_factory=list)


@dataclass
class WorkflowStep:
    """单个工作流步骤（文档 7.2 D）"""
    step_id:         str
    operation_type:  str
    method:          str
    inputs:          List[str]          = field(default_factory=list)
    parameters:      Dict[str, Any]     = field(default_factory=dict)
    expected_output: str                = ""
    optional:        bool               = False
    notes:           str                = ""


@dataclass
class WorkflowPlan:
    """完整工作流计划（文档 7.2 D）"""
    preconditions:  List[Dict[str, Any]]  = field(default_factory=list)
    steps:          List[WorkflowStep]    = field(default_factory=list)
    optional_steps: List[WorkflowStep]   = field(default_factory=list)


@dataclass
class ArtifactSpec:
    """预期输出产物描述（文档 7.2 F）"""
    type:  str        # vector / raster / table / map / report / workflow
    name:  str
    notes: str = ""


@dataclass
class Provenance:
    """溯源信息（文档 7.2 G）"""
    engine_version:      str   = "sre-0.1-phase1"
    reasoning_timestamp: str   = field(default_factory=lambda: str(time.time()))
    source_query:        str   = ""
    rule_sets_used:      List[str] = field(default_factory=list)
    llm_model:           Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
#  最终输出  →  SpatialReasoningResult
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SpatialReasoningResult:
    """
    SRE 最终输出对象（文档 7.1）。

    供 Tool Router、Report Generator、Memory Manager 共同消费。
    包含 7 个子 Schema：

        task_profile      — 任务类型识别结果
        input_assessment  — 输入数据适配情况
        reasoning_summary — 方法选择与理由
        workflow_plan     — 可执行工作流（核心）
        validation        — 校验报告
        artifacts         — 预期产物列表
        provenance        — 溯源信息

    快捷属性：
        .ok               — bool，是否可以直接执行（无阻断错误）
        .has_warnings     — bool，是否存在警告
        .to_dict()        — 序列化为字典（供存档/日志）
    """
    task_profile:      TaskProfile        = field(default_factory=TaskProfile)
    input_assessment:  InputAssessment    = field(default_factory=InputAssessment)
    reasoning_summary: ReasoningSummary   = field(default_factory=ReasoningSummary)
    workflow_plan:     WorkflowPlan       = field(default_factory=WorkflowPlan)
    validation:        ValidationResult   = field(default_factory=ValidationResult)
    artifacts:         List[ArtifactSpec] = field(default_factory=list)
    provenance:        Provenance         = field(default_factory=Provenance)

    @property
    def ok(self) -> bool:
        """是否无阻断错误，可直接交给执行层"""
        return self.validation.passed

    @property
    def has_warnings(self) -> bool:
        return len(self.validation.warnings) > 0

    @property
    def blocking_errors(self) -> List[str]:
        return self.validation.blocking_errors

    def to_dict(self) -> Dict[str, Any]:
        """序列化为嵌套字典（用于日志/存档/报告）"""
        import dataclasses
        def _convert(obj: Any) -> Any:
            if dataclasses.is_dataclass(obj):
                return {k: _convert(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, list):
                return [_convert(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, Enum):
                return obj.value
            return obj
        return _convert(self)

    def summary_text(self, lang: str = "zh") -> str:
        """生成人类可读的推理摘要（供 GeoAgent 直接展示，Phase 3 增强）"""
        rs = self.reasoning_summary
        score_str = f"{rs.uncertainty_score:.2f}" if rs.uncertainty_score >= 0 else "N/A"

        if lang == "zh":
            lines = [
                f"[SRE] 任务类型: {self.task_profile.task_type.value}",
                f"      分析模式: {rs.analysis_mode}",
                f"      主分析方法: {rs.primary_method or '待定'}",
                f"      不确定性: {rs.uncertainty_level} (评分: {score_str})",
                f"      MAUP 风险: {rs.maup_risk}",
                f"      CRS 状态: {self.input_assessment.crs_status.value}",
                f"      校验状态: {self.validation.status.value}",
                f"      工作流步骤: {len(self.workflow_plan.steps)} 步",
            ]
            if rs.parameter_sensitivity:
                lines.append(f"      参数敏感点: {', '.join(h.parameter_name for h in rs.parameter_sensitivity[:3])}")
            if self.validation.blocking_errors:
                lines.append(f"      ⛔ 阻断错误: {'; '.join(self.validation.blocking_errors)}")
            if self.validation.warnings:
                for w in self.validation.warnings[:3]:
                    lines.append(f"      ⚠ {w.code}: {w.message}")
        else:
            lines = [
                f"[SRE] Task: {self.task_profile.task_type.value}",
                f"      Mode: {rs.analysis_mode}",
                f"      Primary method: {rs.primary_method or 'TBD'}",
                f"      Uncertainty: {rs.uncertainty_level} (score: {score_str})",
                f"      MAUP risk: {rs.maup_risk}",
                f"      CRS: {self.input_assessment.crs_status.value}",
                f"      Validation: {self.validation.status.value}",
                f"      Steps: {len(self.workflow_plan.steps)}",
            ]
            if rs.parameter_sensitivity:
                lines.append(f"      Sensitive params: {', '.join(h.parameter_name for h in rs.parameter_sensitivity[:3])}")
        return "\n".join(lines)
