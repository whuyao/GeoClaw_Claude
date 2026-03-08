"""
retail_site_ai.py — 内置 Skill（AI 驱动版）
=============================================
商场选址综合分析 — 大语言模型驱动版

本 Skill 以 LLM 为核心分析引擎：
  1. 通过 Python 进行基础空间运算（缓冲、叠加、KDE）
  2. 将所有空间统计结果打包交给 LLM
  3. 由 LLM 综合多维指标、进行权重推理，输出选址评分与推荐报告

适用场景：
  - 需要结合非结构化商业逻辑（品牌策略、竞争格局）进行研判
  - 数据指标多元、权重主观，适合让 AI 进行综合研判
  - 输出内容需要面向非专业人员，要求可读性强

依赖:
  pip install geopandas shapely scipy

输入数据:
  --data      候选地块点图层 (.geojson / .shp)
  --radius_km 商圈半径（km，默认 1.5）
  --pop_layer 人口热力图层（可选）
  --comp_layer 竞争商场图层（可选）
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "retail_site_ai",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "商场选址分析（AI 大语言模型驱动版）：空间指标计算 + LLM 综合评判",
    "tags":        ["选址", "零售", "AI驱动", "商业地产"],
    "inputs": [
        {"name": "input",      "type": "GeoLayer", "desc": "候选选址点图层（必填）"},
        {"name": "pop_layer",  "type": "GeoLayer", "desc": "人口/热力点图层（可选，用于估算商圈人口）",
         "required": False},
        {"name": "comp_layer", "type": "GeoLayer", "desc": "竞争商场点图层（可选，用于竞争密度分析）",
         "required": False},
        {"name": "radius_km",  "type": "float",    "desc": "商圈半径(km)", "default": 1.5},
        {"name": "top_n",      "type": "int",      "desc": "输出推荐选址数量", "default": 3},
    ],
    "outputs": [
        {"name": "candidates", "type": "GeoLayer", "desc": "带评分的候选点图层"},
        {"name": "report",     "type": "str",       "desc": "AI 撰写的选址分析报告"},
    ],
    "requires_ai": True,
    "example": (
        "geoclaw-claude skill run retail_site_ai "
        "--data candidates.geojson --ai --radius_km=2.0 --top_n=3"
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
def run(ctx):
    """
    执行 AI 驱动商场选址分析。

    分析流程:
      Phase 1 — 空间指标计算（Python 精确计算）
        · 计算各候选点的商圈覆盖面积
        · 统计商圈内竞争商场数量（若提供）
        · 估算商圈人口密度（若提供）
        · 计算候选点间最小间距

      Phase 2 — LLM 综合研判（AI 主导）
        · 将所有指标结构化后交给 LLM
        · LLM 依据商业逻辑动态分配权重
        · 输出评分、排名及选址报告
    """
    import json
    import math
    import geopandas as gpd
    from geoclaw_claude.analysis.spatial_ops import buffer, kde
    from geoclaw_claude.core.layer import GeoLayer

    # ── Phase 1: 读取输入 ────────────────────────────────────────────────────
    candidates = ctx.get_layer("input")
    radius_km  = float(ctx.param("radius_km", 1.5))
    top_n      = int(ctx.param("top_n", 3))

    print(f"\n  📍 候选选址点: {len(candidates)} 个")
    print(f"  📐 商圈半径:   {radius_km} km")

    # 转为 UTM 坐标系（米制计算）
    utm_crs    = "EPSG:32650"   # 中国中部大部地区适用
    cands_utm  = candidates.data.to_crs(utm_crs)
    radius_m   = radius_km * 1000

    site_stats = []

    for idx, row in cands_utm.iterrows():
        pt   = row.geometry
        stat = {"id": idx, "name": row.get("name", f"候选点_{idx}")}

        # 商圈面积（理论圆形）
        stat["trade_area_km2"] = round(math.pi * radius_km ** 2, 3)

        # ── 竞争密度（若有竞争图层）──────────────────────────────────────────
        comp_count = 0
        try:
            comp_layer = ctx.get_layer("comp_layer")
            comp_utm   = comp_layer.data.to_crs(utm_crs)
            comp_count = int(comp_utm.geometry.distance(pt).lt(radius_m).sum())
        except (KeyError, Exception):
            pass
        stat["competitor_count"] = comp_count

        # ── 商圈人口估算（若有人口图层）──────────────────────────────────────
        pop_density = None
        try:
            pop_layer = ctx.get_layer("pop_layer")
            pop_utm   = pop_layer.data.to_crs(utm_crs)
            nearby_pop = int(pop_utm.geometry.distance(pt).lt(radius_m).sum())
            pop_density = round(nearby_pop / stat["trade_area_km2"], 1)
        except (KeyError, Exception):
            pass
        stat["pop_points_in_radius"] = pop_density

        # ── 与其他候选点最小间距 ────────────────────────────────────────────
        others   = cands_utm.geometry.drop(index=idx)
        min_dist = float(others.distance(pt).min()) / 1000 if len(others) > 0 else 999
        stat["min_dist_to_others_km"] = round(min_dist, 2)

        # ── 名称/坐标（WGS84）──────────────────────────────────────────────
        pt_wgs = candidates.data.loc[idx].geometry
        stat["lon"] = round(pt_wgs.x, 6)
        stat["lat"] = round(pt_wgs.y, 6)

        site_stats.append(stat)
        print(f"    [{idx}] {stat['name']} — 竞对:{comp_count} 间距:{min_dist:.2f}km")

    # ── Phase 2: 构造 LLM prompt 并调用 ─────────────────────────────────────
    stats_json = json.dumps(site_stats, ensure_ascii=False, indent=2)

    prompt = f"""你是一名资深商业地产选址顾问，请对以下 {len(candidates)} 个候选商场选址进行综合评估。

## 分析参数
- 商圈半径: {radius_km} km
- 推荐选址数量: {top_n} 个

## 各候选点空间指标数据（JSON格式）
{stats_json}

## 分析要求
请完成以下任务:

1. **评分模型**（满分100分）
   - 人口密度得分（若有数据，权重30%）
   - 竞争回避得分（竞对越少越好，权重25%）
   - 空间分散得分（选址之间需有合理间距，权重20%）
   - 综合位置得分（经纬度判断区位条件，权重25%）
   - 若部分数据缺失，请说明并在剩余维度中重新分配权重

2. **候选点评分表**
   格式: | 候选点名称 | 总分 | 各维度得分 | 排名 |

3. **TOP {top_n} 推荐**
   - 列出推荐的 {top_n} 个选址
   - 说明每个选址的核心优势和潜在风险

4. **综合建议**（150字以内）
   - 整体选址策略建议
   - 数据局限性说明

请用中文回复，结构清晰，语言专业但易于理解。"""

    print("\n  🤖 正在调用 AI 进行综合研判...")
    ai_report = ctx.ask_ai(prompt)

    if ai_report.startswith("(AI"):
        print("  ⚠ AI 未启用，仅输出空间统计结果")
        ai_report = _build_fallback_report(site_stats, radius_km, top_n)

    print(f"\n  ✅ AI 分析完成\n")
    print("  " + "\n  ".join(ai_report.split("\n")[:15]) + "\n  ...")

    # ── 将评分写回图层 ────────────────────────────────────────────────────────
    scored_gdf = candidates.data.copy()
    scored_gdf["competitor_count"] = [s["competitor_count"] for s in site_stats]
    scored_gdf["min_dist_km"]      = [s["min_dist_to_others_km"] for s in site_stats]
    scored_layer = GeoLayer(scored_gdf, name="retail_candidates_scored")

    return ctx.result(candidates=scored_layer, report=ai_report)


def _build_fallback_report(site_stats, radius_km, top_n):
    """AI 未启用时的基础报告。"""
    lines = ["=" * 60, "  商场选址分析报告（基础版，未启用 AI）", "=" * 60, ""]
    lines.append(f"  商圈半径: {radius_km} km | 候选点数: {len(site_stats)}")
    lines.append("")
    lines.append("  候选点空间指标汇总:")
    lines.append(f"  {'名称':<20} {'竞对数':>6} {'最小间距(km)':>12}")
    lines.append("  " + "-" * 42)
    for s in site_stats:
        lines.append(
            f"  {s['name']:<20} {s['competitor_count']:>6} {s['min_dist_to_others_km']:>12}"
        )
    lines.append("")
    lines.append(f"  提示: 使用 --ai 参数启用 AI 综合评分，获得完整分析报告。")
    lines.append("=" * 60)
    return "\n".join(lines)
