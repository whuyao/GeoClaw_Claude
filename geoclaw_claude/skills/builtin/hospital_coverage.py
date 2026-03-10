"""
hospital_coverage.py — 内置 Skill
===================================
分析医院服务覆盖范围，计算覆盖率和可达性指标。
支持 AI 解读分析结果。
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "hospital_coverage",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "医院服务覆盖分析：缓冲区叠加 + 覆盖率统计 + AI 解读",
    "inputs": [
        {"name": "hospitals", "type": "GeoLayer", "desc": "医院点图层"},
        {"name": "boundary",  "type": "GeoLayer", "desc": "研究区边界图层（可选）", "required": False},
        {"name": "radius_km", "type": "float",    "desc": "服务半径(km)", "default": 3.0},
    ],
    "outputs": [
        {"name": "coverage",  "type": "GeoLayer", "desc": "覆盖缓冲区图层"},
        {"name": "report",    "type": "str",       "desc": "分析报告文本"},
    ],
    # ── OpenClaw / AgentSkills 兼容声明（供 skill export 命令使用）
    "agentskills_compat": {
        "enabled":            True,
        "export_description": 'Hospital service coverage analysis: buffer overlay + coverage rate statistics + optional AI commentary.',
        "requires_bins":      ['python3', 'geoclaw-claude'],
        "requires_env":       [],
        "homepage":           'https://github.com/whuyao/GeoClaw_Claude',
    },
}


def run(ctx):
    """
    执行医院覆盖分析。

    流程:
      1. 读取医院点图层
      2. 生成服务半径缓冲区
      3. 计算覆盖面积/覆盖率
      4. （可选）AI 解读结果
      5. 输出覆盖图层和报告
    """
    import geopandas as gpd
    from geoclaw_claude.analysis.spatial_ops import buffer, dissolve

    # ── 读取输入 ──────────────────────────────────────────────────────────────
    hospitals = ctx.get_layer("input")  # CLI 传入时默认名为 input
    radius_km = float(ctx.param("radius_km", 3.0))

    print(f"  医院数量: {len(hospitals)}")
    print(f"  服务半径: {radius_km} km")

    # ── 生成缓冲区 ────────────────────────────────────────────────────────────
    coverage = buffer(hospitals, radius_km * 1000, unit="meters")
    coverage_union = dissolve(coverage)  # 合并重叠缓冲区

    # ── 统计指标 ──────────────────────────────────────────────────────────────
    # 转 UTM 计算面积
    coverage_utm = coverage_union.data.to_crs(epsg=32650)
    total_area_km2 = float(coverage_utm.area.sum() / 1e6)

    # 各医院缓冲区面积
    hosp_utm = coverage.data.to_crs(epsg=32650)
    avg_area = float(hosp_utm.area.mean() / 1e6)

    stats = {
        "hospital_count":   len(hospitals),
        "radius_km":        radius_km,
        "total_coverage_km2": round(total_area_km2, 2),
        "avg_coverage_km2": round(avg_area, 4),
    }

    # 如果有边界图层，计算覆盖率
    try:
        boundary = ctx.get_layer("boundary")
        boundary_utm = boundary.data.to_crs(epsg=32650)
        study_area_km2 = float(boundary_utm.area.sum() / 1e6)
        coverage_rate = min(total_area_km2 / study_area_km2 * 100, 100)
        stats["study_area_km2"] = round(study_area_km2, 2)
        stats["coverage_rate_pct"] = round(coverage_rate, 1)
        print(f"  覆盖率: {coverage_rate:.1f}%")
    except Exception:
        stats["coverage_rate_pct"] = None

    # ── 统计报告 ──────────────────────────────────────────────────────────────
    report_lines = [
        "=" * 50,
        "  医院服务覆盖分析报告",
        "=" * 50,
        f"  医院数量        : {stats['hospital_count']} 所",
        f"  服务半径        : {stats['radius_km']} km",
        f"  覆盖总面积      : {stats['total_coverage_km2']} km²",
        f"  单院平均覆盖    : {stats['avg_coverage_km2']} km²",
    ]
    if stats.get("coverage_rate_pct") is not None:
        report_lines += [
            f"  研究区面积      : {stats['study_area_km2']} km²",
            f"  空间覆盖率      : {stats['coverage_rate_pct']}%",
        ]
    report_lines.append("=" * 50)
    report = "\n".join(report_lines)
    print(report)

    # ── AI 分析（可选）────────────────────────────────────────────────────────
    ai_result = ctx.ask_ai(
        "请用中文分析以下医院空间分布数据，评估医疗服务可及性，"
        "并给出改善建议（100-200字）：",
        context_data="\n".join([f"{k}: {v}" for k, v in stats.items()]),
    )
    if ai_result and not ai_result.startswith("(AI"):
        print(f"\n  AI 分析:\n  {ai_result}\n")
        report += f"\n\nAI 分析:\n{ai_result}"

    return ctx.result(coverage=coverage_union, report=report)
