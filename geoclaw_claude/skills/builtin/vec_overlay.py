"""
vec_overlay.py — 矢量叠加分析 Skill（裁剪 / 相交 / 合并）
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "vec_overlay",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "矢量叠加分析：支持 clip（裁剪）、intersect（相交）、union（合并）三种操作",
    "category":    "vector",
    "inputs": [
        {"name": "layer_a",    "type": "GeoLayer", "desc": "主图层"},
        {"name": "layer_b",    "type": "GeoLayer", "desc": "叠加图层（掩膜/范围）"},
        {"name": "operation",  "type": "str",      "desc": "操作类型: clip / intersect / union", "default": "clip"},
    ],
    "outputs": [
        {"name": "result", "type": "GeoLayer", "desc": "叠加结果图层"},
        {"name": "report", "type": "str",       "desc": "要素数量变化统计"},
    ],
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Spatial overlay: clip, intersect, or union two vector layers.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


def run(ctx):
    from geoclaw_claude.analysis.spatial_ops import clip, intersect, union

    layer_a   = ctx.get_layer("layer_a")
    layer_b   = ctx.get_layer("layer_b")
    operation = str(ctx.param("operation", "clip")).lower().strip()

    print(f"  操作: {operation}")
    print(f"  layer_a 要素数: {len(layer_a)}")
    print(f"  layer_b 要素数: {len(layer_b)}")

    if operation == "clip":
        result = clip(layer_a, layer_b)
        op_zh = "裁剪"
    elif operation == "intersect":
        result = intersect(layer_a, layer_b)
        op_zh = "相交"
    elif operation == "union":
        result = union(layer_a, layer_b)
        op_zh = "合并"
    else:
        raise ValueError(f"不支持的操作类型: {operation}，请选择 clip / intersect / union")

    print(f"  结果要素数: {len(result)}")

    report = (
        f"矢量{op_zh}分析结果\n"
        f"  操作类型  : {operation}\n"
        f"  输入要素A : {len(layer_a)} 个\n"
        f"  输入要素B : {len(layer_b)} 个\n"
        f"  输出要素  : {len(result)} 个\n"
        f"  要素变化  : {len(result) - len(layer_a):+d}"
    )
    print(report)
    return ctx.result(result=result, report=report)
