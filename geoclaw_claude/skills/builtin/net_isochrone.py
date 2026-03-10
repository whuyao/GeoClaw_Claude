"""
net_isochrone.py — 等时圈 / 服务区分析 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "net_isochrone",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "等时圈分析：以设施点为中心，计算指定时间/距离内可达的路网服务区范围",
    "category":    "network",
    "inputs": [
        {"name": "city",        "type": "str",   "desc": "城市名称（下载OSM路网）"},
        {"name": "center_lon",  "type": "float", "desc": "设施中心点经度"},
        {"name": "center_lat",  "type": "float", "desc": "设施中心点纬度"},
        {"name": "cutoffs",     "type": "str",   "desc": "截断值列表（分钟或米，逗号分隔）", "default": "5,10,15"},
        {"name": "weight",      "type": "str",   "desc": "权重: travel_time / length",       "default": "travel_time"},
        {"name": "network_type","type": "str",   "desc": "路网类型: drive/walk/bike",         "default": "walk"},
    ],
    "outputs": [
        {"name": "isochrones", "type": "GeoLayer", "desc": "等时圈多边形图层"},
        {"name": "report",     "type": "str",       "desc": "各等时圈面积统计"},
    ],
}


def run(ctx):
    from geoclaw_claude.analysis.network import build_network, isochrone, nearest_node

    city         = str(ctx.param("city", "")).strip()
    center_lon   = float(ctx.param("center_lon", 0))
    center_lat   = float(ctx.param("center_lat", 0))
    cutoffs_str  = str(ctx.param("cutoffs", "5,10,15"))
    weight       = str(ctx.param("weight", "travel_time"))
    network_type = str(ctx.param("network_type", "walk"))

    cutoffs = [float(x.strip()) for x in cutoffs_str.split(",")]
    # travel_time 单位秒，输入为分钟时转换
    if weight == "travel_time":
        cutoffs_sec = [c * 60 for c in cutoffs]
        unit_label  = "分钟"
    else:
        cutoffs_sec = cutoffs
        unit_label  = "米"

    print(f"  下载路网: {city} ({network_type})")
    G = build_network(city, network_type=network_type)

    center_node, snap_dist = nearest_node(G, center_lon, center_lat)
    print(f"  中心点捕捉距离: {snap_dist:.1f} 米")

    result = isochrone(G, center_node, cutoffs=cutoffs_sec, weight=weight)

    # 面积统计
    utm = result.data.to_crs(epsg=32650)
    lines = [f"等时圈分析结果", f"  路网类型: {network_type}", f"  权重   : {weight}"]
    for i, row in utm.iterrows():
        area_km2 = row.geometry.area / 1e6
        cutoff_val = cutoffs[i] if i < len(cutoffs) else "?"
        lines.append(f"  {cutoff_val} {unit_label} 等时圈面积: {area_km2:.4f} km²")
    report = "\n".join(lines)
    print(report)

    ai = ctx.ask_ai(
        "请解读以下等时圈分析结果，评估该设施的可达性水平（50-100字）：",
        context_data=report,
    )
    if ai and not ai.startswith("(AI"):
        report += f"\n\nAI 解读:\n{ai}"

    return ctx.result(isochrones=result, report=report)
