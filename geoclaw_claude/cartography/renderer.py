"""
GeoClaw Cartography - Map rendering engine
Supports: static maps (matplotlib) + interactive maps (folium)
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import geopandas as gpd
import numpy as np
from pathlib import Path
from typing import Optional, Union, List
import folium
from folium.plugins import MarkerCluster

from geoclaw_claude.core.layer import GeoLayer

def _clean_gdf_for_folium(gdf):
    import pandas as pd
    gdf = gdf.copy()
    for col in list(gdf.columns):
        if col == 'geometry':
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)
    return gdf

# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License




# ─── Static Maps (matplotlib) ────────────────────────────────────────────────

class StaticMap:
    """QGIS-style static map composer using matplotlib."""

    def __init__(self, figsize=(12, 9), dpi=150, background="#f5f5f0"):
        self.figsize = figsize
        self.dpi = dpi
        self.background = background
        self.fig = None
        self.ax = None
        self._layers: list[dict] = []
        self._title = ""
        self._legend_items = []

    def add_layer(
        self,
        layer: GeoLayer,
        color: str = "#4a90d9",
        edge_color: str = "#2c5f8a",
        alpha: float = 0.7,
        linewidth: float = 0.8,
        markersize: float = 5,
        label: Optional[str] = None,
        column: Optional[str] = None,
        cmap: str = "YlOrRd",
        scheme: str = "quantiles",
    ) -> "StaticMap":
        self._layers.append({
            "layer": layer,
            "color": color,
            "edge_color": edge_color,
            "alpha": alpha,
            "linewidth": linewidth,
            "markersize": markersize,
            "label": label or layer.name,
            "column": column,
            "cmap": cmap,
            "scheme": scheme,
        })
        return self

    def set_title(self, title: str) -> "StaticMap":
        self._title = title
        return self

    def render(self) -> plt.Figure:
        """Render all layers and return the figure."""
        self.fig, self.ax = plt.subplots(1, 1, figsize=self.figsize, dpi=self.dpi)
        self.ax.set_facecolor(self.background)
        self.fig.patch.set_facecolor("white")

        for spec in self._layers:
            lyr = spec["layer"]
            gdf = lyr.data

            # Reproject to WGS84 for display if needed
            if lyr.epsg != 4326:
                gdf = gdf.to_crs("EPSG:4326")

            geom_type = gdf.geometry.geom_type.iloc[0]

            if spec["column"]:
                # Choropleth
                gdf.plot(
                    ax=self.ax,
                    column=spec["column"],
                    cmap=spec["cmap"],
                    scheme=spec["scheme"],
                    alpha=spec["alpha"],
                    edgecolor=spec["edge_color"],
                    linewidth=spec["linewidth"],
                    legend=True,
                    legend_kwds={"shrink": 0.5, "label": spec["column"]},
                )
            elif "Polygon" in geom_type:
                gdf.plot(
                    ax=self.ax,
                    color=spec["color"],
                    edgecolor=spec["edge_color"],
                    alpha=spec["alpha"],
                    linewidth=spec["linewidth"],
                )
                patch = mpatches.Patch(color=spec["color"], alpha=spec["alpha"], label=spec["label"])
                self._legend_items.append(patch)
            elif "Line" in geom_type:
                gdf.plot(ax=self.ax, color=spec["color"], alpha=spec["alpha"], linewidth=spec["linewidth"])
                from matplotlib.lines import Line2D
                line = Line2D([0], [0], color=spec["color"], linewidth=spec["linewidth"], label=spec["label"])
                self._legend_items.append(line)
            elif "Point" in geom_type:
                gdf.plot(ax=self.ax, color=spec["color"], markersize=spec["markersize"],
                         alpha=spec["alpha"], edgecolors=spec["edge_color"], linewidth=0.5)
                patch = mpatches.Patch(color=spec["color"], alpha=spec["alpha"], label=spec["label"])
                self._legend_items.append(patch)

        # Styling
        if self._title:
            self.ax.set_title(self._title, fontsize=14, fontweight="bold", pad=12)
        if self._legend_items:
            self.ax.legend(handles=self._legend_items, loc="lower right", fontsize=8,
                           framealpha=0.9, fancybox=True)

        self.ax.set_xlabel("Longitude", fontsize=8)
        self.ax.set_ylabel("Latitude", fontsize=8)
        self.ax.tick_params(labelsize=7)
        self.ax.grid(True, linestyle="--", alpha=0.3, linewidth=0.5)
        self.fig.tight_layout()
        return self.fig

    def save(self, path: str) -> str:
        if self.fig is None:
            self.render()
        self.fig.savefig(path, bbox_inches="tight", dpi=self.dpi)
        plt.close(self.fig)
        print(f"✓ Map saved → {path}")
        return path

    def show(self):
        if self.fig is None:
            self.render()
        plt.show()


# ─── Interactive Maps (folium) ────────────────────────────────────────────────

class InteractiveMap:
    """Web-based interactive map using folium."""

    BASEMAPS = {
        "osm":       "OpenStreetMap",
        "satellite": "Esri.WorldImagery",
        "topo":      "OpenTopoMap",
        "dark":      "CartoDB.DarkMatter",
        "light":     "CartoDB.Positron",
    }

    def __init__(self, basemap: str = "osm", zoom: int = 6):
        self.basemap = basemap
        self.zoom = zoom
        self._layers: list[dict] = []
        self._center: Optional[list] = None
        self._map: Optional[folium.Map] = None

    def set_center(self, lat: float, lon: float) -> "InteractiveMap":
        self._center = [lat, lon]
        return self

    def add_layer(
        self,
        layer: GeoLayer,
        color: str = "#3388ff",
        weight: float = 2,
        opacity: float = 0.8,
        fill_opacity: float = 0.4,
        popup_cols: Optional[List[str]] = None,
        cluster_points: bool = False,
    ) -> "InteractiveMap":
        self._layers.append({
            "layer": layer,
            "color": color,
            "weight": weight,
            "opacity": opacity,
            "fill_opacity": fill_opacity,
            "popup_cols": popup_cols,
            "cluster_points": cluster_points,
        })
        return self

    def build(self) -> folium.Map:
        """Build and return the folium Map object."""
        # Determine center from layers
        if self._center is None and self._layers:
            all_bounds = [spec["layer"].reproject(4326).bounds for spec in self._layers]
            minx = min(b[0] for b in all_bounds)
            miny = min(b[1] for b in all_bounds)
            maxx = max(b[2] for b in all_bounds)
            maxy = max(b[3] for b in all_bounds)
            self._center = [(miny + maxy) / 2, (minx + maxx) / 2]

        tiles = self.BASEMAPS.get(self.basemap, "OpenStreetMap")
        self._map = folium.Map(location=self._center or [0, 0], zoom_start=self.zoom, tiles=tiles)

        for spec in self._layers:
            lyr = spec["layer"]
            gdf = lyr.data
            if lyr.epsg != 4326:
                gdf = gdf.to_crs("EPSG:4326")

            geom_type = gdf.geometry.geom_type.iloc[0] if len(gdf) > 0 else "Unknown"

            def make_popup(row):
                if spec["popup_cols"]:
                    cols = spec["popup_cols"]
                else:
                    cols = [c for c in gdf.columns if c != "geometry"][:5]
                content = "<br>".join([f"<b>{c}</b>: {row[c]}" for c in cols if c in row.index])
                return folium.Popup(content, max_width=300) if content else None

            fg = folium.FeatureGroup(name=lyr.name)

            if "Point" in geom_type and spec["cluster_points"]:
                cluster = MarkerCluster()
                for _, row in gdf.iterrows():
                    popup = make_popup(row)
                    folium.Marker(
                        location=[row.geometry.y, row.geometry.x],
                        popup=popup,
                    ).add_to(cluster)
                cluster.add_to(fg)
            else:
                style = {
                    "color": spec["color"],
                    "weight": spec["weight"],
                    "opacity": spec["opacity"],
                    "fillColor": spec["color"],
                    "fillOpacity": spec["fill_opacity"],
                }
                gdf = _clean_gdf_for_folium(gdf)
                gdf = _clean_gdf_for_folium(gdf)
                folium.GeoJson(
                    gdf.__geo_interface__,
                    name=lyr.name,
                    style_function=lambda f, s=style: s,
                    tooltip=folium.GeoJsonTooltip(
                        fields=[c for c in gdf.columns if c != "geometry"][:3],
                        sticky=False,
                    ) if len(gdf.columns) > 1 else None,
                ).add_to(fg)

            fg.add_to(self._map)

        folium.LayerControl().add_to(self._map)
        return self._map

    def save(self, path: str) -> str:
        if self._map is None:
            self.build()
        self._map.save(path)
        print(f"✓ Interactive map saved → {path}")
        return path


# ── 便捷包装函数（供 NLExecutor 调用）─────────────────────────────────────────

def render_map(layers, title: str = "GeoClaw-claude 地图") -> "plt.Figure":
    """
    将一组 GeoLayer 渲染为静态地图，返回 matplotlib Figure。
    不调用 plt.show()，避免在无显示环境下挂死终端。
    """
    import matplotlib
    matplotlib.use("Agg")  # 强制非交互后端，防止终端崩溃

    m = StaticMap()
    m.set_title(title)
    for layer in layers:
        m.add_layer(layer)
    return m.render()


def render_interactive(layers, title: str = "GeoClaw-claude 交互地图") -> str:
    """
    将一组 GeoLayer 渲染为 Folium 交互地图，保存为临时 HTML 文件，返回路径。
    """
    import tempfile, os

    m = InteractiveMap(title=title)
    for layer in layers:
        m.add_layer(layer)
    m.build()

    tmp = tempfile.NamedTemporaryFile(
        suffix=".html", prefix="geoclaw_map_", delete=False
    )
    tmp.close()
    m.save(tmp.name)
    return tmp.name
