"""
geoclaw_claude/cartography/map_composer.py
=====================================
专业制图引擎 — MapComposer

提供多图层、多主题的高质量静态地图生成功能，参考 QGIS Print Layout 设计。

支持:
  - 4 种内置主题 (urban / light / satellite / blueprint)
  - 多图层叠加 (点/线/面，支持 Choropleth 分级设色)
  - KDE 密度热力图叠加
  - 比例尺 (matplotlib-scalebar)
  - 指北针
  - 图例自动生成
  - 中文字体支持 (Noto Sans CJK)

────────────────────────────────────────────────────────
TODO (高优先级):
  - [ ] 添加 add_labels(layer, column) — 图上标注要素名称
        需要处理标注碰撞（使用 adjustText 库）
  - [ ] 添加 add_inset_map(bbox) — 区位示意图（右下角小地图）
  - [ ] Choropleth: 自动生成分类色带图例（颜色框 + 值范围标注）

TODO (中优先级):
  - [ ] 添加 add_grid(interval) — 经纬网格线（带坐标标注）
  - [ ] 添加 set_extent(bbox) — 手动设置地图显示范围
  - [ ] 支持 contextily basemap 底图 (OSM/卫星底图叠加)
        示例: import contextily; contextily.add_basemap(ax)
  - [ ] 添加多图幅布局 (subplots) 支持并排对比地图

TODO (低优先级):
  - [ ] 输出 SVG 格式（可缩放矢量图）
  - [ ] 支持 A4/A3 图纸尺寸模板
  - [ ] 添加地图边框 (neatline) 和图名区域
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import warnings
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # 非交互后端，适合服务器环境
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import geopandas as gpd

from geoclaw_claude.core.layer import GeoLayer

# ── CJK 字体初始化 ────────────────────────────────────────────────────────────
import matplotlib.font_manager as _fm
_fm._load_fontmanager(try_read_cache=False)
_CJK_FONTS = [f.name for f in _fm.fontManager.ttflist
              if "CJK" in f.name or "WenQuanYi" in f.name or "Noto" in f.name]
# 优先使用 Noto Sans CJK SC（简体中文），其次 WenQuanYi
_DEFAULT_FONT = next((f for f in _CJK_FONTS if "SC" in f or "Simplified" in f), None) \
             or (_CJK_FONTS[0] if _CJK_FONTS else None)

# 比例尺库（可选）
try:
    from matplotlib_scalebar.scalebar import ScaleBar
    _HAS_SCALEBAR = True
except ImportError:
    _HAS_SCALEBAR = False
    # TODO: 实现一个不依赖 matplotlib-scalebar 的简易比例尺替代方案


# ── 内置主题配置 ──────────────────────────────────────────────────────────────
#
# 每个主题定义背景色、水体色、道路色、公园色、POI 色、网格色。
# 新增主题时在此字典添加条目，render() 会自动应用。
#
# TODO: 支持从 YAML/JSON 文件加载自定义主题

PALETTES = {
    "urban": {
        # 暗色城市风格 — 适合展示城市基础设施、夜景感
        "background": "#1a1a2e",
        "water":      "#16213e",
        "road":       "#e94560",
        "park":       "#0f3460",
        "poi":        "#f5a623",
        "grid":       "#2a2a4a",
    },
    "light": {
        # 浅色简洁风格 — 适合专题地图，接近传统纸质地图
        "background": "#f8f4f0",
        "water":      "#b8d4e8",
        "road":       "#d4b896",
        "park":       "#c8e6c9",
        "poi":        "#e53935",
        "grid":       "#e0e0e0",
    },
    "satellite": {
        # 卫星图风格 — 适合遥感/影像相关主题
        "background": "#1b2631",
        "water":      "#1a5276",
        "road":       "#f0b27a",
        "park":       "#1e8449",
        "poi":        "#f1c40f",
        "grid":       "#2c3e50",
    },
    "blueprint": {
        # 蓝图工程风格 — 适合规划图、基础设施分析
        "background": "#0d2137",
        "water":      "#1565c0",
        "road":       "#90caf9",
        "park":       "#1b5e20",
        "poi":        "#ff6f00",
        "grid":       "#1a3a5c",
    },
}


class MapComposer:
    """
    专业地图制图引擎。

    使用流式 API 逐层添加数据，最后调用 render() 输出文件。

    使用示例:
        composer = MapComposer(
            title="武汉医院分布",
            subtitle="数据来源: OpenStreetMap",
            palette="light",
        )
        composer.add_layer(boundary, role="boundary", label="城市边界")
        composer.add_layer(hospitals, role="hospital", label="医院", markersize=6)
        composer.render("output/map.png")
    """

    def __init__(
        self,
        figsize: tuple = (16, 12),
        dpi: int = 150,
        palette: str = "light",
        title: str = "",
        subtitle: str = "",
    ):
        """
        Args:
            figsize : 图幅尺寸（英寸），默认 (16, 12)
            dpi     : 分辨率，150 适合屏幕展示，300 适合印刷
            palette : 主题名称，支持 'urban' 'light' 'satellite' 'blueprint'
            title   : 主标题
            subtitle: 副标题（显示在主标题下方）
        """
        self.figsize   = figsize
        self.dpi       = dpi
        self.palette   = PALETTES.get(palette, PALETTES["light"])
        self.title     = title
        self.subtitle  = subtitle
        self._layers:  list = []   # 图层规格列表
        self._kde_spec: Optional[dict] = None  # KDE 热力图规格

    def add_layer(
        self,
        layer: GeoLayer,
        color: Optional[str] = None,
        edge_color: Optional[str] = None,
        alpha: float = 0.85,
        linewidth: float = 0.8,
        markersize: float = 4,
        zorder: int = 2,
        label: Optional[str] = None,
        column: Optional[str] = None,  # Choropleth 字段名
        cmap: str = "YlOrRd",
        scheme: str = "quantiles",
        k: int = 5,
        marker: str = "o",
        role: str = "default",
    ) -> "MapComposer":
        """
        添加一个图层到制图队列。

        Args:
            layer     : GeoLayer
            color     : 填充色/线色/点色（None 时按 role 自动配色）
            edge_color: 边框色
            alpha     : 透明度 0~1
            linewidth : 线宽（面边框/线要素）
            markersize: 点符号大小
            zorder    : 渲染层次（数值越大越靠前）
            label     : 图例标签（默认使用 layer.name）
            column    : Choropleth 分级设色字段名（点/面均支持）
            cmap      : Choropleth 色带名称
            scheme    : Choropleth 分级方案 'quantiles' | 'equal_interval' | 'jenks'
            k         : Choropleth 分级数
            marker    : 点符号形状 'o' '^' 's' 'D' 等
            role      : 预设角色自动配色，支持:
                        'boundary' 'water' 'road' 'park'
                        'hospital' 'university' 'metro' 'poi'

        Returns:
            self（支持链式调用）

        TODO:
            - [ ] 支持 size_column 按属性值控制点符号大小（比例符号）
            - [ ] 添加 hatch 参数为面要素设置阴影线填充
        """
        # 按 role 自动配色
        role_presets = {
            "boundary":  (None,                    "#888888"),
            "water":     (self.palette["water"],   "#3d85c8"),
            "road":      (self.palette["road"],    None),
            "park":      (self.palette["park"],    "#2e7d32"),
            "hospital":  ("#e53935",               "#b71c1c"),
            "university":("#7b1fa2",               "#4a148c"),
            "metro":     ("#f57f17",               "#e65100"),
            "poi":       (self.palette["poi"],     None),
        }
        if role in role_presets and color is None:
            auto_c, auto_e = role_presets[role]
            color      = auto_c
            edge_color = edge_color or auto_e

        self._layers.append({
            "layer": layer, "color": color, "edge_color": edge_color,
            "alpha": alpha, "linewidth": linewidth, "markersize": markersize,
            "zorder": zorder, "label": label or layer.name,
            "column": column, "cmap": cmap, "scheme": scheme, "k": k,
            "marker": marker, "role": role,
        })
        return self

    def add_kde_heatmap(
        self,
        density_data: dict,
        cmap: str = "hot",
        alpha: float = 0.6,
        zorder: int = 3,
    ) -> "MapComposer":
        """
        添加 KDE 核密度热力图叠加层。

        Args:
            density_data: point_density() 函数返回的 dict (含 X/Y/Z/extent)
            cmap        : 色带名称（'hot' 'YlOrRd' 'plasma' 等）
            alpha       : 透明度
            zorder      : 渲染层次
        """
        self._kde_spec = {"data": density_data, "cmap": cmap, "alpha": alpha, "zorder": zorder}
        return self

    def render(self, output_path: str) -> str:
        """
        渲染地图并保存为图片文件。

        Args:
            output_path: 输出路径，支持 .png / .jpg / .pdf / .svg

        Returns:
            实际保存路径

        TODO:
            - [ ] 添加 show=True 参数，在 Jupyter Notebook 中内联显示
            - [ ] 自动创建输出目录（当前未处理目录不存在的情况）
            - [ ] 添加 watermark 水印支持（图片角落显示数据来源）
        """
        import os
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # 应用 CJK 字体
        if _DEFAULT_FONT:
            plt.rcParams["font.family"] = _DEFAULT_FONT

        fig, ax = plt.subplots(1, 1, figsize=self.figsize, dpi=self.dpi)
        bg = self.palette.get("background", "#f8f4f0")
        ax.set_facecolor(bg)
        fig.patch.set_facecolor(bg)

        legend_handles = []

        # ── 绘制 KDE 热力图 ────────────────────────────────────────────────
        if self._kde_spec:
            d = self._kde_spec["data"]
            ax.imshow(
                d["Z"], origin="lower",
                extent=d["extent"],
                cmap=self._kde_spec["cmap"],
                alpha=self._kde_spec["alpha"],
                aspect="auto",
                zorder=self._kde_spec["zorder"],
            )

        # ── 逐层绘制图层 ───────────────────────────────────────────────────
        for spec in self._layers:
            lyr = spec["layer"]
            gdf = lyr.data.copy()
            if lyr.epsg != 4326:
                gdf = gdf.to_crs("EPSG:4326")
            if len(gdf) == 0:
                continue

            geom_type = gdf.geometry.geom_type.iloc[0]
            c  = spec["color"]
            ec = spec["edge_color"]

            if spec["column"]:
                # Choropleth 分级设色
                gdf.plot(
                    ax=ax, column=spec["column"],
                    cmap=spec["cmap"], scheme=spec["scheme"], k=spec["k"],
                    alpha=spec["alpha"], edgecolor=ec or "none",
                    linewidth=spec["linewidth"], legend=False, zorder=spec["zorder"],
                )
                legend_handles.append(mpatches.Patch(
                    facecolor="gray", alpha=0.7,
                    label=f"{spec['label']} ({spec['column']})",
                ))
            elif "Polygon" in geom_type:
                fc = c or "#cccccc"
                gdf.plot(ax=ax, facecolor=fc, edgecolor=ec or "white",
                         alpha=spec["alpha"], linewidth=spec["linewidth"],
                         zorder=spec["zorder"])
                legend_handles.append(mpatches.Patch(
                    facecolor=fc, alpha=spec["alpha"],
                    label=spec["label"], edgecolor=ec or "none",
                ))
            elif "Line" in geom_type:
                lc = c or "#888888"
                gdf.plot(ax=ax, color=lc, alpha=spec["alpha"],
                         linewidth=spec["linewidth"], zorder=spec["zorder"])
                legend_handles.append(Line2D(
                    [0], [0], color=lc, linewidth=spec["linewidth"],
                    alpha=spec["alpha"], label=spec["label"],
                ))
            elif "Point" in geom_type:
                pc = c or self.palette["poi"]
                gdf.plot(ax=ax, color=pc, markersize=spec["markersize"],
                         alpha=spec["alpha"], edgecolors=ec or "none",
                         linewidth=0.4, zorder=spec["zorder"], marker=spec["marker"])
                legend_handles.append(Line2D(
                    [0], [0], marker=spec["marker"], color="w",
                    markerfacecolor=pc, markersize=7,
                    alpha=spec["alpha"], label=spec["label"],
                ))

        # ── 标题 & 副标题 ─────────────────────────────────────────────────
        is_dark = bg in ("#1a1a2e", "#1b2631", "#0d2137")
        title_color = "white" if is_dark else "#1a1a2e"

        if self.title:
            ax.set_title(self.title, fontsize=16, fontweight="bold",
                         color=title_color, pad=14, loc="left")
        if self.subtitle:
            ax.text(0.0, 1.01, self.subtitle, transform=ax.transAxes,
                    fontsize=9, color=title_color, alpha=0.7, va="bottom")

        # ── 图例 ──────────────────────────────────────────────────────────
        if legend_handles:
            leg_bg = "#ffffff" if not is_dark else "#1e1e3a"
            leg_tc = "#1a1a2e" if not is_dark else "white"
            ax.legend(
                handles=legend_handles, loc="lower right",
                fontsize=8, framealpha=0.9, fancybox=True,
                facecolor=leg_bg, labelcolor=leg_tc,
                edgecolor="#aaaaaa", borderpad=0.8,
            )

        # ── 指北针 ────────────────────────────────────────────────────────
        _draw_north_arrow(ax, color=title_color)

        # ── 比例尺 ────────────────────────────────────────────────────────
        if _HAS_SCALEBAR:
            try:
                scalebar = ScaleBar(
                    1, "m", length_fraction=0.15, location="lower left",
                    color=title_color, box_color="none",
                    font_properties={"size": 7},
                )
                ax.add_artist(scalebar)
            except Exception:
                pass  # TODO: 记录日志而非静默忽略

        # ── 轴样式 ────────────────────────────────────────────────────────
        grid_color = self.palette.get("grid", "#e0e0e0")
        ax.grid(True, linestyle="--", alpha=0.25, color=grid_color, linewidth=0.4)
        ax.tick_params(colors=title_color, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor(grid_color)
            spine.set_linewidth(0.5)
        ax.set_xlabel("Longitude", fontsize=8, color=title_color)
        ax.set_ylabel("Latitude",  fontsize=8, color=title_color)

        fig.tight_layout(pad=1.2)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 抑制字体缺失警告（CJK 字体已处理）
            fig.savefig(output_path, bbox_inches="tight",
                        dpi=self.dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
        print(f"  ✓ 地图已保存 → {output_path}")
        return output_path


def _draw_north_arrow(
    ax,
    x: float = 0.96,
    y: float = 0.96,
    size: float = 0.05,
    color: str = "black",
) -> None:
    """
    在地图右上角绘制简易指北针（N + 箭头）。

    TODO:
        - [ ] 支持更美观的指北针样式（玫瑰风向图）
        - [ ] 自动避开图例区域
    """
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    xr   = xlim[1] - xlim[0]
    yr   = ylim[1] - ylim[0]
    cx   = xlim[0] + x * xr
    cy   = ylim[0] + y * yr
    arrow_len = size * yr

    ax.annotate(
        "N",
        xy=(cx, cy + arrow_len * 0.3),
        xytext=(cx, cy - arrow_len * 0.6),
        arrowprops=dict(arrowstyle="->", color=color, lw=1.5),
        ha="center", va="center",
        fontsize=8, color=color, fontweight="bold",
    )
