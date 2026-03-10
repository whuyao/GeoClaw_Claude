"""
vec_kde.py — 核密度估计（KDE）Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "vec_kde",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "核密度估计（KDE）：分析点要素的空间聚集热点，生成密度栅格图",
    "category":    "vector",
    "inputs": [
        {"name": "input",      "type": "GeoLayer", "desc": "输入点图层"},
        {"name": "bandwidth",  "type": "float",    "desc": "带宽（米，影响平滑程度）", "default": 500.0},
        {"name": "resolution", "type": "float",    "desc": "输出栅格分辨率（米）",     "default": 100.0},
        {"name": "weight_col", "type": "str",      "desc": "权重字段（可选，空则等权）", "default": ""},
    ],
    "outputs": [
        {"name": "density", "type": "GeoLayer", "desc": "核密度栅格/矢量结果"},
        {"name": "report",  "type": "str",       "desc": "密度统计摘要"},
    ],
}


def run(ctx):
    from geoclaw_claude.analysis.spatial_ops import kde

    layer      = ctx.get_layer("input")
    bandwidth  = float(ctx.param("bandwidth", 500.0))
    resolution = float(ctx.param("resolution", 100.0))
    weight_col = str(ctx.param("weight_col", "")).strip() or None

    print(f"  输入点数   : {len(layer)}")
    print(f"  带宽       : {bandwidth} 米")
    print(f"  分辨率     : {resolution} 米")
    if weight_col:
        print(f"  权重字段   : {weight_col}")

    kwargs = dict(bandwidth=bandwidth, resolution=resolution)
    if weight_col:
        kwargs["weight_col"] = weight_col

    result = kde(layer, **kwargs)

    report = (
        f"核密度估计结果\n"
        f"  输入点数   : {len(layer)}\n"
        f"  带宽       : {bandwidth} 米\n"
        f"  分辨率     : {resolution} 米\n"
        f"  权重字段   : {weight_col or '无（等权）'}\n"
        f"  输出要素数 : {len(result)}"
    )
    print(report)

    ai = ctx.ask_ai(
        "请分析以下核密度估计参数配置是否合理，并说明热点聚集的空间意义（50-100字）：",
        context_data=report,
    )
    if ai and not ai.startswith("(AI"):
        report += f"\n\nAI 解读:\n{ai}"

    return ctx.result(density=result, report=report)
