# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude/analysis/mobility/visualization.py
===================================================
Human mobility data visualization (English labels)
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# UrbanComp Lab dark theme palette
COLORS = {
    "positionfixes": "#aab7d4",
    "staypoints":    "#e07b39",
    "triplegs":      "#3a86ff",
    "locations":     "#e63946",
    "home":          "#2dc653",
    "work":          "#ffd60a",
    "slow_mobility":      "#06d6a0",
    "motorized_mobility": "#ef476f",
    "fast_mobility":      "#ffd166",
    "walk":    "#06d6a0",
    "bike":    "#118ab2",
    "car":     "#ef476f",
    "train":   "#ffd166",
    "unknown": "#adb5bd",
}

MODE_LABELS = {
    "slow_mobility":      "Slow Mobility",
    "motorized_mobility": "Motorized",
    "fast_mobility":      "Fast Mobility",
    "walk":  "Walk",
    "bike":  "Bike",
    "car":   "Car",
    "train": "Train",
}

def _setup_dark_ax(ax):
    ax.set_facecolor("#16213e")
    ax.tick_params(colors="#888")
    for sp in ax.spines.values():
        sp.set_edgecolor("#333355")

def plot_mobility_layers(
    hierarchy: dict,
    *,
    user_id=None,
    show_positionfixes: bool = False,
    show_staypoints: bool = True,
    show_triplegs: bool = True,
    show_locations: bool = True,
    title: str = "Mobility Data Layers Map",
    figsize: tuple = (12, 10),
    save_path=None,
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    legend_handles = []

    def _filter(gdf):
        if user_id is not None and len(gdf) and "user_id" in gdf.columns:
            return gdf[gdf["user_id"] == user_id]
        return gdf

    if show_positionfixes and "positionfixes" in hierarchy:
        pfs = _filter(hierarchy["positionfixes"])
        if len(pfs):
            pfs.plot(ax=ax, color=COLORS["positionfixes"], markersize=1, alpha=0.3, zorder=1)
            legend_handles.append(mpatches.Patch(color=COLORS["positionfixes"],
                                                  label=f"GPS Points ({len(pfs):,})"))

    if show_triplegs and "triplegs" in hierarchy:
        tpls = _filter(hierarchy["triplegs"])
        if len(tpls):
            if "mode" in tpls.columns:
                for mode, grp in tpls.groupby("mode"):
                    c = COLORS.get(mode, COLORS["unknown"])
                    lbl = MODE_LABELS.get(mode, mode)
                    grp.plot(ax=ax, color=c, linewidth=0.9, alpha=0.75, zorder=2)
                    legend_handles.append(mpatches.Patch(color=c,
                                                          label=f"{lbl} ({len(grp)})"))
            else:
                tpls.plot(ax=ax, color=COLORS["triplegs"], linewidth=0.8, alpha=0.6, zorder=2)
                legend_handles.append(mpatches.Patch(color=COLORS["triplegs"],
                                                      label=f"Triplegs ({len(tpls)})"))

    if show_staypoints and "staypoints" in hierarchy:
        sp = _filter(hierarchy["staypoints"])
        if len(sp):
            sp.plot(ax=ax, color=COLORS["staypoints"], markersize=6, alpha=0.85,
                    zorder=3, edgecolors="white", linewidth=0.3)
            legend_handles.append(mpatches.Patch(color=COLORS["staypoints"],
                                                  label=f"Staypoints ({len(sp)})"))

    if show_locations and "locations" in hierarchy:
        locs = _filter(hierarchy["locations"])
        if len(locs):
            purpose_col = "purpose" if "purpose" in locs.columns else None
            if purpose_col:
                for purpose, grp in locs.groupby(purpose_col, dropna=False):
                    p = str(purpose) if pd.notna(purpose) else "Other"
                    c = COLORS.get(p.lower(), COLORS["locations"])
                    grp.plot(ax=ax, color=c, markersize=14, zorder=5,
                             edgecolors="white", linewidth=1.5)
                    legend_handles.append(mpatches.Patch(color=c,
                                                          label=f"Location:{p} ({len(grp)})"))
            else:
                locs.plot(ax=ax, color=COLORS["locations"], markersize=14,
                          zorder=5, edgecolors="white", linewidth=1.5)
                legend_handles.append(mpatches.Patch(color=COLORS["locations"],
                                                      label=f"Locations ({len(locs)})"))

    ax.set_title(title, color="white", fontsize=14, pad=12)
    ax.tick_params(colors="gray")
    ax.set_xlabel("Longitude", color="gray", fontsize=9)
    ax.set_ylabel("Latitude", color="gray", fontsize=9)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333355")
    if legend_handles:
        ax.legend(handles=legend_handles, loc="lower left",
                  facecolor="#16213e", edgecolor="#444",
                  labelcolor="white", fontsize=9)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(f"[Mobility] Saved: {save_path}")
    return fig


def plot_modal_split(
    triplegs: gpd.GeoDataFrame,
    *,
    metric: str = "count",
    title: str = "Modal Split",
    figsize: tuple = (10, 5),
    save_path=None,
) -> plt.Figure:
    if "mode" not in triplegs.columns:
        raise ValueError("triplegs missing 'mode' column — run predict_transport_mode() first")

    if metric == "duration" and "duration" not in triplegs.columns:
        tpls = triplegs.copy()
        tpls["duration"] = ((tpls["finished_at"] - tpls["started_at"])
                            .dt.total_seconds() / 60)
        data = tpls.groupby("mode")["duration"].sum().sort_values(ascending=False)
        unit = "min"
    else:
        data = triplegs["mode"].value_counts()
        unit = "trips"

    labels = [MODE_LABELS.get(m, m) for m in data.index]
    colors = [COLORS.get(m, COLORS["unknown"]) for m in data.index]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, facecolor="#1a1a2e")
    for ax in (ax1, ax2):
        _setup_dark_ax(ax)

    # Pie
    wedges, texts, autotexts = ax1.pie(
        data.values, labels=labels, colors=colors,
        autopct="%1.1f%%", startangle=90,
        textprops={"color": "white", "fontsize": 10}, pctdistance=0.78,
    )
    for at in autotexts:
        at.set_fontsize(9)
    ax1.set_title("Share (%)", color="white", fontsize=12)

    # Bar
    bars = ax2.barh(labels, data.values, color=colors, edgecolor="#333")
    ax2.set_xlabel(unit, color="gray")
    ax2.set_title(f"Count ({unit})", color="white", fontsize=12)
    ax2.tick_params(colors="gray")
    for bar, val in zip(bars, data.values):
        ax2.text(val * 1.01, bar.get_y() + bar.get_height() / 2,
                 str(int(val)), va="center", color="white", fontsize=9)

    fig.suptitle(title, color="white", fontsize=14, y=1.01)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    return fig


def plot_activity_heatmap(
    staypoints: gpd.GeoDataFrame,
    *,
    user_id=None,
    title: str = "Activity Time Heatmap (Weekday × Hour)",
    figsize: tuple = (14, 5),
    save_path=None,
) -> plt.Figure:
    sp = staypoints.copy()
    if user_id is not None:
        sp = sp[sp["user_id"] == user_id]
    if "started_at" not in sp.columns:
        raise ValueError("staypoints missing 'started_at' column")

    sp["hour"]    = pd.to_datetime(sp["started_at"]).dt.hour
    sp["weekday"] = pd.to_datetime(sp["started_at"]).dt.dayofweek

    pivot = sp.groupby(["weekday", "hour"]).size().unstack(fill_value=0)
    for h in range(24):
        if h not in pivot.columns: pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]
    for d in range(7):
        if d not in pivot.index: pivot.loc[d] = 0
    pivot = pivot.sort_index()

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24), color="gray", fontsize=8)
    ax.set_yticks(range(7))
    ax.set_yticklabels(weekday_labels, color="gray")
    ax.set_xlabel("Hour of Day", color="gray")
    ax.set_ylabel("Weekday", color="gray")
    ax.set_title(title, color="white", fontsize=13, pad=10)
    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(colors="gray")
    cbar.set_label("Staypoint Count", color="gray")
    for sp_ in ax.spines.values():
        sp_.set_edgecolor("#333355")
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    return fig


def plot_mobility_metrics(
    summary: dict,
    *,
    title: str = "Mobility Metrics Dashboard",
    figsize: tuple = (12, 7),
    save_path=None,
) -> plt.Figure:
    fig = plt.figure(figsize=figsize, facecolor="#1a1a2e")
    fig.suptitle(title, color="white", fontsize=15, y=0.98)

    # ── Stats card ────────────────────────────────────────────────────────────
    ax_stats = fig.add_axes([0.02, 0.55, 0.28, 0.38])
    ax_stats.set_facecolor("#16213e")
    ax_stats.axis("off")
    stats = [
        ("Users",       str(summary.get("n_users", "—"))),
        ("GPS Points",  f"{summary.get('n_positionfixes', '—'):,}"),
        ("Staypoints",  f"{summary.get('n_staypoints', '—'):,}"),
        ("Triplegs",    f"{summary.get('n_triplegs', '—'):,}"),
        ("Locations",   f"{summary.get('n_locations', '—'):,}"),
    ]
    ax_stats.text(0.5, 1.0, "Dataset Overview", color="white", fontsize=11,
                  ha="center", va="top", transform=ax_stats.transAxes, fontweight="bold")
    y = 0.88
    for label, val in stats:
        ax_stats.text(0.08, y, label, color="#adb5bd", fontsize=10, transform=ax_stats.transAxes)
        ax_stats.text(0.92, y, val, color="#e07b39", fontsize=10, ha="right",
                      transform=ax_stats.transAxes, fontweight="bold")
        y -= 0.18

    # ── Radius of gyration ────────────────────────────────────────────────────
    if "radius_of_gyration_m" in summary:
        ax_rog = fig.add_axes([0.35, 0.55, 0.28, 0.38])
        ax_rog.set_facecolor("#16213e")
        rog = summary["radius_of_gyration_m"]
        vals = [rog["mean"]/1000, rog["median"]/1000, rog["max"]/1000]
        bars = ax_rog.bar(["Mean", "Median", "Max"], vals,
                           color=["#3a86ff", "#06d6a0", "#ef476f"],
                           edgecolor="#333", width=0.5)
        ax_rog.set_title("Radius of Gyration (km)", color="white", fontsize=11)
        ax_rog.tick_params(colors="gray")
        for sp_ in ax_rog.spines.values(): sp_.set_edgecolor("#333355")
        for bar in bars:
            ax_rog.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                        f"{bar.get_height():.1f}", ha="center", color="white", fontsize=9)

    # ── Modal split ───────────────────────────────────────────────────────────
    if "modal_split" in summary:
        ax_ms = fig.add_axes([0.68, 0.55, 0.28, 0.38])
        ax_ms.set_facecolor("#16213e")
        ms = summary["modal_split"]
        modes  = list(ms.keys())
        values = [ms[m]*100 for m in modes]
        labels = [MODE_LABELS.get(m, m) for m in modes]
        colors = [COLORS.get(m, COLORS["unknown"]) for m in modes]
        ax_ms.pie(values, labels=labels, colors=colors, autopct="%1.0f%%", startangle=90,
                  textprops={"color": "white", "fontsize": 9})
        ax_ms.set_title("Modal Split", color="white", fontsize=11)

    # ── Jump length ───────────────────────────────────────────────────────────
    if "jump_length_m" in summary:
        ax_jl = fig.add_axes([0.02, 0.06, 0.45, 0.38])
        ax_jl.set_facecolor("#16213e")
        jl = summary["jump_length_m"]
        vals   = [jl["mean"]/1000, jl["median"]/1000, jl["p90"]/1000]
        labels = ["Mean", "Median", "P90"]
        ax_jl.barh(labels, vals, color=["#3a86ff", "#06d6a0", "#ffd166"], edgecolor="#333")
        ax_jl.set_title("Jump Length (km)", color="white", fontsize=11)
        ax_jl.tick_params(colors="gray")
        for sp_ in ax_jl.spines.values(): sp_.set_edgecolor("#333355")
        for i, v in enumerate(vals):
            ax_jl.text(v + 0.02, i, f"{v:.2f}", va="center", color="white", fontsize=9)

    # ── Tracking quality gauge ────────────────────────────────────────────────
    if "tracking_quality_mean" in summary:
        ax_tq = fig.add_axes([0.55, 0.06, 0.40, 0.38])
        ax_tq.set_facecolor("#16213e")
        tq = summary["tracking_quality_mean"]
        theta = np.linspace(0, np.pi, 200)
        # Background arc
        ax_tq.plot(np.cos(theta), np.sin(theta), color="#333355", lw=18, solid_capstyle="round")
        # Fill arc
        fill_theta = np.linspace(0, np.pi * tq, 200)
        ax_tq.plot(np.cos(fill_theta), np.sin(fill_theta),
                   color="#06d6a0", lw=18, solid_capstyle="round")
        ax_tq.text(0, 0.15, f"{tq:.1%}", ha="center", va="center",
                   color="white", fontsize=20, fontweight="bold")
        ax_tq.text(0, -0.25, "Tracking Quality", ha="center", va="center",
                   color="#adb5bd", fontsize=10)
        ax_tq.set_xlim(-1.3, 1.3)
        ax_tq.set_ylim(-0.5, 1.2)
        ax_tq.axis("off")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    return fig


COLORS_EXPORT = COLORS   # backward compat alias
