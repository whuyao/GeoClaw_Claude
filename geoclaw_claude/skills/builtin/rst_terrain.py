"""
rst_terrain.py — DEM 地形分析 Skill（坡度 / 坡向 / 山体阴影）
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "rst_terrain",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "DEM地形分析：计算坡度、坡向、山体阴影，输出各地形指标栅格及统计摘要",
    "category":    "raster",
    "inputs": [
        {"name": "dem_path",   "type": "str",  "desc": "DEM 栅格文件路径（.tif）"},
        {"name": "analysis",   "type": "str",  "desc": "分析类型（逗号分隔）: slope,aspect,hillshade", "default": "slope,aspect"},
        {"name": "slope_unit", "type": "str",  "desc": "坡度单位: degrees / percent",                 "default": "degrees"},
        {"name": "sun_az",     "type": "float","desc": "山体阴影太阳方位角（hillshade用）",            "default": 315.0},
        {"name": "sun_alt",    "type": "float","desc": "山体阴影太阳高度角（hillshade用）",            "default": 45.0},
    ],
    "outputs": [
        {"name": "slope",     "type": "RasterLayer", "desc": "坡度栅格"},
        {"name": "aspect",    "type": "RasterLayer", "desc": "坡向栅格"},
        {"name": "hillshade", "type": "RasterLayer", "desc": "山体阴影栅格"},
        {"name": "report",    "type": "str",          "desc": "地形统计摘要"},
    ],
}


def run(ctx):
    import numpy as np
    from geoclaw_claude.analysis.raster_ops import load_raster, slope, aspect, hillshade

    dem_path    = str(ctx.param("dem_path", ""))
    analysis    = [a.strip() for a in str(ctx.param("analysis", "slope,aspect")).split(",")]
    slope_unit  = str(ctx.param("slope_unit", "degrees"))
    sun_az      = float(ctx.param("sun_az", 315.0))
    sun_alt     = float(ctx.param("sun_alt", 45.0))

    if not dem_path:
        raise ValueError("请提供 dem_path 参数（DEM 文件路径）")

    print(f"  加载 DEM: {dem_path}")
    dem = load_raster(dem_path)

    elev = dem.data[0]
    valid = elev[elev != dem.nodata] if dem.nodata is not None else elev.flatten()
    lines = [
        "DEM 地形分析结果",
        f"  栅格尺寸  : {dem.data.shape[1]} × {dem.data.shape[2]}",
        f"  高程范围  : {float(np.nanmin(valid)):.1f} ~ {float(np.nanmax(valid)):.1f} 米",
        f"  平均高程  : {float(np.nanmean(valid)):.1f} 米",
    ]

    results = {}

    if "slope" in analysis:
        slope_rst = slope(dem, units=slope_unit)
        sv = slope_rst.data[0]
        lines.append(f"  坡度范围  : {float(np.nanmin(sv)):.1f} ~ {float(np.nanmax(sv)):.1f} {slope_unit}")
        lines.append(f"  平均坡度  : {float(np.nanmean(sv)):.1f} {slope_unit}")
        results["slope"] = slope_rst
        print("  坡度计算完成")

    if "aspect" in analysis:
        aspect_rst = aspect(dem)
        results["aspect"] = aspect_rst
        print("  坡向计算完成")

    if "hillshade" in analysis:
        hs_rst = hillshade(dem, azimuth=sun_az, altitude=sun_alt)
        results["hillshade"] = hs_rst
        print("  山体阴影计算完成")

    report = "\n".join(lines)
    print(report)

    ai = ctx.ask_ai(
        "请根据以下地形统计数据，评估该区域地形对工程建设/生态保护的影响（50-100字）：",
        context_data=report,
    )
    if ai and not ai.startswith("(AI"):
        report += f"\n\nAI 评价:\n{ai}"

    return ctx.result(
        slope=results.get("slope"),
        aspect=results.get("aspect"),
        hillshade=results.get("hillshade"),
        report=report,
    )
