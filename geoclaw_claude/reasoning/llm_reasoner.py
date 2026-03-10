# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.llm_reasoner
=======================================
LLM Geo Reasoner（Phase 2 完整实现）。

三个逻辑单元（文档 5.1-5.3）：
  - Task Interpreter       深入理解用户真正的分析目标（含隐含需求）
  - Geo Method Reasoner    在规则层候选方法中做权衡，选择更合适的方法链
  - Geo Explanation Generator  生成方法选择的自然语言解释

设计原则：
  - LLM 不直接生成工具命令，只输出"高层分析设计"（文档 5.5）
  - 规则层输出作为 LLM 的结构化约束输入（文档 5.4）
  - soul.md system_policy 作为最高优先级注入
  - 输出强制为 JSON，parse 失败时降级为 rule-only 模式（已有 phase1 兜底）

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import json
import logging
import textwrap
from typing import List, Optional

from geoclaw_claude.reasoning.schemas import (
    LLMReasoningOutput,
    ReasoningContext,
    RuleEngineOutput,
    TaskProfile,
)
from geoclaw_claude.reasoning.template_library import get_method_limitations, get_template_notes

logger = logging.getLogger(__name__)

# ── 系统 Prompt 模板（文档 5.4）─────────────────────────────────────────────
_SYSTEM_PROMPT = textwrap.dedent("""\
You are the Spatial Reasoning Engine (SRE) of GeoClaw — a professional GIS analysis framework.

Your role is the geospatial reasoning component. You are NOT an execution engine.
Your job is to produce a structured spatial analysis design, NOT runnable code.

You MUST:
1. Infer the actual spatial analysis objective (including hidden/implicit goals)
2. Select appropriate geospatial methods based on rule-layer candidates, data conditions, and user context
3. Obey ALL hard GIS constraints provided by the rule layer (especially CRS constraints)
4. Explicitly note assumptions, limitations, and uncertainty
5. Prefer interpretable methods over complex ones unless complexity is explicitly required
6. Output ONLY a valid JSON object — no markdown, no explanation outside JSON

Output schema (strict JSON):
{
  "inferred_goal": "string — one-sentence description of the actual analysis objective",
  "recommended_analysis_strategy": {
    "primary_method": "string — main method ID from candidates",
    "secondary_methods": ["list of supplementary method IDs"]
  },
  "reasoning": ["list of strings — why this method was chosen"],
  "assumptions": ["list of strings — analytical assumptions"],
  "limitations": ["list of strings — known limitations and caveats"],
  "uncertainty_level": "low|medium|high",
  "explanation": "string — 2-3 sentence natural language explanation for the user"
}
""")


# ══════════════════════════════════════════════════════════════════════════════
#  主接口
# ══════════════════════════════════════════════════════════════════════════════

def run_llm_reasoner(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
    llm_provider: Optional[object] = None,
) -> Optional[LLMReasoningOutput]:
    """
    运行 LLM 地理推理层（Phase 2）。

    若 llm_provider 为 None 或 LLM 调用失败，返回 None（降级到 rule-only 模式）。

    Args:
        ctx          : 推理上下文
        task_profile : 任务分类结果
        rule_output  : 规则层输出（作为 LLM 结构化输入）
        llm_provider : LLMProvider 实例

    Returns:
        LLMReasoningOutput 或 None
    """
    if llm_provider is None:
        logger.debug("LLMReasoner: no llm_provider, running rule-only mode.")
        return None

    prompt = _build_llm_prompt(ctx, task_profile, rule_output)

    try:
        raw_response = _call_llm(llm_provider, prompt)
        if not raw_response:
            return None
        result = _parse_llm_response(raw_response)
        logger.info(f"LLMReasoner: inferred_goal={result.inferred_goal!r}")
        return result
    except Exception as e:
        logger.warning(f"LLMReasoner failed, falling back to rule-only: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Prompt 构建（文档 5.4）
# ══════════════════════════════════════════════════════════════════════════════

def _build_llm_prompt(
    ctx: ReasoningContext,
    task_profile: TaskProfile,
    rule_output: RuleEngineOutput,
) -> str:
    """
    构建 LLM 推理 Prompt（文档 5.4）。

    输入包含：
      - 原始 query
      - 规则层输出（任务候选、方法候选、硬约束、警告）
      - 数据元信息摘要
      - 用户偏好
      - 系统约束
      - 方法局限说明（来自模板库）
    """
    # ── 数据集元信息摘要 ────────────────────────────────────────────────────
    datasets_summary = []
    for ds in ctx.datasets:
        summary = {
            "id": ds.id,
            "type": ds.type,
            "geometry": ds.geometry,
            "crs": ds.crs,
            "time_range": ds.time_range,
            "attributes": ds.attributes[:8],  # 最多展示8个字段
        }
        datasets_summary.append(summary)

    # ── 方法候选详情（附上局限说明）───────────────────────────────────────
    method_details = []
    for mc in rule_output.method_candidates[:6]:
        detail = {
            "method_id": mc.method_id,
            "category": mc.category,
            "description": mc.description,
            "limitations": get_method_limitations(mc.category, mc.method_id),
        }
        method_details.append(detail)

    # ── 模板注意事项 ────────────────────────────────────────────────────────
    template_notes = []
    seen_categories = set()
    for mc in rule_output.method_candidates:
        if mc.category not in seen_categories:
            note = get_template_notes(mc.category)
            if note:
                template_notes.append(note)
            seen_categories.add(mc.category)

    # ── 用户偏好 ────────────────────────────────────────────────────────────
    user_prefs = {
        "language": ctx.user_context.language,
        "expertise": ctx.user_context.expertise,
        "output_preference": ctx.user_context.output_preference,
        "tool_preference": ctx.user_context.tool_preference,
    }

    # ── 系统约束 ────────────────────────────────────────────────────────────
    policy = {
        "readonly_inputs": ctx.system_policy.readonly_inputs,
        "allow_unregistered_tools": ctx.system_policy.allow_unregistered_tools,
    }

    # ── 组装 Prompt ─────────────────────────────────────────────────────────
    user_message = json.dumps({
        "original_query": ctx.query,
        "user_context": user_prefs,
        "system_policy": policy,
        "study_area": ctx.study_area,
        "geo_terms_detected": ctx.geo_terms[:10],
        "datasets": datasets_summary,
        "rule_layer_output": {
            "task_candidates": rule_output.task_candidates,
            "resolved_entities": rule_output.resolved_entities,
            "resolved_relations": rule_output.resolved_relations,
            "target_metrics": rule_output.target_metrics,
            "hard_constraints": rule_output.hard_constraints,
            "warnings": rule_output.warnings,
            "crs_status": rule_output.crs_status.value if hasattr(rule_output.crs_status, "value") else str(rule_output.crs_status),
        },
        "method_candidates": method_details,
        "template_notes": template_notes,
        "instruction": (
            "Based on the above context, produce a structured spatial analysis design. "
            "Select the best primary method from the method_candidates. "
            "Obey all hard_constraints. "
            "Explain your method selection reasoning in 2-4 bullet points. "
            "Output ONLY a valid JSON object matching the specified schema."
        ),
    }, ensure_ascii=False, indent=2)

    return user_message


# ══════════════════════════════════════════════════════════════════════════════
#  LLM 调用
# ══════════════════════════════════════════════════════════════════════════════

def _call_llm(llm_provider: object, prompt: str) -> Optional[str]:
    """
    调用 LLMProvider 获取原始响应文本。

    兼容 geoclaw_claude.nl.llm_provider.LLMProvider 的 call() 接口。
    """
    try:
        # LLMProvider.call(messages, system_prompt) → str
        messages = [{"role": "user", "content": prompt}]
        if hasattr(llm_provider, "call"):
            response = llm_provider.call(
                messages=messages,
                system_prompt=_SYSTEM_PROMPT,
                max_tokens=1200,
            )
            return response
        # 兼容 LLMProvider.chat() 接口（标准接口）
        elif hasattr(llm_provider, "chat"):
            resp = llm_provider.chat(
                messages=messages,
                system=_SYSTEM_PROMPT,
                max_tokens=1200,
            )
            if resp is None:
                return None
            return resp.content if hasattr(resp, "content") else str(resp)
        # 兜底：尝试直接调用
        elif callable(llm_provider):
            return llm_provider(prompt)
        else:
            logger.warning("LLMProvider has no compatible interface.")
            return None
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  响应解析
# ══════════════════════════════════════════════════════════════════════════════

def _parse_llm_response(raw_response: str) -> LLMReasoningOutput:
    """
    解析 LLM 响应为 LLMReasoningOutput（文档 5.5）。

    尝试顺序：
      1. 直接 JSON 解析
      2. 提取 ```json...``` 代码块
      3. 找第一个 { ... } 块
      4. 返回部分解析结果（不抛出）
    """
    text = raw_response.strip()

    # 尝试 1：直接解析
    data = _try_json_parse(text)

    # 尝试 2：提取代码块
    if data is None:
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            data = _try_json_parse(m.group(1).strip())

    # 尝试 3：找 {...} 块
    if data is None:
        import re
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            data = _try_json_parse(m.group(0))

    if data is None:
        logger.warning("LLMReasoner: could not parse JSON response, using partial result.")
        return LLMReasoningOutput(
            inferred_goal="(LLM response parse failed)",
            raw_response=raw_response,
        )

    # 提取字段
    strategy = data.get("recommended_analysis_strategy", {})
    primary = strategy.get("primary_method", data.get("primary_method", ""))
    secondary = strategy.get("secondary_methods", data.get("secondary_methods", []))

    return LLMReasoningOutput(
        inferred_goal=data.get("inferred_goal", ""),
        primary_method=primary,
        secondary_methods=secondary if isinstance(secondary, list) else [],
        method_rationale=_ensure_list(data.get("reasoning", [])),
        assumptions=_ensure_list(data.get("assumptions", [])),
        limitations=_ensure_list(data.get("limitations", [])),
        explanation=data.get("explanation", ""),
        uncertainty_level=data.get("uncertainty_level", "unknown"),
        raw_response=raw_response,
    )


def _try_json_parse(text: str) -> Optional[dict]:
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _ensure_list(val) -> List[str]:
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str) and val:
        return [val]
    return []
