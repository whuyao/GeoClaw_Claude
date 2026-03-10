"""
vec_zonal_stats.py — 矢量分区统计 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "vec_zonal_stats",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "分区统计：按区域多边形统计目标图层的数量、面积、字段均值等空间聚合指标",
    "category":    "vector",
    "inputs": [
        {"name": "zones",      "type": "GeoLayer", "desc": "区域多边形图层（分区依据）"},
        {"name": "values",     "type": "GeoLayer", "desc": "统计目标图层（点/面）"},
        {"name": "stats",      "type": "str",      "desc": "统计项（逗号分隔）: count,sum,mean,min,max", "default": "count"},
        {"name": "value_col",  "type": "str",      "desc": "数值字段（sum/mean/min/max 需要）", "default": ""},
    ],
    "outputs": [
        {"name": "result", "type": "GeoLayer", "desc": "含统计字段的区域图层"},
        {"name": "report", "type": "str",       "desc": "各区统计摘要"},
    ],
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Zonal statistics: count, area, and field aggregation per polygon zone.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


def run(ctx):
    from geoclaw_claude.analysis.spatial_ops import zonal_stats

    # 兼容多种图层名：zones/regions/area；values/points/target/input
    def _get_layer_flexible(ctx, *names):
        for n in names:
            try: return ctx.get_layer(n)
            except KeyError: pass
        raise KeyError(f"找不到图层，已尝试: {names}")

    zones  = _get_layer_flexible(ctx, "zones", "regions", "area", "zone_layer")
    values = _get_layer_flexible(ctx, "values", "points", "target", "input", "point_layer")
    stats_str = str(ctx.param("stats", "count"))
    value_col = str(ctx.param("value_col", "")).strip() or None

    stats_list = [s.strip() for s in stats_str.split(",")]
    print(f"  区域数     : {len(zones)}")
    print(f"  统计目标数 : {len(values)}")
    print(f"  统计项     : {stats_list}")

    # 底层 zonal_stats 只接受单个 stat 字符串，取列表第一项
    kwargs = dict(stat=stats_list[0] if stats_list else "count")
    if value_col:
        kwargs["value_col"] = value_col

    result = zonal_stats(zones, values, **kwargs)

    # 汇总输出字段
    new_cols = [c for c in result.data.columns if c not in zones.data.columns]
    lines = [f"分区统计结果", f"  区域数    : {len(result)}", f"  新增字段  : {new_cols}"]
    for col in new_cols:
        try:
            s = result.data[col]
            lines.append(f"  {col}: min={s.min():.2f}, max={s.max():.2f}, mean={s.mean():.2f}")
        except Exception:
            pass
    report = "\n".join(lines)
    print(report)

    ai = ctx.ask_ai(
        "请对以下分区统计结果进行简要空间差异评价（50-100字）：",
        context_data=report,
    )
    if ai and not ai.startswith("(AI"):
        report += f"\n\nAI 分析:\n{ai}"

    return ctx.result(result=result, report=report)
