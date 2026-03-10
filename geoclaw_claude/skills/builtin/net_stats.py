"""
net_stats.py — 路网统计分析 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "net_stats",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "路网统计：计算节点数、边数、平均度、总长度、连通性等路网拓扑指标",
    "category":    "network",
    "inputs": [
        {"name": "city",         "type": "str",   "desc": "城市名称（下载OSM路网）"},
        {"name": "network_type", "type": "str",   "desc": "路网类型: drive/walk/bike/all", "default": "drive"},
        {"name": "area_km2",     "type": "float", "desc": "研究区面积(km²)，用于密度计算（可选）", "default": 0},
    ],
    "outputs": [
        {"name": "report", "type": "str", "desc": "路网拓扑统计报告"},
    ],
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Road network topology statistics: node count, edge count, average degree, total length, and connectivity metrics.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


def run(ctx):
    from geoclaw_claude.analysis.network import build_network, network_stats

    city         = str(ctx.param("city", "")).strip()
    network_type = str(ctx.param("network_type", "drive"))
    area_km2     = float(ctx.param("area_km2", 0)) or None

    print(f"  下载路网: {city} ({network_type})")
    G = build_network(city, network_type=network_type)

    stats = network_stats(G, area_km2=area_km2)

    lines = [
        "路网统计分析结果",
        f"  城市      : {city}",
        f"  路网类型  : {network_type}",
    ]
    for k, v in stats.items():
        if isinstance(v, float):
            lines.append(f"  {k:<20}: {v:.4f}")
        else:
            lines.append(f"  {k:<20}: {v}")
    report = "\n".join(lines)
    print(report)

    ai = ctx.ask_ai(
        "请根据以下路网统计指标，评价该城市路网的连通性和密度水平（50-100字）：",
        context_data=report,
    )
    if ai and not ai.startswith("(AI"):
        report += f"\n\nAI 评价:\n{ai}"

    return ctx.result(report=report)
