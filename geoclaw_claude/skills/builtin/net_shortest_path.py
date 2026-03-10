"""
net_shortest_path.py — 最短路径分析 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "net_shortest_path",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "最短路径分析：基于路网计算起终点间最短（最快）路径，输出路径线图层与距离/时间统计",
    "category":    "network",
    "inputs": [
        {"name": "city",        "type": "str",   "desc": "城市名称（用于下载OSM路网）", "default": ""},
        {"name": "orig_lon",    "type": "float", "desc": "起点经度"},
        {"name": "orig_lat",    "type": "float", "desc": "起点纬度"},
        {"name": "dest_lon",    "type": "float", "desc": "终点经度"},
        {"name": "dest_lat",    "type": "float", "desc": "终点纬度"},
        {"name": "weight",      "type": "str",   "desc": "权重: length（距离）/ travel_time（时间）", "default": "length"},
        {"name": "network_type","type": "str",   "desc": "路网类型: drive/walk/bike/all", "default": "drive"},
    ],
    "outputs": [
        {"name": "path",   "type": "GeoLayer", "desc": "最短路径线图层"},
        {"name": "report", "type": "str",       "desc": "路径距离与耗时统计"},
    ],
}


def run(ctx):
    from geoclaw_claude.analysis.network import build_network, shortest_path, nearest_node

    city         = str(ctx.param("city", "")).strip()
    orig_lon     = float(ctx.param("orig_lon", 0))
    orig_lat     = float(ctx.param("orig_lat", 0))
    dest_lon     = float(ctx.param("dest_lon", 0))
    dest_lat     = float(ctx.param("dest_lat", 0))
    weight       = str(ctx.param("weight", "length"))
    network_type = str(ctx.param("network_type", "drive"))

    if not city:
        raise ValueError("请提供 city 参数（如 '武汉市'）用于下载路网")

    print(f"  下载路网: {city} ({network_type})")
    G = build_network(city, network_type=network_type)

    orig_node, orig_dist = nearest_node(G, orig_lon, orig_lat)
    dest_node, dest_dist = nearest_node(G, dest_lon, dest_lat)

    print(f"  起点最近节点距离: {orig_dist:.1f} 米")
    print(f"  终点最近节点距离: {dest_dist:.1f} 米")

    path_result = shortest_path(G, orig_node, dest_node, weight=weight)

    total_length = path_result.get("length_m", 0)
    total_time   = path_result.get("travel_time_s", None)

    report = (
        f"最短路径分析结果\n"
        f"  城市/路网  : {city} ({network_type})\n"
        f"  权重       : {weight}\n"
        f"  路径长度   : {total_length:.1f} 米\n"
    )
    if total_time:
        report += f"  预计行驶时间: {total_time/60:.1f} 分钟\n"
    print(report)

    ai = ctx.ask_ai(
        "请评价以下路径规划结果，并给出出行建议（50-80字）：",
        context_data=report,
    )
    if ai and not ai.startswith("(AI"):
        report += f"\nAI 建议:\n{ai}"

    path_layer = path_result.get("path_layer")
    return ctx.result(path=path_layer, report=report)
