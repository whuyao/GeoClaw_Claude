# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude/analysis/mobility/visualization.py
===================================================
人类移动性数据可视化

提供:
  - plot_mobility_layers  分层叠加地图（pf/sp/triplegs/locations）
  - plot_modal_split      交通方式饼图/条形图
  - plot_trajectory       单用户轨迹动态图
  - plot_activity_heatmap 活动时间热力图（星期×小时）
  - plot_mobility_metrics 移动性指标分布图

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches


# 颜色方案（UrbanComp Lab 风格）
COLORS = {
    "positionfixes": "#aab7d4",
    "staypoints":    "#e07b39",
    "triplegs":      "#3a86ff",
    "locations":     "#e63946",
    "home":          "#2dc653",
    "work":          "#ffd60a",
    "walk":          "#06d6a0",
    "bike":          "#118ab2",
    "car":           "#ef476f",
    "train":         "#ffd166",
    "unknown":       "#adb5bd",
}


def plot_mobility_layers(
    hierarchy: dict,
    *,
    user_id: Optional[Union[int, str]] = None,
    show_positionfixes: bool = False,
    show_staypoints:    bool = True,
    show_triplegs:      bool = True,
    show_locations:     bool = True,
    title: str = "移动性数据层级地图",
    figsize: tuple = (12, 10),
    save_path: Optional[Union[str, Path]] = None,
) -> plt.Figure:
    """
    绘制移动性数据的分层叠加地图。

    Args:
        hierarchy          : generate_full_hierarchy() 的返回值
        user_id            : 筛选特定用户（None 则显示所有）
        show_positionfixes : 是否显示原始 GPS 点
        show_staypoints    : 是否显示停留点
        show_triplegs      : 是否显示出行段
        show_locations     : 是否显示重要地点
        title              : 图标题
        figsize            : 图尺寸
        save_path          : 保存路径（None 则不保存）

    Returns:
        matplotlib Figure
    """
    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    legend_handles = []

    def _filter(gdf):
        if user_id is not None and len(gdf) and "user_id" in gdf.columns:
            return gdf[gdf["user_id"] == user_id]
        return gdf

    # GPS 轨迹点
    if show_positionfixes and "positionfixes" in hierarchy:
        pfs = _filter(hierarchy["positionfixes"])
        if len(pfs):
            pfs.plot(ax=ax, color=COLORS["positionfixes"], markersize=1,
                     alpha=0.3, zorder=1)
            legend_handles.append(
                mpatches.Patch(color=COLORS["positionfixes"],
                               label=f"GPS 轨迹点 ({len(pfs)})"))

    # 出行段
    if show_triplegs and "triplegs" in hierarchy:
        tpls = _filter(hierarchy["triplegs"])
        if len(tpls) and hasattr(tpls, "geometry"):
            # 按交通方式上色
            if "mode" in tpls.columns:
                for mode, grp in tpls.groupby("mode"):
                    color = COLORS.get(mode, COLORS["unknown"])
                    grp.plot(ax=ax, color=color, linewidth=0.8, alpha=0.7, zorder=2)
                    legend_handles.append(
                        mpatches.Patch(color=color, label=f"{mode} ({len(grp)})"))
            else:
                tpls.plot(ax=ax, color=COLORS["triplegs"], linewidth=0.8,
                          alpha=0.6, zorder=2)
                legend_handles.append(
                    mpatches.Patch(color=COLORS["triplegs"],
                                   label=f"出行段 ({len(tpls)})"))

    # 停留点
    if show_staypoints and "staypoints" in hierarchy:
        sp = _filter(hierarchy["staypoints"])
        if len(sp):
            sp.plot(ax=ax, color=COLORS["staypoints"], markersize=6,
                    alpha=0.8, zorder=3, edgecolors="white", linewidth=0.3)
            legend_handles.append(
                mpatches.Patch(color=COLORS["staypoints"],
                               label=f"停留点 ({len(sp)})"))

    # 重要地点
    if show_locations and "locations" in hierarchy:
        locs = _filter(hierarchy["locations"])
        if len(locs):
            purpose_col = "purpose" if "purpose" in locs.columns else None
            if purpose_col:
                for purpose, grp in locs.groupby(purpose_col, dropna=False):
                    purpose = purpose if pd.notna(purpose) else "other"
                    color = COLORS.get(purpose, COLORS["locations"])
                    grp.plot(ax=ax, color=color, markersize=14, zorder=5,
                             edgecolors="white", linewidth=1.5)
                    legend_handles.append(
                        mpatches.Patch(color=color,
                                       label=f"地点:{purpose} ({len(grp)})"))
            else:
                locs.plot(ax=ax, color=COLORS["locations"], markersize=14,
                          zorder=5, edgecolors="white", linewidth=1.5)
                legend_handles.append(
                    mpatches.Patch(color=COLORS["locations"],
                                   label=f"重要地点 ({len(locs)})"))

    ax.set_title(title, color="white", fontsize=14, pad=12)
    ax.tick_params(colors="gray")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")

    if legend_handles:
        ax.legend(handles=legend_handles, loc="lower left",
                  facecolor="#16213e", edgecolor="#444", labelcolor="white",
                  fontsize=9)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        print(f"[Mobility] 地图已保存: {save_path}")

    return fig


def plot_modal_split(
    triplegs: gpd.GeoDataFrame,
    *,
    metric: str = "count",
    title: str = "出行方式构成",
    figsize: tuple = (10, 5),
    save_path: Optional[Union[str, Path]] = None,
) -> plt.Figure:
    """
    绘制出行方式构成图（饼图 + 条形图并排）。

    Args:
        triplegs : 含 mode 列的出行段
        metric   : 统计口径（'count' / 'duration' / 'distance'）
        title    : 图标题
        figsize  : 图尺寸
        save_path: 保存路径

    Returns:
        matplotlib Figure
    """
    if "mode" not in triplegs.columns:
        raise ValueError("triplegs 缺少 mode 列，请先运行 predict_transport_mode()")

    if metric == "count":
        data = triplegs["mode"].value_counts()
        unit = "次"
    elif metric == "duration":
        if "duration" not in triplegs.columns:
            triplegs = triplegs.copy()
            triplegs["duration"] = (
                (triplegs["finished_at"] - triplegs["started_at"])
                .dt.total_seconds() / 60
            )
        data = triplegs.groupby("mode")["duration"].sum().sort_values(ascending=False)
        unit = "分钟"
    else:
        data = triplegs["mode"].value_counts()
        unit = "次"

    colors = [COLORS.get(m, COLORS["unknown"]) for m in data.index]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, facecolor="#1a1a2e")
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")

    # 饼图
    wedges, texts, autotexts = ax1.pie(
        data.values, labels=data.index, colors=colors,
        autopct="%1.1f%%", startangle=90,
        textprops={"color": "white", "fontsize": 10},
        pctdistance=0.8,
    )
    for at in autotexts:
        at.set_fontsize(9)
    ax1.set_title("占比", color="white", fontsize=12)

    # 条形图
    bars = ax2.barh(data.index, data.values, color=colors, edgecolor="#333")
    ax2.set_xlabel(unit, color="gray")
    ax2.set_title(f"数量（{unit}）", color="white", fontsize=12)
    ax2.tick_params(colors="gray")
    ax2.set_facecolor("#1a1a2e")
    for spine in ax2.spines.values():
        spine.set_edgecolor("#333355")
    for bar, val in zip(bars, data.values):
        ax2.text(val * 1.01, bar.get_y() + bar.get_height() / 2,
                 str(int(val)), va="center", color="white", fontsize=9)

    fig.suptitle(title, color="white", fontsize=14, y=1.02)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())

    return fig


def plot_activity_heatmap(
    staypoints: gpd.GeoDataFrame,
    *,
    user_id: Optional[Union[int, str]] = None,
    title: str = "活动时间热力图（星期 × 小时）",
    figsize: tuple = (14, 5),
    save_path: Optional[Union[str, Path]] = None,
) -> plt.Figure:
    """
    绘制活动时间热力图：横轴小时（0-23）× 纵轴星期（Mon-Sun）。

    颜色越深 → 该时段停留越频繁。

    Args:
        staypoints: 含 started_at 的停留点
        user_id   : 筛选特定用户
        title     : 图标题
        figsize   : 图尺寸
        save_path : 保存路径

    Returns:
        matplotlib Figure
    """
    sp = staypoints.copy()
    if user_id is not None:
        sp = sp[sp["user_id"] == user_id]

    if "started_at" not in sp.columns:
        raise ValueError("staypoints 缺少 started_at 列")

    sp["hour"]    = pd.to_datetime(sp["started_at"]).dt.hour
    sp["weekday"] = pd.to_datetime(sp["started_at"]).dt.dayofweek

    pivot = sp.groupby(["weekday", "hour"]).size().unstack(fill_value=0)
    # 补全所有小时
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]

    # 补全所有星期
    for d in range(7):
        if d not in pivot.index:
            pivot.loc[d] = 0
    pivot = pivot.sort_index()

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd",
                    interpolation="nearest")
    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24), color="gray", fontsize=8)
    ax.set_yticks(range(7))
    ax.set_yticklabels(weekday_labels, color="gray")
    ax.set_xlabel("小时（Hour）", color="gray")
    ax.set_ylabel("星期", color="gray")
    ax.set_title(title, color="white", fontsize=13, pad=10)

    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(colors="gray")
    cbar.set_label("停留次数", color="gray")

    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())

    return fig


def plot_mobility_metrics(
    summary: dict,
    *,
    title: str = "移动性指标摘要",
    figsize: tuple = (12, 7),
    save_path: Optional[Union[str, Path]] = None,
) -> plt.Figure:
    """
    绘制移动性综合指标仪表盘。

    展示: 回转半径分布、跳跃距离分布、数据质量、出行方式等。

    Args:
        summary  : mobility_summary() 的返回值
        title    : 总标题
        figsize  : 图尺寸
        save_path: 保存路径

    Returns:
        matplotlib Figure
    """
    fig = plt.figure(figsize=figsize, facecolor="#1a1a2e")
    fig.suptitle(title, color="white", fontsize=15, y=0.98)

    # 基础统计卡片
    ax_stats = fig.add_axes([0.02, 0.55, 0.28, 0.38])
    ax_stats.set_facecolor("#16213e")
    ax_stats.axis("off")

    stats_text = [
        ("用户数",   str(summary.get("n_users", "—"))),
        ("GPS点",   f"{summary.get('n_positionfixes', '—'):,}"),
        ("停留点",   f"{summary.get('n_staypoints', '—'):,}"),
        ("出行段",   f"{summary.get('n_triplegs', '—'):,}"),
        ("重要地点", f"{summary.get('n_locations', '—'):,}"),
    ]
    y = 0.90
    ax_stats.text(0.5, 1.0, "数据概览", color="white", fontsize=11,
                  ha="center", va="top", transform=ax_stats.transAxes,
                  fontweight="bold")
    for label, val in stats_text:
        ax_stats.text(0.1, y, label, color="#adb5bd", fontsize=10,
                      transform=ax_stats.transAxes)
        ax_stats.text(0.9, y, val, color="#e07b39", fontsize=10,
                      ha="right", transform=ax_stats.transAxes,
                      fontweight="bold")
        y -= 0.18

    # 回转半径
    if "radius_of_gyration_m" in summary:
        ax_rog = fig.add_axes([0.35, 0.55, 0.28, 0.38])
        ax_rog.set_facecolor("#16213e")
        rog = summary["radius_of_gyration_m"]
        bars = ax_rog.bar(["均值", "中位数", "最大值"],
                           [rog["mean"] / 1000, rog["median"] / 1000,
                            rog["max"] / 1000],
                           color=["#3a86ff", "#06d6a0", "#ef476f"],
                           edgecolor="#333", width=0.5)
        ax_rog.set_title("回转半径（km）", color="white", fontsize=11)
        ax_rog.tick_params(colors="gray")
        for spine in ax_rog.spines.values():
            spine.set_edgecolor("#333355")
        for bar in bars:
            ax_rog.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.1,
                        f"{bar.get_height():.1f}", ha="center",
                        color="white", fontsize=9)

    # 出行方式
    if "modal_split" in summary:
        ax_ms = fig.add_axes([0.68, 0.55, 0.28, 0.38])
        ax_ms.set_facecolor("#16213e")
        ms = summary["modal_split"]
        modes  = list(ms.keys())
        values = [ms[m] * 100 for m in modes]
        colors = [COLORS.get(m, COLORS["unknown"]) for m in modes]
        ax_ms.pie(values, labels=modes, colors=colors,
                  autopct="%1.0f%%", startangle=90,
                  textprops={"color": "white", "fontsize": 9})
        ax_ms.set_title("出行方式构成", color="white", fontsize=11)

    # 跳跃距离
    if "jump_length_m" in summary:
        ax_jl = fig.add_axes([0.02, 0.06, 0.45, 0.38])
        ax_jl.set_facecolor("#16213e")
        jl = summary["jump_length_m"]
        labels = ["均值", "中位数", "P90"]
        values = [jl["mean"] / 1000, jl["median"] / 1000, jl["p90"] / 1000]
        ax_jl.barh(labels, values, color=["#3a86ff", "#06d6a0", "#ffd166"],
                   edgecolor="#333")
        ax_jl.set_title("跳跃距离（km）", color="white", fontsize=11)
        ax_jl.tick_params(colors="gray")
        for spine in ax_jl.spines.values():
            spine.set_edgecolor("#333355")
        for i, (v, l) in enumerate(zip(values, labels)):
            ax_jl.text(v + 0.02, i, f"{v:.1f}", va="center",
                       color="white", fontsize=9)

    # 数据质量
    if "tracking_quality_mean" in summary:
        ax_tq = fig.add_axes([0.55, 0.06, 0.40, 0.38])
        ax_tq.set_facecolor("#16213e")
        tq = summary["tracking_quality_mean"]
        theta = np.linspace(0, 2 * np.pi, 100)
        # 仪表盘风格
        fill_angle = tq * 2 * np.pi
        ax_tq.fill_between(np.linspace(0, fill_angle, 100),
                           0, 1, color="#06d6a0", alpha=0.8)
        ax_tq.fill_between(np.linspace(fill_angle, 2 * np.pi, 100),
                           0, 1, color="#333355", alpha=0.5)
        ax_tq.set_xlim(0, 2 * np.pi)
        ax_tq.set_ylim(0, 1.2)
        ax_tq.text(np.pi, 0.5, f"{tq:.1%}",
                   ha="center", va="center", color="white",
                   fontsize=18, fontweight="bold")
        ax_tq.set_title("轨迹覆盖率", color="white", fontsize=11)
        ax_tq.axis("off")

    plt.subplots_adjust(hspace=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())

    return fig
