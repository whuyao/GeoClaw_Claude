# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning — Spatial Reasoning Engine (SRE)

GeoClaw v2.5.0-alpha 核心新增模块。

SRE 是 GeoClaw 的地理推理中枢，位于 Intent Parser 与 Tool Router 之间。
它不直接执行 GIS 工具，而是将自然语言空间任务转换为：
  - 受地理规则约束（Rule Layer）
  - 经 LLM 解释优化（LLM Reasoner Layer，Phase 2）
  - 可被执行层稳定消费的结构化空间工作流（SpatialReasoningResult）

模块结构::

    reasoning/
    ├── schemas.py            # 所有数据类定义（ReasoningInput → SpatialReasoningResult）
    ├── input_adapter.py      # 原始输入 → ReasoningInput 标准化
    ├── context_builder.py    # ReasoningInput → ReasoningContext 预处理
    ├── task_typer.py         # 任务类型识别（9 种意图 × 10 种实体 × 9 种关系）
    ├── rule_engine.py        # GIS 硬规则校验（加载 rules/*.yaml）
    ├── template_library.py   # 方法模板库（加载 templates/*.yaml，Phase 2）
    ├── primitive_resolver.py # 地理原语解析（Phase 2）
    ├── llm_reasoner.py       # LLM 语义推理（Phase 2）
    ├── validator.py          # 一致性与可行性校验
    ├── workflow_synthesizer.py # 组装 SpatialReasoningResult
    ├── rules/                # YAML 硬规则库
    └── templates/            # YAML 方法模板库（Phase 2）

Phase 1 可用入口::

    from geoclaw_claude.reasoning import reason
    result = reason(query="...", datasets=[...], user_context={...})

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

from geoclaw_claude.reasoning.schemas import (
    ReasoningInput,
    DatasetMeta,
    UserContext,
    ProjectContext,
    PlannerHints,
    SystemPolicy,
    ReasoningContext,
    RuleEngineOutput,
    SpatialReasoningResult,
    TaskProfile,
    InputAssessment,
    ReasoningSummary,
    WorkflowPlan,
    WorkflowStep,
    ValidationResult,
    ArtifactSpec,
    Provenance,
    ValidationStatus,
    AnalysisIntent,
    GeoEntityType,
    SpatialRelation,
    OutputType,
)

__all__ = [
    # 主入口
    "reason",
    # 输入 Schema
    "ReasoningInput",
    "DatasetMeta",
    "UserContext",
    "ProjectContext",
    "PlannerHints",
    "SystemPolicy",
    # 中间对象
    "ReasoningContext",
    "RuleEngineOutput",
    # 输出 Schema
    "SpatialReasoningResult",
    "TaskProfile",
    "InputAssessment",
    "ReasoningSummary",
    "WorkflowPlan",
    "WorkflowStep",
    "ValidationResult",
    "ArtifactSpec",
    "Provenance",
    # 枚举
    "ValidationStatus",
    "AnalysisIntent",
    "GeoEntityType",
    "SpatialRelation",
    "OutputType",
    # Phase 2 新增
    "reason_with_llm",
    "LLMReasoningOutput",
    # Phase 3 新增
    "AnalysisMode",
    "ParameterSensitivityHint",
]


def reason(
    query: str,
    datasets: list | None = None,
    user_context: dict | None = None,
    project_context: dict | None = None,
    planner_hints: dict | None = None,
    system_policy: dict | None = None,
) -> "SpatialReasoningResult":
    """
    SRE 顶层入口函数（Rule-only 模式，无需 LLM）。

    将自然语言空间任务转换为结构化空间工作流。
    Phase 2 新增：primitive_resolver 和 template_library 参与推理，
    llm_reasoner 不调用（保持离线可用）。

    Args:
        query           : 用户自然语言查询
        datasets        : 数据集元信息列表（dict 或 DatasetMeta）
        user_context    : 用户偏好上下文
        project_context : 项目级上下文（研究区、默认CRS等）
        planner_hints   : 上游 Planner 的初步猜测
        system_policy   : 系统级安全策略

    Returns:
        SpatialReasoningResult — 结构化推理结果，供 Tool Router 消费
    """
    from geoclaw_claude.reasoning.input_adapter import build_reasoning_input
    from geoclaw_claude.reasoning.context_builder import build_reasoning_context
    from geoclaw_claude.reasoning.task_typer import classify_task
    from geoclaw_claude.reasoning.primitive_resolver import resolve_primitives
    from geoclaw_claude.reasoning.rule_engine import run_rule_engine
    from geoclaw_claude.reasoning.template_library import get_method_candidates
    from geoclaw_claude.reasoning.validator import validate_reasoning
    from geoclaw_claude.reasoning.workflow_synthesizer import synthesize_workflow

    # 1. 标准化输入
    ri = build_reasoning_input(
        query=query,
        datasets=datasets or [],
        user_context=user_context or {},
        project_context=project_context or {},
        planner_hints=planner_hints or {},
        system_policy=system_policy or {},
    )

    # 2. 构建推理上下文
    ctx = build_reasoning_context(ri)

    # 3. 任务类型识别
    task_profile = classify_task(ctx)

    # Phase 2: 地理原语解析（补充 entities/relations 到 task_profile）
    primitives = resolve_primitives(ctx)
    _enrich_task_profile(task_profile, primitives)

    # 4. 规则层（Phase 2：用 template_library 补充 method_candidates）
    rule_output = run_rule_engine(ctx, task_profile)
    template_candidates = get_method_candidates(task_profile, ctx)
    _merge_method_candidates(rule_output, template_candidates)

    # 5. 校验层（Phase 1: Constraint + Feasibility；Phase 2 扩展时 llm_output 非 None）
    validation = validate_reasoning(ctx, task_profile, rule_output, llm_output=None)

    # 6. 组装输出
    return synthesize_workflow(ctx, task_profile, rule_output, validation, llm_output=None)


def reason_with_llm(
    query: str,
    llm_provider: object = None,
    datasets: list | None = None,
    user_context: dict | None = None,
    project_context: dict | None = None,
    planner_hints: dict | None = None,
    system_policy: dict | None = None,
) -> "SpatialReasoningResult":
    """
    SRE 顶层入口函数（Phase 2 完整模式，含 LLM 语义推理）。

    在 reason() 的基础上额外调用 LLM Geo Reasoner，将语义理解结果
    融合到 workflow_plan 和 reasoning_summary 中。

    若 llm_provider 为 None，自动从环境变量/配置文件创建。
    若 llm_provider 调用失败，自动降级为 rule-only 模式。

    Args:
        query           : 用户自然语言查询
        llm_provider    : LLMProvider 实例（None=自动创建）
        datasets        : 数据集元信息列表
        user_context    : 用户偏好上下文
        project_context : 项目级上下文
        planner_hints   : 上游 Planner 的初步猜测
        system_policy   : 系统级安全策略

    Returns:
        SpatialReasoningResult（含 LLM 推理增强）
    """
    # 自动创建 llm_provider
    if llm_provider is None:
        try:
            from geoclaw_claude.nl.llm_provider import LLMProvider
            llm_provider = LLMProvider.from_config()
        except Exception:
            llm_provider = None
    from geoclaw_claude.reasoning.input_adapter import build_reasoning_input
    from geoclaw_claude.reasoning.context_builder import build_reasoning_context
    from geoclaw_claude.reasoning.task_typer import classify_task
    from geoclaw_claude.reasoning.primitive_resolver import resolve_primitives
    from geoclaw_claude.reasoning.rule_engine import run_rule_engine
    from geoclaw_claude.reasoning.template_library import get_method_candidates
    from geoclaw_claude.reasoning.llm_reasoner import run_llm_reasoner
    from geoclaw_claude.reasoning.validator import validate_reasoning
    from geoclaw_claude.reasoning.workflow_synthesizer import synthesize_workflow

    # 1. 标准化输入
    ri = build_reasoning_input(
        query=query,
        datasets=datasets or [],
        user_context=user_context or {},
        project_context=project_context or {},
        planner_hints=planner_hints or {},
        system_policy=system_policy or {},
    )

    # 2. 构建推理上下文
    ctx = build_reasoning_context(ri)

    # 3. 任务类型识别
    task_profile = classify_task(ctx)

    # Phase 2: 地理原语解析
    primitives = resolve_primitives(ctx)
    _enrich_task_profile(task_profile, primitives)

    # 4. 规则层 + 模板库
    rule_output = run_rule_engine(ctx, task_profile)
    template_candidates = get_method_candidates(task_profile, ctx)
    _merge_method_candidates(rule_output, template_candidates)

    # Phase 2: LLM 语义推理（失败则 llm_output=None，降级 rule-only）
    llm_output = run_llm_reasoner(ctx, task_profile, rule_output, llm_provider)

    # 5. 校验层（含 Phase 2 一致性校验）
    validation = validate_reasoning(ctx, task_profile, rule_output, llm_output)

    # 6. 组装输出
    return synthesize_workflow(ctx, task_profile, rule_output, validation, llm_output)


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 2 辅助函数
# ══════════════════════════════════════════════════════════════════════════════

def _enrich_task_profile(task_profile: "TaskProfile", primitives) -> None:
    """将 primitive_resolver 的解析结果补充到 task_profile（去重）"""
    from geoclaw_claude.reasoning.schemas import GeoEntityType, SpatialRelation

    existing_entities = {e.value if hasattr(e, "value") else e for e in task_profile.entities}
    for ent_str in primitives.entities:
        if ent_str not in existing_entities:
            try:
                task_profile.entities.append(GeoEntityType(ent_str))
            except ValueError:
                pass

    existing_relations = {r.value if hasattr(r, "value") else r for r in task_profile.relations}
    for rel_str in primitives.relations:
        if rel_str not in existing_relations:
            try:
                task_profile.relations.append(SpatialRelation(rel_str))
            except ValueError:
                pass

    # 补充 target_metrics 到 task_profile.analysis_goal（追加说明）
    if primitives.target_metrics and not task_profile.analysis_goal:
        task_profile.analysis_goal = ", ".join(primitives.target_metrics[:3])


def _merge_method_candidates(rule_output, template_candidates) -> None:
    """将 template_library 推荐的方法合并到 rule_output.method_candidates（不重复）"""
    existing_ids = {mc.method_id for mc in rule_output.method_candidates}
    for tc in template_candidates:
        if tc.method_id not in existing_ids:
            rule_output.method_candidates.append(tc)
            existing_ids.add(tc.method_id)
