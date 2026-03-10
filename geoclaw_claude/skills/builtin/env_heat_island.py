"""
env_heat_island.py — 城市热岛效应分析 Skill
=============================================
Urban Heat Island (UHI) Analysis

基于地表覆盖类型数据，通过绿化率、不透水面比例、水体距离等
空间指标，估算城市热岛效应强度分布，识别高温风险区域。

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations
import numpy as np

SKILL_META = {
    "name": "env_heat_island",
    "version": "1.0.0",
    "author": "UrbanComp Lab",
    "description": (
        "城市热岛效应分析：基于绿化率、不透水面比例、水体距离等空间指标，"
        "估算热岛强度分布，识别高温风险区域，输出热岛强度图层与 AI 解读"
    ),
    "params": {
        "buildings_layer": {"type": "str", "default": "buildings", "description": "建筑物/不透水面图层名"},
        "green_layer":     {"type": "str", "default": "green",     "description": "绿化/公园图层名（可选）"},
        "water_layer":     {"type": "str", "default": "water",     "description": "水体图层名（可选）"},
        "grid_size":       {"type": "float", "default": 300.0,     "description": "分析网格尺寸（米）"},
        "study_area":      {"type": "str", "default": "",          "description": "研究区范围图层名（可选）"},
    },
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Urban heat island analysis: estimate UHI intensity from impervious surface, vegetation, and water coverage. Outputs a grid of UHI index values.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


def run(ctx):
    """城市热岛效应分析：不透水面率 / 绿化率 / 水体率 → UHI 指数网格"""
    import geopandas as gpd
    from shapely.geometry import box

    buildings_name = ctx.param("buildings_layer", default="buildings")
    green_name     = ctx.param("green_layer",     default="green")
    water_name     = ctx.param("water_layer",     default="water")
    grid_size      = float(ctx.param("grid_size", default=300.0))
    study_name     = ctx.param("study_area",      default="")

    buildings = ctx.get_layer(buildings_name)
    if buildings is None:
        return ctx.result(output=None, commentary="错误：找不到建筑物图层，请先加载建筑数据。")

    bld_gdf = buildings.gdf.copy()
    try:
        utm_crs = bld_gdf.estimate_utm_crs()
    except Exception:
        utm_crs = "EPSG:32650"
    bld_proj = bld_gdf.to_crs(utm_crs)

    green_gdf = water_gdf = None
    gl = ctx.get_layer(green_name)
    if gl is not None:
        green_gdf = gl.gdf.to_crs(utm_crs)
    wl = ctx.get_layer(water_name)
    if wl is not None:
        water_gdf = wl.gdf.to_crs(utm_crs)

    bounds = bld_proj.total_bounds
    if study_name:
        sa = ctx.get_layer(study_name)
        if sa is not None:
            bounds = sa.gdf.to_crs(utm_crs).total_bounds

    minx, miny, maxx, maxy = bounds
    xs = np.arange(minx, maxx, grid_size)
    ys = np.arange(miny, maxy, grid_size)
    grid_cells = [box(x, y, x + grid_size, y + grid_size) for x in xs for y in ys]
    grid_gdf = gpd.GeoDataFrame({"grid_id": range(len(grid_cells))},
                                 geometry=grid_cells, crs=utm_crs)
    cell_area = grid_size * grid_size

    def _ratio(grid, features):
        r = np.zeros(len(grid))
        if features is None:
            return r
        try:
            joined = gpd.overlay(grid, features[["geometry"]], how="intersection", keep_geom_type=False)
            joined["area"] = joined.geometry.area
            sums = joined.groupby("grid_id")["area"].sum()
            for i, gid in enumerate(grid["grid_id"]):
                r[i] = min(sums.get(gid, 0.0) / cell_area, 1.0)
        except Exception:
            pass
        return r

    imperv = _ratio(grid_gdf, bld_proj)
    green  = _ratio(grid_gdf, green_gdf)
    water  = _ratio(grid_gdf, water_gdf)

    uhi_raw = np.clip(0.5 * imperv - 0.3 * green - 0.2 * water, 0, None)
    mx = uhi_raw.max()
    uhi_idx = uhi_raw / mx if mx > 0 else uhi_raw

    def lvl(v):
        if v < 0.25: return "低"
        if v < 0.50: return "中"
        if v < 0.75: return "高"
        return "极高"

    grid_gdf["imperv_ratio"] = imperv.round(3)
    grid_gdf["green_ratio"]  = green.round(3)
    grid_gdf["water_ratio"]  = water.round(3)
    grid_gdf["uhi_index"]    = uhi_idx.round(3)
    grid_gdf["uhi_level"]    = [lvl(v) for v in uhi_idx]

    result_gdf = grid_gdf.to_crs("EPSG:4326")
    lc = grid_gdf["uhi_level"].value_counts().to_dict()
    total = len(grid_gdf)
    high_pct = round((lc.get("高", 0) + lc.get("极高", 0)) / max(total, 1) * 100, 1)

    summary = (
        f"网格数：{total}（{grid_size:.0f}m²）| 不透水面均值：{imperv.mean():.1%} | "
        f"绿化均值：{green.mean():.1%} | 水体均值：{water.mean():.1%}\n"
        f"热岛分级：低={lc.get('低',0)} 中={lc.get('中',0)} 高={lc.get('高',0)} 极高={lc.get('极高',0)} | "
        f"高风险占比：{high_pct}%"
    )
    commentary = ctx.ask_ai(
        f"城市热岛分析结果（{grid_size:.0f}m网格）：\n{summary}\n\n"
        "请用2-3句话解读热岛分布格局，并给出1条改善建议。"
    ) or summary

    from geoclaw_claude.core.layer import GeoLayer
    return ctx.result(
        output=GeoLayer(gdf=result_gdf, name="uhi_grid", crs="EPSG:4326",
                        metadata={"source": "env_heat_island", "grid_size_m": grid_size,
                                  "high_risk_pct": high_pct}),
        commentary=commentary,
    )
