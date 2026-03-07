"""
geoclaw_claude/core/project.py
=======================
GeoClawProject — 项目管理器

类比 QGIS 的 .qgz 项目文件，管理图层集合、输出目录和处理日志。

使用示例:
    from geoclaw_claude.core.project import GeoClawProject

    proj = GeoClawProject("武汉分析项目", output_dir="./output")
    proj.add_layer(hospitals_layer, "hospitals")
    proj.add_layer(roads_layer, "roads")

    layer = proj.get_layer("hospitals")
    print(proj.summary())
    proj.save_layer("hospitals", "output/hospitals.geojson")

────────────────────────────────────────────────────────
TODO:
  - [ ] save_project(path)   — 将项目元数据序列化为 JSON (.gcproj 格式)
  - [ ] load_project(path)   — 从 .gcproj 文件恢复项目 (不含数据，仅元数据+路径)
  - [ ] 添加图层分组 (Group) 支持，类似 QGIS 图层面板树
  - [ ] 添加 run_log 导出为 Markdown/HTML 分析报告
  - [ ] 支持图层排序 (拖拽式 z-order 管理)
  - [ ] 添加 CRS 一致性检查: 多图层叠加前自动提示 CRS 不一致
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import datetime
import os
from typing import Dict, Optional

import geopandas as gpd

from geoclaw_claude.core.layer import GeoLayer


class GeoClawProject:
    """
    GeoClaw 项目管理器。

    统一管理分析项目中的图层集合、输出路径和操作日志。

    Attributes:
        name       (str): 项目名称
        output_dir (str): 默认输出目录路径
        crs        (str): 项目默认坐标系（目前仅供参考，不强制同步）
        _layers    (dict): {layer_name: GeoLayer} 图层注册表
        _log       (list): 操作日志条目列表
    """

    def __init__(
        self,
        name: str = "GeoClaw Project",
        output_dir: str = ".",
        crs: str = "EPSG:4326",
    ):
        """
        初始化项目。

        Args:
            name      : 项目显示名称
            output_dir: 默认输出目录（不存在时自动创建）
            crs       : 项目默认坐标参考系
        """
        self.name       = name
        self.output_dir = output_dir
        self.crs        = crs
        self._layers: Dict[str, GeoLayer] = {}
        self._log: list = []
        self._created_at = datetime.datetime.now().isoformat(timespec="seconds")

        # 自动创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        self._append_log(f"项目创建: {name} | 输出目录: {output_dir}")

    # ── 图层管理 ──────────────────────────────────────────────────────────────

    def add_layer(self, layer: GeoLayer, name: Optional[str] = None) -> "GeoClawProject":
        """
        向项目添加图层。

        Args:
            layer: GeoLayer 实例
            name : 注册名（默认使用 layer.name）；若名称已存在则覆盖并记录警告

        Returns:
            self（支持链式调用）

        TODO:
            - [ ] 添加 allow_duplicate=False 参数防止意外覆盖
            - [ ] 图层名称标准化 (去除空格/特殊字符)
        """
        reg_name = name or layer.name
        if reg_name in self._layers:
            self._append_log(f"[WARNING] 图层 '{reg_name}' 已存在，已覆盖")
        self._layers[reg_name] = layer
        self._append_log(f"添加图层: '{reg_name}' ({layer.feature_count} 要素, {layer.geometry_type})")
        return self

    def add_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        name: str,
        source: str = "",
    ) -> "GeoClawProject":
        """
        直接从 GeoDataFrame 创建图层并添加到项目。

        Args:
            gdf   : GeoDataFrame
            name  : 图层名称
            source: 来源描述

        Returns:
            self（支持链式调用）
        """
        layer = GeoLayer(gdf, name=name, source=source)
        return self.add_layer(layer, name)

    def get_layer(self, name: str) -> GeoLayer:
        """
        按名称获取图层。

        Raises:
            KeyError: 图层名不存在时
        """
        if name not in self._layers:
            available = list(self._layers.keys())
            raise KeyError(f"图层 '{name}' 不存在。当前图层: {available}")
        return self._layers[name]

    def remove_layer(self, name: str) -> "GeoClawProject":
        """从项目中移除图层（不删除原始数据文件）。"""
        if name in self._layers:
            del self._layers[name]
            self._append_log(f"移除图层: '{name}'")
        return self

    def list_layers(self) -> list:
        """返回所有图层名称列表。"""
        return list(self._layers.keys())

    # ── 数据 I/O ──────────────────────────────────────────────────────────────

    def load_vector(self, path: str, name: Optional[str] = None) -> GeoLayer:
        """
        从文件加载矢量数据并注册为图层。

        支持格式: GeoJSON / Shapefile / GeoPackage / CSV（含坐标列）

        Args:
            path: 文件路径
            name: 图层名称（默认使用文件名）

        Returns:
            加载的 GeoLayer（同时已注册到项目）

        TODO:
            - [ ] 支持 URL 路径 (HTTP GeoJSON)
            - [ ] 支持从 ZIP 压缩包读取 Shapefile
        """
        from geoclaw_claude.io.vector import load_vector
        layer = load_vector(path, name=name)
        self.add_layer(layer)
        return layer

    def save_layer(
        self,
        name: str,
        path: Optional[str] = None,
        fmt: str = "geojson",
    ) -> str:
        """
        将指定图层保存到文件。

        Args:
            name: 图层注册名
            path: 输出路径（默认保存到 output_dir/{name}.{fmt}）
            fmt : 格式，支持 'geojson' / 'shapefile' / 'gpkg' / 'csv'

        Returns:
            实际保存路径字符串
        """
        from geoclaw_claude.io.vector import save_vector
        layer = self.get_layer(name)
        if path is None:
            ext_map = {"geojson": "geojson", "shapefile": "shp", "gpkg": "gpkg", "csv": "csv"}
            path = os.path.join(self.output_dir, f"{name}.{ext_map.get(fmt, fmt)}")
        save_vector(layer, path, fmt=fmt)
        self._append_log(f"保存图层: '{name}' → {path}")
        return path

    # ── 展示 ─────────────────────────────────────────────────────────────────

    def summary(self) -> str:
        """返回项目摘要字符串。"""
        lines = [
            f"╔══ {self.name} ══╗",
            f"  CRS        : {self.crs}",
            f"  Output dir : {self.output_dir}",
            f"  Created    : {self._created_at}",
            f"  Layers ({len(self._layers)}):",
        ]
        for lname, layer in self._layers.items():
            lines.append(
                f"    • {lname:<35} {layer.feature_count:>4} feat | "
                f"{layer.geometry_type} | EPSG:{layer.epsg}"
            )
        lines.append(f"  Log entries: {len(self._log)}")
        return "\n".join(lines)

    def print_log(self) -> None:
        """打印完整操作日志。"""
        print(f"── {self.name} 操作日志 ──")
        for entry in self._log:
            print(f"  {entry}")

    def _append_log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append(f"[{ts}] {msg}")

    def __repr__(self) -> str:
        return f"GeoClawProject(name={self.name!r}, layers={len(self._layers)})"
