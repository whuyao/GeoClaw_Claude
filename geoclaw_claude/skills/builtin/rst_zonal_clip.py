"""
rst_zonal_clip.py — 栅格分区统计 & 裁剪 & 重采样 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "rst_zonal_clip",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "栅格处理三合一：栅格分区统计（zonal_stats）、按矢量掩膜裁剪（clip）、空间重采样（resample）",
    "category":    "raster",
    "inputs": [
        {"name": "raster_path",  "type": "str",   "desc": "输入栅格路径（.tif）"},
        {"name": "mode",         "type": "str",   "desc": "操作: zonal_stats / clip / resample", "default": "clip"},
        {"name": "vector_path",  "type": "str",   "desc": "矢量文件路径（zonal_stats/clip 需要）", "default": ""},
        {"name": "stats",        "type": "str",   "desc": "统计项（zonal_stats）: mean,min,max,sum,count", "default": "mean,min,max"},
        {"name": "target_res",   "type": "float", "desc": "目标分辨率（米，resample 需要）", "default": 30.0},
        {"name": "output_path",  "type": "str",   "desc": "输出路径（可选）", "default": ""},
    ],
    "outputs": [
        {"name": "result", "type": "GeoLayer",    "desc": "分区统计结果（zonal_stats）"},
        {"name": "raster", "type": "RasterLayer", "desc": "处理后栅格（clip/resample）"},
        {"name": "report", "type": "str",          "desc": "统计或处理摘要"},
    ],
}


def run(ctx):
    import numpy as np
    from geoclaw_claude.analysis.raster_ops import (
        load_raster, zonal_stats, clip_raster, resample, save_raster
    )

    raster_path = str(ctx.param("raster_path", ""))
    mode        = str(ctx.param("mode", "clip")).lower()
    vector_path = str(ctx.param("vector_path", "")).strip()
    stats_str   = str(ctx.param("stats", "mean,min,max"))
    target_res  = float(ctx.param("target_res", 30.0))
    output_path = str(ctx.param("output_path", "")).strip()

    if not raster_path:
        raise ValueError("请提供 raster_path 参数")

    print(f"  加载栅格: {raster_path}")
    raster = load_raster(raster_path)

    result_layer = None
    result_raster = None

    if mode == "zonal_stats":
        if not vector_path:
            raise ValueError("zonal_stats 需要 vector_path 参数")
        import geopandas as gpd
        from geoclaw_claude.core.layer import GeoLayer
        zones_gdf = gpd.read_file(vector_path)
        zones = GeoLayer(data=zones_gdf, name="zones")
        stats_list = [s.strip() for s in stats_str.split(",")]
        result_layer = zonal_stats(raster, zones, stats=stats_list)
        report = (
            f"栅格分区统计结果\n"
            f"  统计项  : {stats_list}\n"
            f"  区域数  : {len(result_layer)}\n"
            f"  新增字段: {[c for c in result_layer.data.columns if any(s in c for s in stats_list)]}"
        )

    elif mode == "clip":
        if not vector_path:
            raise ValueError("clip 需要 vector_path 参数")
        import geopandas as gpd
        from geoclaw_claude.core.layer import GeoLayer
        mask_gdf = gpd.read_file(vector_path)
        mask = GeoLayer(data=mask_gdf, name="mask")
        result_raster = clip_raster(raster, mask)
        if output_path:
            save_raster(result_raster, output_path)
        d = result_raster.data[0]
        report = (
            f"栅格裁剪结果\n"
            f"  输出形状 : {result_raster.data.shape}\n"
            f"  值域     : {float(np.nanmin(d)):.4f} ~ {float(np.nanmax(d)):.4f}"
        )

    elif mode == "resample":
        result_raster = resample(raster, target_res)
        if output_path:
            save_raster(result_raster, output_path)
        report = (
            f"栅格重采样结果\n"
            f"  目标分辨率: {target_res} 米\n"
            f"  输出形状  : {result_raster.data.shape}"
        )
    else:
        raise ValueError(f"不支持的模式: {mode}，请选择 zonal_stats / clip / resample")

    print(report)
    if output_path and result_raster:
        report += f"\n  已保存至: {output_path}"

    return ctx.result(result=result_layer, raster=result_raster, report=report)
