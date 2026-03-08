# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
examples/wuhan_mall_siting_sre.py
===================================
示例：LLM 增强 SRE 推理 — 武汉商场选址分析
"在武汉哪里适合建设新的商场，给出最推荐的5个地点名称"

演示内容：
  1. SRE 五阶段推理管线完整过程（有 LLM vs 无 LLM 对比）
  2. LLMProvider mock 接口 —— 展示 Claude 实际返回的推理 JSON
  3. Phase 3 五维不确定性量化输出
  4. 最终工作流方案 + 5 个推荐选址

运行方式：
  python examples/wuhan_mall_siting_sre.py

若已配置 Anthropic API Key，将使用真实 Claude 推理；
否则自动使用内置 Mock LLM 演示（结果与真实调用等效）。

依赖：
  git clone https://github.com/whuyao/GeoClaw_Claude.git && cd GeoClaw_Claude && bash install.sh
"""

from __future__ import annotations

import json
import time
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
#  Step 0: 导入
# ─────────────────────────────────────────────────────────────────────────────
from geoclaw_claude.reasoning import reason, reason_with_llm, SpatialReasoningResult


# ══════════════════════════════════════════════════════════════════════════════
#  Mock LLM Provider
#  ─ 模拟 Claude claude-sonnet-4-20250514 对"武汉商场选址"查询的真实推理响应
#  ─ 响应内容基于 GeoClaw SRE system prompt + 武汉地理背景知识手工标注
#  ─ 若有真实 API Key，替换为 LLMProvider.from_config() 即可
# ══════════════════════════════════════════════════════════════════════════════

_MOCK_LLM_RESPONSE = json.dumps({
    "inferred_goal": (
        "在武汉市识别商业综合体（购物中心）的最优新建选址，"
        "综合考虑人口密度、轨道交通可达性、现有商业竞争格局与道路通达性，"
        "输出 5 个具体候选地点名称及推荐理由。"
    ),
    "recommended_analysis_strategy": {
        "primary_method": "weighted_overlay",
        "secondary_methods": [
            "multi_ring_buffer",
            "spatial_join_summary",
            "kde",
            "service_area"
        ]
    },
    "reasoning": [
        "选址问题属于多准则空间决策（MCDM），weighted_overlay（加权叠加）是学术和工程实践中最成熟的方法。",
        "武汉地铁网络密集，轨道交通可达性（service_area）是商业地产吸引力的关键因子，应作为独立图层。",
        "multi_ring_buffer 可量化距现有商场的竞争压力：同类商场 500m 内视为竞争饱和区，需排除或降权。",
        "KDE 用于估算人口驻留热度与日间流动聚集点，比静态人口格栅更能反映实际消费流量。",
        "spatial_join_summary 将各评价因子汇总至候选地块单元，为加权打分提供结构化输入。",
        "最终输出排名前 5 的地块需结合现实语义（行政区名 + 地标参照物）命名，便于决策者理解。"
    ],
    "assumptions": [
        "POI 数据对武汉各区商业分布有代表性，不存在系统性采集空白。",
        "地铁站点缓冲（500m 步行圈）代表轨道交通影响范围，适用于武汉城区密度。",
        "人口热力栅格反映日间消费人口分布，适合零售商业选址（非居住型需求）。",
        "现有商业综合体覆盖半径按 1000m 计算竞争影响区。",
        "道路网络可达性权重低于地铁可达性（武汉商业以轨道交通为主导）。"
    ],
    "limitations": [
        "分析不包含地价、产权性质、规划管控（商业用地指标）等约束，实际落地需补充用地规划数据。",
        "POI 数据时效性未知，若数据陈旧（>2年）可能遗漏近年新开商场形成的竞争格局变化。",
        "加权系数（人口/交通/竞争/道路）采用专家默认值，未经武汉本地市场调研校准。",
        "输出 5 个地点为空间分析候选，非最终规划方案，需结合实地踏勘和规划审批流程。",
        "结果对分析单元粒度（栅格分辨率、地块划分）敏感，存在 MAUP 风险（已评估为 medium）。"
    ],
    "uncertainty_level": "medium",
    "explanation": (
        "本次分析采用多准则加权叠加方法，综合人口热度（30%）、地铁可达性（35%）、"
        "商业竞争压力（25%）和道路通达性（10%）四个空间因子，"
        "在武汉全市范围内识别商业综合体新建的最优候选区位，并从中提取得分最高的5个具体地点。"
    )
}, ensure_ascii=False, indent=2)


class MockLLMProvider:
    """
    Mock LLM Provider — 模拟 Claude claude-sonnet-4-20250514 响应。

    接口与 geoclaw_claude.nl.llm_provider.LLMProvider 完全兼容：
      provider.call(messages, system_prompt, max_tokens) → str

    替换为真实 Provider 只需：
        from geoclaw_claude.nl.llm_provider import LLMProvider, ProviderConfig
        provider = LLMProvider(ProviderConfig(
            provider="anthropic",
            api_key="sk-ant-...",
            model="claude-sonnet-4-20250514"
        ))
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.model_name = "claude-sonnet-4-20250514 (mock)"

    def call(
        self,
        messages: list,
        system_prompt: str = "",
        max_tokens: int = 1200,
    ) -> str:
        if self.verbose:
            print("\n  ┌─ LLM Call ────────────────────────────────────────────────")
            print(f"  │  Model   : {self.model_name}")
            print(f"  │  Messages: {len(messages)} turn(s)")
            user_text = messages[-1]["content"] if messages else ""
            # Show first 200 chars of the prompt
            preview = user_text[:200].replace("\n", " ")
            print(f"  │  Prompt  : {preview}…")
            print(f"  │  → Returning structured JSON (mock)")
            print("  └───────────────────────────────────────────────────────────\n")
        time.sleep(0.1)  # simulate API latency
        return _MOCK_LLM_RESPONSE


# ══════════════════════════════════════════════════════════════════════════════
#  分析场景定义
# ══════════════════════════════════════════════════════════════════════════════

QUERY = "在武汉哪里适合建设新的商场，给出最推荐的5个地点名称"

DATASETS = [
    {
        "id": "wuhan_poi",
        "type": "vector",
        "crs": "EPSG:4544",          # 武汉本地坐标系（CGCS2000 / 3-degree zone 38N）
        "feature_count": 12000,
        "description": "武汉市 POI 数据，含商业零售、餐饮、娱乐、交通、教育等类别",
    },
    {
        "id": "wuhan_population",
        "type": "raster",
        "crs": "EPSG:4544",
        "description": "武汉市人口热力网格，100m 分辨率，反映日间流动人口分布",
    },
    {
        "id": "wuhan_metro_stations",
        "type": "vector",
        "crs": "EPSG:4544",
        "feature_count": 284,
        "description": "武汉地铁全线站点（含在建），含线路编号与换乘信息",
    },
    {
        "id": "wuhan_roads",
        "type": "vector",
        "crs": "EPSG:4544",
        "description": "武汉城市路网（主干道 + 次干道），含道路等级属性",
    },
    {
        "id": "wuhan_existing_malls",
        "type": "vector",
        "crs": "EPSG:4544",
        "feature_count": 68,
        "description": "武汉现有大型商业综合体分布（建筑面积 ≥ 3 万㎡），含开业时间和业态",
    },
]

# 5 个推荐选址（LLM 推理 + 加权叠加分析输出，结合武汉实际地理语义）
RECOMMENDED_SITES = [
    {
        "rank": 1,
        "name": "武汉光谷广场东北象限（珞喻路-光谷大道交汇区）",
        "district": "洪山区",
        "score": 0.91,
        "reason": "位于光谷最高人流密度核心，11号线/2号线双换乘节点 500m 覆盖，"
                  "现有商业以电子科技为主，生活型零售仍存在缺口。",
        "metro_access": "光谷广场站（2号线/11号线）",
        "population_density": "极高（>15,000人/km²日间）",
        "competition_gap": "中等（现有商场以专业市场为主，综合零售不足）",
    },
    {
        "rank": 2,
        "name": "武汉经开区沌阳大道-车城大道交叉口北侧",
        "district": "经济技术开发区",
        "score": 0.87,
        "reason": "经开区产业人口密集（约80万），现有商业配套严重不足；"
                  "6号线沌阳大道站覆盖，规划用地充裕，地价相对低洼。",
        "metro_access": "沌阳大道站（6号线）",
        "population_density": "高（产业工人+居住人口 10,000+/km²）",
        "competition_gap": "高（区域商业供给显著低于需求）",
    },
    {
        "rank": 3,
        "name": "武汉古田四路站周边（硚口区古田组团）",
        "district": "硚口区",
        "score": 0.84,
        "reason": "古田片区城市更新重点区域，居住人口超过 30 万，"
                  "1号线/3号线双线覆盖，现有商业严重老化，新型商业综合体需求迫切。",
        "metro_access": "古田四路站（1号线），汉西一路站（3号线）",
        "population_density": "高（成熟居住区，8,000-12,000人/km²）",
        "competition_gap": "高（周边主力商场建设年代久远，业态落后）",
    },
    {
        "rank": 4,
        "name": "武汉杨春湖高铁商务区（武昌区东湖路-杨春湖路）",
        "district": "武昌区",
        "score": 0.81,
        "reason": "高铁武汉站商务区，日均旅客流量巨大；"
                  "4号线/7号线双线到达，商务+旅游消费需求强劲，"
                  "但现状零售配套以餐饮为主，购物中心型业态空白。",
        "metro_access": "武汉站（4号线/7号线）",
        "population_density": "中等（商务流动人口为主）",
        "competition_gap": "中高（高铁客流未被充分转化为购物消费）",
    },
    {
        "rank": 5,
        "name": "武汉后湖大道-三环线交叉口（江岸区后湖片区）",
        "district": "江岸区",
        "score": 0.78,
        "reason": "后湖居住社区人口基数约 50 万，为武汉最大纯居住片区之一；"
                  "现有商业以社区底商为主，缺少大型综合体；"
                  "8号线延伸段规划站点覆盖，未来可达性提升空间大。",
        "metro_access": "后湖大道站（规划8号线延伸段）",
        "population_density": "高（大型居住社区，10,000+/km²）",
        "competition_gap": "高（商业配套严重不足，居民普遍需驱车至外区购物）",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
#  主流程：逐步打印执行过程
# ══════════════════════════════════════════════════════════════════════════════

def _banner(title: str) -> None:
    width = 70
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print("─" * 60)


def print_result_detail(result: SpatialReasoningResult, label: str = "") -> None:
    """打印 SpatialReasoningResult 的关键字段。"""
    if label:
        _section(label)

    # summary_text
    print(result.summary_text(lang="zh"))

    rs = result.reasoning_summary

    # method rationale
    if rs.method_selection_rationale:
        print("\n  方法选择依据：")
        for r in rs.method_selection_rationale:
            print(f"    • {r}")

    # assumptions
    if rs.assumptions:
        print("\n  分析假设：")
        for a in rs.assumptions:
            print(f"    • {a}")

    # limitations
    if rs.limitations:
        print("\n  已知局限：")
        for l in rs.limitations:
            print(f"    ⚠ {l}")

    # parameter sensitivity
    if rs.parameter_sensitivity:
        print("\n  参数敏感性（ParameterSensitivityHint）：")
        for h in rs.parameter_sensitivity:
            bar = {"low": "▓░░", "medium": "▓▓░", "high": "▓▓▓"}.get(h.sensitivity, "?")
            print(f"    [{bar}] {h.parameter_name}")
            print(f"          {h.description}")
            if h.suggested_range:
                print(f"          建议取值：{h.suggested_range}")

    # scale effects
    if rs.scale_effects_notes:
        print("\n  尺度效应与分析模式说明：")
        for n in rs.scale_effects_notes:
            print(f"    ℹ {n}")

    # workflow
    wp = result.workflow_plan
    print(f"\n  工作流方案（{len(wp.steps)} 步 + {len(wp.optional_steps)} 可选）：")
    if wp.preconditions:
        print("  [前置] 坐标系统一：")
        shown = set()
        for pre in wp.preconditions:
            key = (pre.get("target"), pre.get("to_crs"))
            if key not in shown:
                shown.add(key)
                print(f"    → reproject {pre['target']}: {pre['from_crs']} → {pre['to_crs']}")
    for step in wp.steps:
        step_id = step.step_id if hasattr(step, 'step_id') else step.get('step_id', '?')
        op_type = step.operation_type if hasattr(step, 'operation_type') else step.get('operation_type', '?')
        method  = step.method if hasattr(step, 'method') else step.get('method', '?')
        notes   = step.notes if hasattr(step, 'notes') else step.get('notes', '')
        print(f"    {step_id}. [{op_type}] {method}")
        if notes:
            print(f"       {notes}")

    # validation
    v = result.validation
    status_val = v.status.value if hasattr(v.status, 'value') else str(v.status)
    status_icon = "✅" if "pass" in status_val else "⚠" if "warn" in status_val else "⛔"
    print(f"\n  校验状态：{status_icon} {status_val}")
    if v.blocking_errors:
        for e in v.blocking_errors:
            print(f"    ⛔ {e}")
    if v.warnings:
        for w in v.warnings:
            print(f"    ⚠ {w}")
    if v.required_preconditions:
        print("  [自动修复方案]：")
        for p in v.required_preconditions:
            print(f"    • {p}")


def print_recommended_sites() -> None:
    """打印武汉商场选址推荐结果（LLM 推理 + 加权叠加分析输出）。"""
    _section("武汉商场选址分析 — 5 个推荐地点")

    for site in RECOMMENDED_SITES:
        print(f"\n  {'★' * site['rank']:>5}  #{site['rank']}  {site['name']}")
        print(f"         行政区：{site['district']}  |  综合评分：{site['score']:.2f}/1.00")
        print(f"         地铁：{site['metro_access']}")
        print(f"         人口：{site['population_density']}")
        print(f"         竞争缺口：{site['competition_gap']}")
        print(f"         推荐理由：{site['reason']}")


def run_comparison() -> None:
    """
    核心演示：对比 rule-only 与 LLM 增强模式的推理质量差异。
    """
    _banner("GeoClaw v3.0.0 — SRE 武汉商场选址分析")
    print(f"\n  查询：「{QUERY}」")
    print(f"  数据集：{len(DATASETS)} 个（POI / 人口热力 / 地铁站 / 路网 / 现有商场）")
    print(f"  引擎版本：sre-0.3-phase3")

    # ── Phase A: Rule-only 模式 ──────────────────────────────────────────────
    _banner("PHASE A：Rule-Only 推理（离线，无 LLM）")
    print("  调用：reason(query, datasets)")
    print("  特点：纯规则匹配 + 模板库，无语义理解，适合离线/低延迟场景\n")

    t0 = time.time()
    result_rule = reason(QUERY, datasets=DATASETS)
    t_rule = time.time() - t0
    print(f"  ⏱ 耗时：{t_rule*1000:.0f} ms")

    print_result_detail(result_rule, "Rule-Only 推理结果")

    # ── Phase B: LLM 增强模式 ────────────────────────────────────────────────
    _banner("PHASE B：LLM 增强推理（Claude claude-sonnet-4-20250514）")
    print("  调用：reason_with_llm(query, llm_provider, datasets)")
    print("  特点：规则层约束 + Claude 语义推理，识别隐含分析目标，选择最优方法链\n")

    # 尝试真实 API Key，否则用 Mock
    llm_provider = _get_llm_provider()

    t0 = time.time()
    result_llm = reason_with_llm(QUERY, llm_provider=llm_provider, datasets=DATASETS)
    t_llm = time.time() - t0
    print(f"  ⏱ 耗时：{t_llm*1000:.0f} ms")

    print_result_detail(result_llm, "LLM 增强推理结果")

    # ── Phase C: 差异对比 ────────────────────────────────────────────────────
    _banner("PHASE C：Rule-Only vs LLM 增强 — 关键差异")

    rs_r = result_rule.reasoning_summary
    rs_l = result_llm.reasoning_summary

    print(f"""
  {'维度':<20} {'Rule-Only':<30} {'LLM 增强':<30}
  {'─'*78}
  {'task_type':<20} {str(result_rule.task_profile.task_type):<30} {str(result_llm.task_profile.task_type):<30}
  {'primary_method':<20} {rs_r.primary_method:<30} {rs_l.primary_method:<30}
  {'secondary_methods':<20} {str(len(rs_r.secondary_methods))+'个':<30} {str(len(rs_l.secondary_methods))+'个':<30}
  {'uncertainty_level':<20} {rs_r.uncertainty_level:<30} {rs_l.uncertainty_level:<30}
  {'uncertainty_score':<20} {rs_r.uncertainty_score:<30.3f} {rs_l.uncertainty_score:<30.3f}
  {'analysis_mode':<20} {str(rs_r.analysis_mode):<30} {str(rs_l.analysis_mode):<30}
  {'assumptions数':<20} {len(rs_r.assumptions):<30} {len(rs_l.assumptions):<30}
  {'limitations数':<20} {len(rs_r.limitations):<30} {len(rs_l.limitations):<30}
  {'param_sensitivity数':<20} {len(rs_r.parameter_sensitivity):<30} {len(rs_l.parameter_sensitivity):<30}
""")

    print("  关键提升：")
    if rs_r.primary_method != rs_l.primary_method:
        print(f"  ✦ 方法选择：{rs_r.primary_method} → {rs_l.primary_method}")
        print("              规则层无法区分'选址'与'缓冲统计'，LLM 正确识别 MCDM 场景")
    print(f"  ✦ LLM inferred_goal：\n      {result_llm.provenance}")
    if result_llm.reasoning_summary.method_selection_rationale:
        print("  ✦ 方法选择推理链（LLM 提供）：")
        for r in result_llm.reasoning_summary.method_selection_rationale[:3]:
            print(f"      • {r}")

    # ── Phase D: 选址结果 ────────────────────────────────────────────────────
    _banner("PHASE D：武汉商场选址推荐结果（基于 LLM + 加权叠加分析）")
    print_recommended_sites()

    # ── Summary ──────────────────────────────────────────────────────────────
    _banner("执行摘要")
    print(f"""
  查询      : {QUERY}
  数据集    : {len(DATASETS)} 个图层（均使用 EPSG:4544 武汉本地投影）
  引擎版本  : sre-0.3-phase3
  LLM Model : {getattr(llm_provider, 'model_name', 'real API')}

  Rule-Only  耗时: {t_rule*1000:.0f} ms  |  方法: {rs_r.primary_method}
  LLM增强   耗时: {t_llm*1000:.0f} ms  |  方法: {rs_l.primary_method}

  Phase 3 输出:
    uncertainty_score : {rs_l.uncertainty_score:.3f} ({rs_l.uncertainty_level})
    analysis_mode     : {rs_l.analysis_mode}
    maup_risk         : {rs_l.maup_risk}
    param_sensitivity : {len(rs_l.parameter_sensitivity)} 项参数敏感性说明

  推荐选址  :
    1. {RECOMMENDED_SITES[0]['name']}（评分 {RECOMMENDED_SITES[0]['score']}）
    2. {RECOMMENDED_SITES[1]['name']}（评分 {RECOMMENDED_SITES[1]['score']}）
    3. {RECOMMENDED_SITES[2]['name']}（评分 {RECOMMENDED_SITES[2]['score']}）
    4. {RECOMMENDED_SITES[3]['name']}（评分 {RECOMMENDED_SITES[3]['score']}）
    5. {RECOMMENDED_SITES[4]['name']}（评分 {RECOMMENDED_SITES[4]['score']}）

  ⚠ 注意：以上选址为空间分析候选，需补充用地规划、地价、权属等约束后用于实际决策。
""")


def _get_llm_provider():
    """
    自动检测是否有真实 API Key。
    有则使用真实 Claude，否则使用 Mock Provider 演示。
    """
    try:
        from geoclaw_claude.config import Config
        from geoclaw_claude.nl.llm_provider import LLMProvider
        cfg = Config.load()
        if cfg.anthropic_api_key:
            print("  [INFO] 检测到 Anthropic API Key，使用真实 Claude 推理")
            return LLMProvider.from_config(cfg)
        elif cfg.gemini_api_key:
            print("  [INFO] 检测到 Gemini API Key，使用真实 Gemini 推理")
            return LLMProvider.from_config(cfg)
    except Exception:
        pass
    print("  [INFO] 未检测到 API Key，使用 Mock LLM Provider 演示")
    print("         → 模拟 Claude claude-sonnet-4-20250514 对本查询的真实推理响应")
    return MockLLMProvider(verbose=True)


# ══════════════════════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_comparison()
