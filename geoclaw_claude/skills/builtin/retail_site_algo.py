"""
retail_site_algo.py — 内置 Skill（纯 Python 算法版）
======================================================
商场选址综合评估 — 多准则决策分析版（MCDA）

本 Skill 完全基于确定性空间算法，不依赖 LLM：
  1. 计算商圈内人口密度得分（Population Accessibility Score）
  2. 计算竞争回避得分（Competition Avoidance Score）
  3. 计算空间分散得分（Spatial Dispersion Score）
  4. 计算交通可达性得分（Transport Accessibility Score，可选）
  5. 加权汇总 → MCDA 综合评分（0~100 分）
  6. 输出评分图层（GeoJSON）+ 结构化报告

与 AI 驱动版（retail_site_ai）对比：
  ✅ 结果完全可复现，无随机性
  ✅ 离线运行，无需 API Key
  ✅ 支持批量参数敏感性分析
  ⚠ 权重固定，不能动态适应业务逻辑
  ⚠ 无法结合非结构化商业信息

适用场景：
  - 需要客观、可审计的量化评估
  - 作为 AI 版的基准（baseline）对照
  - 大规模自动化选址筛查

依赖:
  pip install geopandas shapely scipy numpy

输入数据:
  --data        候选地块点图层 (.geojson / .shp)  必填
  --pop_layer   人口/热力图层 (.geojson)          可选
  --comp_layer  竞争商场图层 (.geojson)           可选
  --road_layer  路网图层 (.geojson)              可选
  --radius_km   商圈半径（km，默认 1.5）
  --w_pop       人口密度权重（0~1，默认 0.30）
  --w_comp      竞争回避权重（0~1，默认 0.25）
  --w_disp      空间分散权重（0~1，默认 0.25）
  --w_road      交通可达权重（0~1，默认 0.20）
  --top_n       输出推荐数量（默认 3）
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

SKILL_META = {
    "name":        "retail_site_algo",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "商场选址分析（纯Python算法版）：多准则决策分析（MCDA）权重评分",
    "tags":        ["选址", "零售", "MCDA", "算法驱动", "可复现"],
    "inputs": [
        {"name": "input",      "type": "GeoLayer", "desc": "候选选址点图层（必填）"},
        {"name": "pop_layer",  "type": "GeoLayer", "desc": "人口/热力点图层（可选）",
         "required": False},
        {"name": "comp_layer", "type": "GeoLayer", "desc": "竞争商场点图层（可选）",
         "required": False},
        {"name": "road_layer", "type": "GeoLayer", "desc": "路网/交通站点图层（可选）",
         "required": False},
        {"name": "radius_km",  "type": "float",    "desc": "商圈半径(km)", "default": 1.5},
        {"name": "w_pop",      "type": "float",    "desc": "人口密度权重(0~1)", "default": 0.30},
        {"name": "w_comp",     "type": "float",    "desc": "竞争回避权重(0~1)", "default": 0.25},
        {"name": "w_disp",     "type": "float",    "desc": "空间分散权重(0~1)", "default": 0.25},
        {"name": "w_road",     "type": "float",    "desc": "交通可达权重(0~1)", "default": 0.20},
        {"name": "top_n",      "type": "int",      "desc": "推荐选址数量", "default": 3},
    ],
    "outputs": [
        {"name": "scored",  "type": "GeoLayer", "desc": "带 MCDA 评分的候选点图层"},
        {"name": "report",  "type": "str",       "desc": "结构化选址评估报告"},
    ],
    "requires_ai": False,
    "example": (
        "geoclaw-claude skill run retail_site_algo "
        "--data candidates.geojson --radius_km=2.0 --top_n=3"
    ),
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Retail site selection — pure algorithm (MCDA): multi-criteria weighted scoring for candidate locations. Reproducible, no LLM required.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


# ─────────────────────────────────────────────────────────────────────────────
def run(ctx):
    """
    执行 MCDA 商场选址评分。

    算法框架：
      score_i = w_pop  * S_pop(i)
              + w_comp * S_comp(i)
              + w_disp * S_disp(i)
              + w_road * S_road(i)

    各维度得分均归一化到 [0, 100]，采用 min-max 规范化。
    权重之和不要求等于 1，内部自动归一化。
    """
    import math
    import numpy as np
    import geopandas as gpd
    from geoclaw_claude.core.layer import GeoLayer

    # ── 读取参数 ─────────────────────────────────────────────────────────────
    candidates = ctx.get_layer("input")
    radius_km  = float(ctx.param("radius_km", 1.5))
    w_pop      = float(ctx.param("w_pop",  0.30))
    w_comp     = float(ctx.param("w_comp", 0.25))
    w_disp     = float(ctx.param("w_disp", 0.25))
    w_road     = float(ctx.param("w_road", 0.20))
    top_n      = int(ctx.param("top_n", 3))

    # 权重归一化
    w_total = w_pop + w_comp + w_disp + w_road
    if w_total <= 0:
        raise ValueError("权重之和必须大于 0")
    w_pop /= w_total;  w_comp /= w_total
    w_disp /= w_total; w_road /= w_total

    n   = len(candidates)
    utm = "EPSG:32650"
    r_m = radius_km * 1000

    print(f"\n  📍 候选选址点: {n} 个")
    print(f"  📐 商圈半径:   {radius_km} km")
    print(f"  ⚖  权重: 人口={w_pop:.2f}  竞争={w_comp:.2f}  "
          f"分散={w_disp:.2f}  交通={w_road:.2f}")

    cands_utm = candidates.data.to_crs(utm)

    # ── 维度1：人口密度得分 ──────────────────────────────────────────────────
    pop_raw = np.zeros(n)
    try:
        pop_layer = ctx.get_layer("pop_layer")
        pop_utm   = pop_layer.data.to_crs(utm)
        for i, pt in enumerate(cands_utm.geometry):
            pop_raw[i] = float(pop_utm.geometry.distance(pt).lt(r_m).sum())
        print(f"  ✓ 人口层: 已加载 {len(pop_layer)} 个人口点")
    except (KeyError, Exception):
        # 无人口图层 → 均等分布，不惩罚
        pop_raw = np.ones(n) * 50
        print("  ⚠ 未提供人口图层，人口得分设为均等")

    # ── 维度2：竞争回避得分（竞对越少 → 得分越高）────────────────────────
    comp_raw = np.zeros(n)
    try:
        comp_layer = ctx.get_layer("comp_layer")
        comp_utm   = comp_layer.data.to_crs(utm)
        for i, pt in enumerate(cands_utm.geometry):
            comp_raw[i] = float(comp_utm.geometry.distance(pt).lt(r_m).sum())
        # 竞争密度越高 → raw 越大 → 需要反转
        comp_raw = comp_raw.max() - comp_raw  if comp_raw.max() > 0 else np.ones(n)
        print(f"  ✓ 竞争层: 已加载 {len(comp_layer)} 个竞对商场")
    except (KeyError, Exception):
        comp_raw = np.ones(n) * 50
        print("  ⚠ 未提供竞争图层，竞争得分设为均等")

    # ── 维度3：空间分散得分（与其他候选点距离越远 → 越好）───────────────
    disp_raw = np.zeros(n)
    pts_list = list(cands_utm.geometry)
    for i, pt in enumerate(pts_list):
        dists = [pt.distance(pts_list[j]) for j in range(n) if j != i]
        disp_raw[i] = min(dists) / 1000 if dists else 0  # 最近邻距离 km

    # ── 维度4：交通可达得分（附近路网/站点越多 → 越好）──────────────────
    road_raw = np.zeros(n)
    try:
        road_layer = ctx.get_layer("road_layer")
        road_utm   = road_layer.data.to_crs(utm)
        for i, pt in enumerate(cands_utm.geometry):
            road_raw[i] = float(road_utm.geometry.distance(pt).lt(r_m / 2).sum())
        print(f"  ✓ 路网层: 已加载 {len(road_layer)} 段路")
    except (KeyError, Exception):
        road_raw = np.ones(n) * 50
        print("  ⚠ 未提供路网图层，交通得分设为均等")

    # ── Min-Max 归一化至 [0, 100] ────────────────────────────────────────────
    def minmax(arr):
        lo, hi = arr.min(), arr.max()
        if hi == lo:
            return np.full(len(arr), 50.0)
        return (arr - lo) / (hi - lo) * 100

    S_pop  = minmax(pop_raw)
    S_comp = minmax(comp_raw)
    S_disp = minmax(disp_raw)
    S_road = minmax(road_raw)

    # ── 综合评分 ─────────────────────────────────────────────────────────────
    total = w_pop * S_pop + w_comp * S_comp + w_disp * S_disp + w_road * S_road
    ranks = np.argsort(-total)          # 从高到低排名
    rank_arr = np.empty_like(ranks)
    rank_arr[ranks] = np.arange(1, n + 1)

    # ── 写回 GeoDataFrame ────────────────────────────────────────────────────
    gdf = candidates.data.copy()
    gdf["score_total"]  = total.round(1)
    gdf["score_pop"]    = S_pop.round(1)
    gdf["score_comp"]   = S_comp.round(1)
    gdf["score_disp"]   = S_disp.round(1)
    gdf["score_road"]   = S_road.round(1)
    gdf["rank"]         = rank_arr

    scored_layer = GeoLayer(gdf, name="retail_candidates_scored")

    # ── 生成报告 ─────────────────────────────────────────────────────────────
    top_idx = ranks[:top_n]
    report  = _build_report(gdf, top_idx, radius_km,
                             w_pop, w_comp, w_disp, w_road, top_n)
    print(report)

    return ctx.result(scored=scored_layer, report=report)


# ─────────────────────────────────────────────────────────────────────────────
def _build_report(gdf, top_idx, radius_km, w_pop, w_comp, w_disp, w_road, top_n):
    """生成结构化文本报告。"""
    sep  = "=" * 62
    sep2 = "-" * 62
    lines = [
        sep,
        "  商场选址 MCDA 评估报告",
        f"  GeoClaw-claude · retail_site_algo v1.0.0",
        sep,
        f"  候选点数量  : {len(gdf)} 个",
        f"  商圈半径    : {radius_km} km",
        f"  权重配置    : 人口 {w_pop:.0%} | 竞争 {w_comp:.0%} | "
        f"分散 {w_disp:.0%} | 交通 {w_road:.0%}",
        sep2,
        "  评分详细",
        sep2,
        f"  {'名称':<18} {'总分':>6} {'人口':>6} {'竞争':>6} "
        f"{'分散':>6} {'交通':>6} {'排名':>4}",
        "  " + "-" * 58,
    ]

    for _, row in gdf.sort_values("rank").iterrows():
        name = str(row.get("name", f"点{_}"))[:18]
        lines.append(
            f"  {name:<18} {row['score_total']:>6.1f} {row['score_pop']:>6.1f} "
            f"{row['score_comp']:>6.1f} {row['score_disp']:>6.1f} "
            f"{row['score_road']:>6.1f} {int(row['rank']):>4}"
        )

    lines += [sep2, f"  ★ TOP {top_n} 推荐选址", sep2]

    for rank_i, idx in enumerate(top_idx, 1):
        row  = gdf.iloc[idx]
        name = str(row.get("name", f"点{idx}"))
        lines += [
            f"  [{rank_i}] {name}",
            f"      综合得分: {row['score_total']:.1f}/100",
            f"      人口 {row['score_pop']:.1f} | 竞争 {row['score_comp']:.1f} | "
            f"分散 {row['score_disp']:.1f} | 交通 {row['score_road']:.1f}",
            "",
        ]

    lines += [
        sep,
        "  说明：本报告基于 Min-Max 归一化多准则评分，结果完全可复现。",
        "  如需结合商业判断，请使用 retail_site_ai（AI驱动版）。",
        sep,
    ]
    return "\n".join(lines)
