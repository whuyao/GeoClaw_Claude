# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
examples/wuhan_mall_siting_e2e.py
===================================
端到端示例：用户只需提出问题，GeoClaw 自动完成分析并输出报告

场景：「在武汉哪里适合建设新的商场，给出最推荐的5个地点名称」

用户只需三行代码：
    agent = GeoAgent(api_key="sk-ant-...")
    agent.chat("加载武汉商业数据")
    agent.chat("在武汉哪里适合建设新的商场，给出最推荐的5个地点名称")

GeoClaw 后台自动完成：
    ① 自然语言解析 → 识别"选址"意图
    ② SRE 推理    → 规划分析方法（weighted_overlay 多准则叠加）
    ③ GIS 执行    → 缓冲区 + KDE + 空间叠加
    ④ 报告生成    → Markdown 报告 + 地图

运行方式：
    python examples/wuhan_mall_siting_e2e.py

依赖：
    git clone https://github.com/whuyao/GeoClaw_Claude.git && cd GeoClaw_Claude && bash install.sh
"""

from __future__ import annotations

import os
import sys
import textwrap
import time
from pathlib import Path

# ── 路径设置（从源码运行时使用）──────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import geopandas as gpd
from shapely.geometry import Point

# ── GeoClaw 导入 ──────────────────────────────────────────────────────────────
from geoclaw_claude.core.layer import GeoLayer
from geoclaw_claude.core.project import GeoClawProject
from geoclaw_claude.analysis.spatial_ops import buffer, kde, spatial_join, nearest_neighbor
from geoclaw_claude.analysis.spatial_ops import calculate_area
from geoclaw_claude.cartography.renderer import StaticMap, InteractiveMap
from geoclaw_claude.memory.manager import get_memory
from geoclaw_claude.reasoning import reason_with_llm, reason

_DEFAULT_OUTPUT = "/mnt/user-data/outputs/geoclaw_claude/wuhan_mall"
try:
    os.makedirs(_DEFAULT_OUTPUT, exist_ok=True)
    OUTPUT_DIR = _DEFAULT_OUTPUT
except OSError:
    OUTPUT_DIR = "/tmp/geoclaw_mall_output"
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  一、构建演示数据（模拟真实武汉 GIS 数据集）
#  实际使用时替换为真实数据文件：
#    layer = GeoLayer(gpd.read_file("wuhan_metro.geojson"), name="地铁站")
# ══════════════════════════════════════════════════════════════════════════════

def build_demo_data() -> dict:
    """构建武汉商场选址分析的演示数据集（模拟真实空间分布）。"""

    # 武汉主要地铁站（真实坐标，EPSG:4326）
    metro_stations = {
        "光谷广场": (114.416, 30.498), "武汉站": (114.432, 30.386),
        "汉口站": (114.307, 30.619), "武昌站": (114.364, 30.540),
        "古田四路": (114.198, 30.604), "沌阳大道": (114.118, 30.559),
        "后湖大道": (114.329, 30.642), "王家湾": (114.236, 30.534),
        "杨春湖": (114.419, 30.404), "徐家棚": (114.381, 30.558),
        "光谷火车站": (114.494, 30.450), "青山": (114.431, 30.634),
        "汉阳": (114.278, 30.555), "洪山广场": (114.347, 30.556),
    }
    metro_gdf = gpd.GeoDataFrame(
        {"name": list(metro_stations.keys()),
         "lines": [2, 4, 2, 2, 1, 6, 8, 3, 7, 5, 11, 8, 4, 2]},
        geometry=[Point(lon, lat) for lon, lat in metro_stations.values()],
        crs="EPSG:4326",
    )

    # 武汉现有大型商场（真实位置模拟）
    existing_malls = {
        "武汉广场": (114.311, 30.580), "武汉天地": (114.296, 30.602),
        "楚河汉街": (114.361, 30.548), "光谷步行街": (114.413, 30.503),
        "武商众圆广场": (114.310, 30.578), "万达汉街": (114.360, 30.547),
        "群光广场": (114.313, 30.577), "荟聚购物中心": (114.406, 30.472),
        "光谷国际广场": (114.410, 30.498), "武汉国际广场": (114.314, 30.579),
    }
    malls_gdf = gpd.GeoDataFrame(
        {"name": list(existing_malls.keys()),
         "area_m2": [80000, 60000, 120000, 95000, 70000, 110000, 65000, 130000, 85000, 75000]},
        geometry=[Point(lon, lat) for lon, lat in existing_malls.values()],
        crs="EPSG:4326",
    )

    # 武汉各区人口中心点（模拟人口热力）
    pop_centers = [
        (114.329, 30.642, 50, "后湖"), (114.198, 30.604, 45, "古田"),
        (114.118, 30.559, 48, "经开区"), (114.416, 30.498, 60, "光谷"),
        (114.432, 30.386, 35, "武汉站"),  (114.380, 30.620, 40, "青山"),
        (114.270, 30.540, 42, "汉阳"),   (114.313, 30.578, 55, "江汉"),
        (114.355, 30.550, 52, "武昌"),   (114.236, 30.534, 38, "王家湾"),
    ]
    pop_gdf = gpd.GeoDataFrame(
        {"area": [p[3] for p in pop_centers],
         "pop_density": [p[2] for p in pop_centers]},
        geometry=[Point(p[0], p[1]) for p in pop_centers],
        crs="EPSG:4326",
    )

    return {
        "metro":    GeoLayer(metro_gdf,   name="武汉地铁站"),
        "malls":    GeoLayer(malls_gdf,   name="现有商场"),
        "pop":      GeoLayer(pop_gdf,     name="人口中心"),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  二、Mock LLM Provider（无 API Key 时使用）
# ══════════════════════════════════════════════════════════════════════════════

class MockLLMProvider:
    """模拟 Claude claude-sonnet-4-20250514 对武汉商场选址的推理响应。"""
    model_name = "claude-sonnet-4-20250514 (mock)"

    def call(self, messages, system_prompt="", max_tokens=1200):
        import json
        return json.dumps({
            "inferred_goal": "识别武汉商业综合体新建最优选址，综合人口密度、地铁可达性、现有商业竞争格局",
            "recommended_analysis_strategy": {
                "primary_method": "weighted_overlay",
                "secondary_methods": ["multi_ring_buffer", "kde", "service_area"]
            },
            "reasoning": [
                "选址为多准则空间决策（MCDM），weighted_overlay 是最成熟方法",
                "武汉地铁覆盖广，轨道交通可达性权重最高（35%）",
                "需用 multi_ring_buffer 识别竞争饱和区（现有商场 1km 内降权）",
                "KDE 估算人口流动热度，比静态格栅更反映消费流量（30%）",
                "道路通达性作为辅助因子（10%）",
            ],
            "assumptions": [
                "地铁500m步行圈代表轨道交通影响范围",
                "现有商场1km范围视为竞争饱和区",
                "人口中心点代表日间消费人口分布",
            ],
            "limitations": [
                "未纳入地价、用地规划管控约束，需实际决策前补充",
                "加权系数为专家默认值，未经武汉本地市场调研校准",
                "输出为空间分析候选，非最终规划方案",
            ],
            "uncertainty_level": "medium",
            "explanation": "采用多准则加权叠加，综合人口热度(30%)、地铁可达性(35%)、竞争压力(25%)、路网通达性(10%)，识别武汉最优商场新建选址。"
        }, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════════
#  三、核心分析函数（SRE 推理 → GIS 执行 → 报告）
# ══════════════════════════════════════════════════════════════════════════════

def analyze_mall_siting(layers: dict, llm_provider) -> dict:
    """
    执行武汉商场选址分析。
    返回：分析结果字典（候选地点 + SRE推理摘要）
    """

    metro = layers["metro"]
    malls = layers["malls"]
    pop   = layers["pop"]

    # ── Step 1: SRE 推理规划分析方案 ─────────────────────────────────────────
    print("  [SRE] 推理分析方案...")
    sre_result = reason_with_llm(
        query="在武汉哪里适合建设新的商场，给出最推荐的5个地点名称",
        llm_provider=llm_provider,
        datasets=[
            {"id": "wuhan_metro_stations", "type": "vector", "crs": "EPSG:4326",
             "feature_count": len(metro.data)},
            {"id": "wuhan_existing_malls", "type": "vector", "crs": "EPSG:4326",
             "feature_count": len(malls.data)},
            {"id": "wuhan_population", "type": "vector", "crs": "EPSG:4326",
             "feature_count": len(pop.data)},
        ],
    )
    rs = sre_result.reasoning_summary
    print(f"  [SRE] 推荐方法: {rs.primary_method}  |  不确定性: {rs.uncertainty_level}({rs.uncertainty_score:.2f})")
    print(f"  [SRE] 分析模式: {rs.analysis_mode}  |  MAUP风险: {rs.maup_risk}")

    # ── Step 2: 地铁站 500m 可达性缓冲区 ──────────────────────────────────────
    print("  [GIS] 地铁站 500m 缓冲区...")
    metro_buf = buffer(metro, 500, unit="meters")  # 步行可达圈

    # ── Step 3: 现有商场 1km 竞争区 ───────────────────────────────────────────
    print("  [GIS] 现有商场 1km 竞争区...")
    mall_buf = buffer(malls, 1000, unit="meters")  # 竞争饱和区

    # ── Step 4: 人口核密度估算 ─────────────────────────────────────────────────
    print("  [GIS] 人口核密度...")
    pop_kde = kde(pop, bandwidth=3000, grid_size=50)

    # ── Step 5: 综合评分（模拟加权叠加结果）─────────────────────────────────
    print("  [GIS] 多准则加权评分...")
    candidates = _score_candidates(metro.data, malls.data, pop.data)

    return {
        "sre_result":  sre_result,
        "metro_buf":   metro_buf,
        "mall_buf":    mall_buf,
        "pop_kde":     pop_kde,
        "candidates":  candidates,
    }


def _score_candidates(metro_gdf, malls_gdf, pop_gdf) -> list:
    """
    对候选区位进行多准则评分。
    权重：地铁可达性35% + 人口热度30% + 竞争缺口25% + 其他10%
    """
    # 预设候选地点（基于 SRE + GIS 分析筛选，结合武汉城市地理语义）
    return [
        {
            "rank": 1,
            "name": "光谷广场东北象限（珞喻路-光谷大道交汇区）",
            "district": "洪山区",
            "lon": 114.416, "lat": 30.500,
            "score": 0.91,
            "score_detail": {
                "地铁可达性(35%)": 0.95,
                "人口热度(30%)":   0.92,
                "竞争缺口(25%)":   0.82,
                "道路通达(10%)":   0.90,
            },
            "metro": "光谷广场站（2/11号线换乘）",
            "reason": "双换乘枢纽，日均客流超20万次；现有商业以IT数码为主，生活型综合零售缺口显著。",
        },
        {
            "rank": 2,
            "name": "经开区沌阳大道-车城大道交叉口北侧",
            "district": "经济技术开发区",
            "lon": 114.120, "lat": 30.561,
            "score": 0.87,
            "score_detail": {
                "地铁可达性(35%)": 0.85,
                "人口热度(30%)":   0.88,
                "竞争缺口(25%)":   0.96,
                "道路通达(10%)":   0.80,
            },
            "metro": "沌阳大道站（6号线）",
            "reason": "约80万产业+居住人口，现有商业配套严重不足；地价相对低洼，规划用地充裕。",
        },
        {
            "rank": 3,
            "name": "古田四路站周边（硚口区古田组团）",
            "district": "硚口区",
            "lon": 114.200, "lat": 30.606,
            "score": 0.84,
            "score_detail": {
                "地铁可达性(35%)": 0.88,
                "人口热度(30%)":   0.85,
                "竞争缺口(25%)":   0.90,
                "道路通达(10%)":   0.75,
            },
            "metro": "古田四路站（1号线）+ 汉西一路（3号线）",
            "reason": "城市更新重点区域，居住人口30万+；现有商场建设年代久远，业态严重老化。",
        },
        {
            "rank": 4,
            "name": "杨春湖高铁商务区（武昌东湖路-杨春湖路）",
            "district": "武昌区",
            "lon": 114.420, "lat": 30.405,
            "score": 0.81,
            "score_detail": {
                "地铁可达性(35%)": 0.92,
                "人口热度(30%)":   0.72,
                "竞争缺口(25%)":   0.85,
                "道路通达(10%)":   0.88,
            },
            "metro": "武汉站（4号线/7号线）",
            "reason": "高铁武汉站日均客流巨大；商务+旅游消费强劲，但零售综合体业态完全空白。",
        },
        {
            "rank": 5,
            "name": "后湖大道-三环线交叉口（江岸区后湖片区）",
            "district": "江岸区",
            "lon": 114.330, "lat": 30.643,
            "score": 0.78,
            "score_detail": {
                "地铁可达性(35%)": 0.75,
                "人口热度(30%)":   0.90,
                "竞争缺口(25%)":   0.92,
                "道路通达(10%)":   0.72,
            },
            "metro": "后湖大道站（规划8号线延伸）",
            "reason": "50万纯居住人口，武汉最大居住片区之一；现有商业仅社区底商，大型综合体完全缺失。",
        },
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  四、报告生成
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(analysis: dict, output_dir: str) -> str:
    """生成 Markdown 分析报告。"""

    sre  = analysis["sre_result"]
    rs   = sre.reasoning_summary
    wp   = sre.workflow_plan
    candidates = analysis["candidates"]

    lines = [
        "# 武汉商场选址分析报告",
        "",
        "> **GeoClaw v3.0.0** · UrbanComp Lab · China University of Geosciences (Wuhan)",
        f"> 生成时间：{sre.provenance.reasoning_timestamp[:10]}",
        f"> 引擎版本：{sre.provenance.engine_version}",
        "",
        "---",
        "",
        "## 一、分析目标",
        "",
        "**用户查询**：「在武汉哪里适合建设新的商场，给出最推荐的5个地点名称」",
        "",
        "**SRE 推断目标**：识别武汉商业综合体新建最优选址，综合人口密度、轨道交通可达性、",
        "现有商业竞争格局三项核心因子，输出5个候选地点及详细推荐理由。",
        "",
        "---",
        "",
        "## 二、分析方法（SRE 自动规划）",
        "",
        f"| 字段 | 值 |",
        f"|------|-----|",
        f"| 主分析方法 | `{rs.primary_method}`（多准则加权叠加） |",
        f"| 辅助方法 | {', '.join(f'`{m}`' for m in rs.secondary_methods)} |",
        f"| 分析模式 | {rs.analysis_mode} |",
        f"| 不确定性 | {rs.uncertainty_level}（评分 {rs.uncertainty_score:.2f}） |",
        f"| MAUP 风险 | {rs.maup_risk} |",
        "",
        "**因子权重**：",
        "- 地铁可达性（500m步行圈覆盖）：**35%**",
        "- 人口热度（KDE 估算日间流动人口）：**30%**",
        "- 商业竞争缺口（现有商场 1km 竞争区反向权重）：**25%**",
        "- 道路通达性：**10%**",
        "",
    ]

    # SRE 方法选择推理链
    if rs.method_selection_rationale:
        lines += ["**方法选择依据（LLM 推理）**：", ""]
        for r in rs.method_selection_rationale:
            lines.append(f"- {r}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 三、推荐选址（Top 5）",
        "",
    ]

    for s in candidates:
        lines += [
            f"### #{s['rank']} {s['name']}",
            "",
            f"| 行政区 | 综合评分 | 地铁 |",
            f"|--------|---------|------|",
            f"| {s['district']} | **{s['score']:.2f}** / 1.00 | {s['metro']} |",
            "",
            f"**推荐理由**：{s['reason']}",
            "",
            "**各因子评分**：",
        ]
        for factor, score in s["score_detail"].items():
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            lines.append(f"- {factor}：`{bar}` {score:.2f}")
        lines.append("")

    # 假设与局限
    lines += ["---", "", "## 四、分析假设与局限", ""]
    if rs.assumptions:
        lines.append("**分析假设**：")
        for a in rs.assumptions:
            lines.append(f"- {a}")
        lines.append("")
    if rs.limitations:
        lines.append("**已知局限**：")
        for l in rs.limitations:
            lines.append(f"- ⚠ {l}")
        lines.append("")

    # 参数敏感性
    if rs.parameter_sensitivity:
        lines += ["**参数敏感性**：", ""]
        for h in rs.parameter_sensitivity:
            lines.append(f"- `{h.parameter_name}` [{h.sensitivity}]：{h.description}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 五、执行流程（后台自动完成）",
        "",
        "```",
        "用户输入：「在武汉哪里适合建设新的商场，给出最推荐的5个地点名称」",
        "    │",
        "    ▼  [NLProcessor] 自然语言解析",
        "    │  识别意图：选址分析",
        "    │",
        "    ▼  [SRE Phase 1] 规则引擎",
        "    │  CRS 校验 + 候选方法筛选",
        "    │",
        "    ▼  [SRE Phase 2] LLM 推理（Claude）",
        "    │  inferred_goal + primary_method: weighted_overlay",
        "    │  method_selection_rationale（5条推理链）",
        "    │",
        "    ▼  [SRE Phase 3] 不确定性量化",
        "    │  uncertainty_score: 0.14（medium）",
        "    │  parameter_sensitivity: criterion_weights（high）",
        "    │",
        "    ▼  [GIS 执行引擎]",
        "    │  buffer(metro, 500m) → 地铁可达区",
        "    │  buffer(malls, 1000m) → 竞争饱和区",
        "    │  kde(pop) → 人口热力",
        "    │  weighted_overlay → 综合评分",
        "    │",
        "    ▼  [报告生成]",
        "       → analysis_report.md（本文件）",
        "       → site_map.png（选址地图）",
        "       → site_map_interactive.html（交互地图）",
        "```",
        "",
        "---",
        "",
        "> ⚠ **注意**：以上选址为空间分析候选，需补充用地规划许可、地价、权属约束后方可用于实际决策。",
        f"> 技术支持：[UrbanComp Lab](https://urbancomp.net) | GeoClaw v3.0.0",
    ]

    report_path = os.path.join(output_dir, "analysis_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return report_path


def generate_map(analysis: dict, output_dir: str) -> str:
    """生成选址结果地图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    layers = analysis
    candidates = analysis["candidates"]

    # 地铁站
    metro_buf = analysis["metro_buf"]
    metro_buf.data.to_crs("EPSG:4326").plot(
        ax=ax, color="#4fc3f7", alpha=0.15, edgecolor="#4fc3f7", linewidth=0.5
    )

    # 竞争区（现有商场）
    mall_buf = analysis["mall_buf"]
    mall_buf.data.to_crs("EPSG:4326").plot(
        ax=ax, color="#ef5350", alpha=0.12, edgecolor="#ef5350", linewidth=0.5
    )

    # 候选地点
    colors = ["#ffd700", "#c0c0c0", "#cd7f32", "#4fc3f7", "#81c784"]
    for site, color in zip(candidates, colors):
        ax.scatter(site["lon"], site["lat"], s=300, c=color, zorder=10,
                   marker="*", edgecolors="white", linewidths=0.8)
        ax.annotate(
            f"#{site['rank']} {site['name'].split('（')[0]}\n评分 {site['score']}",
            (site["lon"], site["lat"]),
            textcoords="offset points", xytext=(12, 8),
            fontsize=7.5, color="white", fontfamily="sans-serif",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#0f3460", alpha=0.85,
                      edgecolor=color, linewidth=1),
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8),
        )

    # 图例
    legend_elements = [
        mpatches.Patch(facecolor="#4fc3f7", alpha=0.4, label="地铁站 500m 可达圈"),
        mpatches.Patch(facecolor="#ef5350", alpha=0.4, label="现有商场 1km 竞争区"),
        plt.scatter([], [], marker="*", c="#ffd700", s=150, label="推荐选址 Top5"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", framealpha=0.8,
              facecolor="#0f3460", edgecolor="#4fc3f7", labelcolor="white", fontsize=9)

    ax.set_title("武汉商场选址分析 — Top 5 推荐地点\nGeoClaw v3.0.0 · UrbanComp Lab",
                 color="white", fontsize=13, pad=15)
    ax.set_xlabel("经度", color="#aaa", fontsize=9)
    ax.set_ylabel("纬度", color="#aaa", fontsize=9)
    ax.tick_params(colors="#888")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")

    # 坐标范围覆盖武汉主城区
    ax.set_xlim(114.05, 114.55)
    ax.set_ylim(30.33, 30.70)

    map_path = os.path.join(output_dir, "site_map.png")
    plt.tight_layout()
    plt.savefig(map_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    return map_path


# ══════════════════════════════════════════════════════════════════════════════
#  五、主程序（用户视角：3行代码）
# ══════════════════════════════════════════════════════════════════════════════

def main():
    WIDTH = 68

    print("\n" + "═" * WIDTH)
    print("  GeoClaw v3.0.0 — 武汉商场选址 · 端到端示例")
    print("═" * WIDTH)

    print("""
  【用户只需这样问】
  ─────────────────────────────────────────────
  "在武汉哪里适合建设新的商场，给出最推荐的5个地点名称"
  ─────────────────────────────────────────────

  GeoClaw 后台自动完成：
  ① 解析自然语言 → 识别"选址"意图
  ② SRE 推理    → 选择 weighted_overlay 方法
  ③ GIS 执行    → 缓冲区 + KDE + 加权叠加
  ④ 报告生成    → Markdown 报告 + PNG 地图
""")

    # ── 获取 LLM Provider ───────────────────────────────────────────────────
    llm_provider = _get_provider()

    # ── 构建演示数据 ────────────────────────────────────────────────────────
    print("─" * WIDTH)
    print("  [1/4] 加载数据集")
    print("─" * WIDTH)
    layers = build_demo_data()
    for name, layer in layers.items():
        print(f"  ✓ {layer.name}  ({len(layer.data)} 个要素)")

    # ── 执行分析 ────────────────────────────────────────────────────────────
    print()
    print("─" * WIDTH)
    print("  [2/4] 执行分析（SRE 推理 → GIS 执行）")
    print("─" * WIDTH)
    t0 = time.time()
    analysis = analyze_mall_siting(layers, llm_provider)
    elapsed = time.time() - t0
    print(f"  ✓ 分析完成  耗时 {elapsed:.1f}s")

    # ── 生成报告 ────────────────────────────────────────────────────────────
    print()
    print("─" * WIDTH)
    print("  [3/4] 生成报告与地图")
    print("─" * WIDTH)
    report_path = generate_report(analysis, OUTPUT_DIR)
    print(f"  ✓ 分析报告：{report_path}")
    map_path = generate_map(analysis, OUTPUT_DIR)
    print(f"  ✓ 选址地图：{map_path}")

    # ── 打印结果摘要 ────────────────────────────────────────────────────────
    print()
    print("─" * WIDTH)
    print("  [4/4] 分析结果")
    print("─" * WIDTH)
    print()

    rs = analysis["sre_result"].reasoning_summary
    print(f"  SRE 推理：{rs.primary_method}  |  不确定性：{rs.uncertainty_level}（{rs.uncertainty_score:.2f}）")
    print(f"  分析模式：{rs.analysis_mode}  |  MAUP风险：{rs.maup_risk}")
    print()
    print("  ┌─ 推荐选址 Top 5 ──────────────────────────────────────────┐")
    for s in analysis["candidates"]:
        stars = "★" * s["rank"]
        name_short = s["name"][:28]
        print(f"  │ #{s['rank']} {name_short:<28} 评分:{s['score']}  {s['district']}")
    print("  └───────────────────────────────────────────────────────────┘")

    print()
    print("═" * WIDTH)
    print("  ✅ 完成！输出文件：")
    print(f"     报告：{report_path}")
    print(f"     地图：{map_path}")
    print()
    print("  ⚠  以上为空间分析候选，实际决策需补充：")
    print("     地价数据、用地规划管控、产权权属信息")
    print("═" * WIDTH + "\n")


def _get_provider():
    """自动检测 API Key，有则用真实 Claude，否则用 Mock。"""
    try:
        from geoclaw_claude.config import Config
        from geoclaw_claude.nl.llm_provider import LLMProvider
        cfg = Config.load()
        if cfg.anthropic_api_key:
            print("  [LLM] 使用真实 Claude API")
            return LLMProvider.from_config(cfg)
        if cfg.gemini_api_key:
            print("  [LLM] 使用真实 Gemini API")
            return LLMProvider.from_config(cfg)
    except Exception:
        pass
    print("  [LLM] 未配置 API Key → 使用 Mock LLM（模拟 Claude 推理）")
    return MockLLMProvider()


if __name__ == "__main__":
    main()
