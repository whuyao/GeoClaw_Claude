"""
geoclaw_claude/core/layer.py
=====================
GeoLayer — GeoClaw 核心空间数据层

类似 QGIS 的 QgsVectorLayer，封装 GeoDataFrame 并添加:
  - CRS 管理与自动重投影
  - 处理历史记录 (provenance / 操作溯源)
  - 属性/空间过滤快捷方法
  - 图层元数据摘要

使用示例:
    import geopandas as gpd
    from geoclaw_claude.core.layer import GeoLayer

    gdf = gpd.read_file("hospitals.geojson")
    layer = GeoLayer(gdf, name="武汉医院")
    layer = layer.reproject(32650)                         # UTM Zone 50N
    named = layer.filter_by_attribute("name", "", "!=")   # 过滤有名称的
    print(layer.summary())

────────────────────────────────────────────────────────
TODO:
  - [ ] 添加 validate() 方法: 检查几何有效性并自动修复 (shapely make_valid)
  - [ ] 添加 sample(n) 方法: 随机采样 n 个要素
  - [ ] 支持图层样式持久化 (颜色/透明度存为元数据 dict)
  - [ ] 添加 to_wkt() / from_wkt() 序列化方法
  - [ ] 支持 MultiIndex 属性表 (用于时序/多维空间数据)
  - [ ] 子类 RasterLayer — 封装 rasterio DatasetReader
  - [ ] 添加 dissolve(by=column) 快捷方法
  - [ ] 添加 to_topojson() 输出方法
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import datetime
from typing import Any, List, Optional

import geopandas as gpd
from pyproj import CRS


class GeoLayer:
    """
    GeoClaw 核心空间数据层。

    封装 GeoDataFrame，提供统一的空间操作接口与处理历史追踪。

    Attributes:
        name    (str): 图层显示名称
        source  (str): 数据来源描述 (文件路径 / API 端点 / 手动创建)
        _data   (GeoDataFrame): 底层地理数据
        _history(list[dict])  : 操作历史，每条记录含 timestamp / action / detail
    """

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def __init__(
        self,
        data: gpd.GeoDataFrame,
        name: str = "Unnamed Layer",
        source: str = "",
    ):
        """
        初始化 GeoLayer。

        Args:
            data  : 带有 CRS 信息的 GeoDataFrame。
                    若 CRS 为空将自动假设 EPSG:4326 并发出警告。
            name  : 图层显示名称
            source: 数据来源描述 (可选，用于溯源)

        Raises:
            TypeError: 若 data 不是 GeoDataFrame
        """
        if not isinstance(data, gpd.GeoDataFrame):
            raise TypeError(f"data 必须是 GeoDataFrame，实际类型: {type(data)}")

        # TODO: 提供更细致的 CRS 推断机制 (如从文件元数据读取 .prj 文件)
        if data.crs is None:
            import warnings
            warnings.warn(
                f"GeoLayer '{name}' 缺少 CRS 信息，已默认设置为 EPSG:4326 (WGS84)。"
                "请确认数据坐标系是否正确。",
                UserWarning,
                stacklevel=2,
            )
            data = data.set_crs("EPSG:4326")

        self._data: gpd.GeoDataFrame = data.copy()
        self.name: str               = name
        self.source: str             = source
        self._history: List[dict]    = []

        self._log_event("created", f"来源={source or '未知'} | 要素数={len(data)}")

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    def _log_event(self, action: str, detail: str = "") -> None:
        """向处理历史追加一条记录。"""
        self._history.append({
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "action":    action,
            "detail":    detail,
        })

    # ── 属性访问 ──────────────────────────────────────────────────────────────

    @property
    def data(self) -> gpd.GeoDataFrame:
        """返回底层 GeoDataFrame（只读副本，防止意外修改）。"""
        return self._data

    @property
    def crs(self) -> CRS:
        """返回坐标参考系统 (pyproj.CRS 对象)。"""
        return self._data.crs

    @property
    def epsg(self) -> int:
        """返回 EPSG 整数代码，无法解析时返回 -1。"""
        try:
            return int(self._data.crs.to_epsg())
        except Exception:
            return -1

    @property
    def feature_count(self) -> int:
        """返回要素（行）数量。"""
        return len(self._data)

    def __len__(self) -> int:
        return self.feature_count

    @property
    def geometry_type(self) -> str:
        """返回主几何类型字符串 (Point / LineString / Polygon / Mixed)。"""
        if len(self._data) == 0:
            return "Empty"
        types = self._data.geometry.geom_type.unique()
        return types[0] if len(types) == 1 else "Mixed"

    @property
    def bounds(self) -> tuple:
        """返回空间范围元组 (minx, miny, maxx, maxy)。"""
        return tuple(self._data.total_bounds)

    @property
    def bbox(self) -> dict:
        """返回边界框字典，键名为 west/south/east/north。"""
        b = self._data.total_bounds
        return {"west": b[0], "south": b[1], "east": b[2], "north": b[3]}

    @property
    def columns(self) -> List[str]:
        """返回属性字段列表（不含 geometry 列）。"""
        return [c for c in self._data.columns if c != "geometry"]

    # ── 数据操作 ──────────────────────────────────────────────────────────────

    def reproject(self, epsg) -> "GeoLayer":
        """
        将图层重投影到指定 EPSG 坐标系，返回新图层（原图层不变）。

        Args:
            epsg: 目标 EPSG 代码，支持整数 (32650) 或字符串 ("EPSG:32650")

        Returns:
            重投影后的新 GeoLayer

        TODO:
            - [ ] 地理 CRS → 投影 CRS 时，在 summary 中提示单位由度变为米
        """
        # 支持 "EPSG:32650" 或 32650 两种格式
        if isinstance(epsg, str):
            epsg_str = epsg.upper()
            if epsg_str.startswith("EPSG:"):
                epsg = int(epsg_str.split(":")[1])
        reprojected = self._data.to_crs(epsg=epsg)
        new_layer = GeoLayer(reprojected, name=f"{self.name} [EPSG:{epsg}]", source=self.source)
        new_layer._history = self._history.copy()
        new_layer._log_event("reproject", f"EPSG:{self.epsg} → EPSG:{epsg}")
        return new_layer

    def filter_by_attribute(
        self,
        column: str,
        value: Any,
        operator: str = "==",
    ) -> "GeoLayer":
        """
        按属性值过滤要素，返回新图层（原图层不变）。

        Args:
            column  : 字段名
            value   : 比较值
            operator: 运算符，支持 '==' '!=' '>' '<' '>=' '<=' 'contains' 'startswith'

        Returns:
            过滤后的新 GeoLayer

        Raises:
            ValueError: 字段不存在或运算符不支持

        TODO:
            - [ ] 支持多条件组合 (AND/OR)，接受 list[tuple] 参数
            - [ ] 支持正则表达式过滤 (operator='regex')
            - [ ] 支持 IS NULL / IS NOT NULL 检测
        """
        if column not in self._data.columns:
            raise ValueError(f"字段 '{column}' 不存在。可用字段: {self.columns}")

        col = self._data[column]
        masks = {
            "==":         col == value,
            "!=":         col != value,
            ">":          col >  value,
            "<":          col <  value,
            ">=":         col >= value,
            "<=":         col <= value,
            "contains":   col.astype(str).str.contains(str(value), na=False),
            "startswith": col.astype(str).str.startswith(str(value), na=False),
        }
        if operator not in masks:
            raise ValueError(f"不支持的运算符 '{operator}'。支持: {list(masks)}")

        filtered = self._data[masks[operator]].reset_index(drop=True)
        new_layer = GeoLayer(filtered, name=f"{self.name} [filtered]", source=self.source)
        new_layer._history = self._history.copy()
        new_layer._log_event("filter_attribute",
                             f"{column} {operator} {value!r} → {len(filtered)} 条记录")
        return new_layer

    def filter_by_extent(self, bbox: tuple) -> "GeoLayer":
        """
        按矩形空间范围过滤要素（保留与 bbox 相交的要素）。

        Args:
            bbox: (minx, miny, maxx, maxy)

        Returns:
            空间过滤后的新 GeoLayer

        TODO:
            - [ ] 支持多边形掩模 (shapely Polygon)
            - [ ] 添加 clip=True 参数：真正裁剪几何边界而非仅按中心点过滤
        """
        from shapely.geometry import box
        mask = box(*bbox)
        filtered = self._data[self._data.intersects(mask)].reset_index(drop=True)
        new_layer = GeoLayer(filtered, name=f"{self.name} [extent]", source=self.source)
        new_layer._history = self._history.copy()
        new_layer._log_event("filter_extent", f"bbox={tuple(round(v, 4) for v in bbox)}")
        return new_layer

    # ── 元数据与展示 ──────────────────────────────────────────────────────────

    def summary(self) -> str:
        """返回图层摘要字符串（适合打印输出）。"""
        b = self.bounds
        lines = [
            f"╔══ {self.name} ══╗",
            f"  来源        : {self.source or '未知'}",
            f"  要素数      : {self.feature_count}",
            f"  几何类型    : {self.geometry_type}",
            f"  坐标系      : EPSG:{self.epsg}",
            f"  范围        : ({b[0]:.4f}, {b[1]:.4f}) → ({b[2]:.4f}, {b[3]:.4f})",
            f"  字段 ({len(self.columns)}): {', '.join(self.columns[:8])}{'...' if len(self.columns) > 8 else ''}",
        ]
        return "\n".join(lines)

    def history(self) -> str:
        """返回操作历史记录字符串。"""
        lines = [f"  [{h['timestamp']}] {h['action']}: {h['detail']}" for h in self._history]
        return "处理历史:\n" + "\n".join(lines)

    def __repr__(self) -> str:
        return (f"GeoLayer(name={self.name!r}, features={self.feature_count}, "
                f"type={self.geometry_type}, epsg={self.epsg})")
