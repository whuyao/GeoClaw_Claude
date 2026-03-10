"""
vec_spatial_join.py — 空间连接 & 最近邻分析 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "vec_spatial_join",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "空间连接与最近邻：将两图层按空间关系连接属性，或计算每个要素到最近邻的距离",
    "category":    "vector",
    "inputs": [
        {"name": "layer_a",     "type": "GeoLayer", "desc": "主图层（接受属性的一侧）"},
        {"name": "layer_b",     "type": "GeoLayer", "desc": "参考图层（提供属性的一侧）"},
        {"name": "mode",        "type": "str",      "desc": "模式: spatial_join / nearest", "default": "spatial_join"},
        {"name": "how",         "type": "str",      "desc": "连接方式(spatial_join): left/inner/right", "default": "left"},
        {"name": "predicate",   "type": "str",      "desc": "空间谓词: intersects/within/contains", "default": "intersects"},
        {"name": "k",           "type": "int",      "desc": "最近邻数量(nearest模式)", "default": 1},
    ],
    "outputs": [
        {"name": "result", "type": "GeoLayer", "desc": "连接结果图层"},
        {"name": "report", "type": "str",       "desc": "统计摘要"},
    ],
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Spatial join and nearest-neighbour analysis between two vector layers.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


def run(ctx):
    from geoclaw_claude.analysis.spatial_ops import spatial_join, nearest_neighbor

    layer_a   = ctx.get_layer("layer_a")
    layer_b   = ctx.get_layer("layer_b")
    mode      = str(ctx.param("mode", "spatial_join")).lower()
    how       = str(ctx.param("how", "left"))
    predicate = str(ctx.param("predicate", "intersects"))
    k         = int(ctx.param("k", 1))

    if mode == "spatial_join":
        result = spatial_join(layer_a, layer_b, how=how, predicate=predicate)
        report = (
            f"空间连接结果\n"
            f"  连接方式   : {how}\n"
            f"  空间谓词   : {predicate}\n"
            f"  layer_a    : {len(layer_a)} 个要素\n"
            f"  layer_b    : {len(layer_b)} 个要素\n"
            f"  连接结果   : {len(result)} 条记录\n"
            f"  新增字段   : {[c for c in result.data.columns if c not in layer_a.data.columns]}"
        )
    elif mode == "nearest":
        result = nearest_neighbor(layer_a, layer_b, k=k)
        dist_col = [c for c in result.data.columns if "dist" in c.lower()]
        if dist_col:
            avg_dist = result.data[dist_col[0]].mean()
            report = (
                f"最近邻分析结果\n"
                f"  邻居数 k   : {k}\n"
                f"  输入要素   : {len(layer_a)} 个\n"
                f"  参考要素   : {len(layer_b)} 个\n"
                f"  平均最近距离: {avg_dist:.2f} 米"
            )
        else:
            report = f"最近邻分析完成，结果要素: {len(result)} 个"
    else:
        raise ValueError(f"不支持的模式: {mode}，请选择 spatial_join 或 nearest")

    print(report)
    return ctx.result(result=result, report=report)
