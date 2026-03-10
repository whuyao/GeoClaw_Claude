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
}


def run(ctx):
    from geoclaw_claude.analysis.spatial_ops import zonal_stats

    zones     = ctx.get_layer("zones")
    values    = ctx.get_layer("values")
    stats_str = str(ctx.param("stats", "count"))
    value_col = str(ctx.param("value_col", "")).strip() or None

    stats_list = [s.strip() for s in stats_str.split(",")]
    print(f"  区域数     : {len(zones)}")
    print(f"  统计目标数 : {len(values)}")
    print(f"  统计项     : {stats_list}")

    kwargs = dict(stats=stats_list)
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
