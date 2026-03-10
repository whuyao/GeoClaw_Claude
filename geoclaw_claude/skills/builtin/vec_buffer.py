"""
vec_buffer.py — 矢量缓冲区分析 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "vec_buffer",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "矢量缓冲区分析：对点/线/面图层生成指定半径缓冲区，支持合并与面积统计",
    "category":    "vector",
    "inputs": [
        {"name": "input",      "type": "GeoLayer", "desc": "输入矢量图层（点/线/面）"},
        {"name": "distance",   "type": "float",    "desc": "缓冲距离（米）", "default": 500.0},
        {"name": "dissolve",   "type": "bool",     "desc": "是否合并重叠缓冲区", "default": False},
    ],
    "outputs": [
        {"name": "buffer",  "type": "GeoLayer", "desc": "缓冲区结果图层"},
        {"name": "report",  "type": "str",       "desc": "面积统计报告"},
    ],
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Run vector buffer analysis on GeoJSON/Shapefile layers. Generates coverage zones around point, line, or polygon features.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


def run(ctx):
    from geoclaw_claude.analysis.spatial_ops import buffer

    layer    = ctx.get_layer("input")
    distance = float(ctx.param("distance", 500.0))
    do_dissolve = str(ctx.param("dissolve", "false")).lower() in ("true", "1", "yes")

    print(f"  输入要素数: {len(layer)}")
    print(f"  缓冲距离  : {distance} 米")

    result = buffer(layer, distance, unit="meters")

    if do_dissolve:
        from geoclaw_claude.analysis.spatial_ops import dissolve as _dissolve
        result = _dissolve(result)
        print("  已合并重叠缓冲区")

    # 面积统计
    utm = result.data.to_crs(epsg=32650)
    total_km2 = float(utm.area.sum() / 1e6)
    avg_km2   = float(utm.area.mean() / 1e6)

    report = (
        f"缓冲区分析结果\n"
        f"  输入要素: {len(layer)} 个\n"
        f"  缓冲距离: {distance} 米\n"
        f"  缓冲总面积: {total_km2:.4f} km²\n"
        f"  平均单体面积: {avg_km2:.4f} km²\n"
        f"  合并模式: {'是' if do_dissolve else '否'}"
    )
    print(report)

    ai = ctx.ask_ai(
        "请简要评价以下缓冲区分析结果的空间覆盖合理性（50-100字）：",
        context_data=report,
    )
    if ai and not ai.startswith("(AI"):
        report += f"\n\nAI 评价:\n{ai}"

    return ctx.result(buffer=result, report=report)
