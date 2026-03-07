"""
geoclaw_claude/utils/coord_transform.py
=========================================
中国常用坐标系互转工具。

  WGS84  — GPS 原始坐标（EPSG:4326）
  GCJ-02 — 国测局加密坐标（高德/腾讯地图）
  BD-09  — 百度地图坐标

函数命名规则: <from>_to_<to>(lon, lat)
  返回值均为 (lon, lat) 元组。

使用示例:
    from geoclaw_claude.utils.coord_transform import wgs84_to_gcj02, gcj02_to_wgs84

    lon2, lat2 = wgs84_to_gcj02(114.30, 30.60)
    layer_fixed = transform_layer(layer, "wgs84", "gcj02")

────────────────────────────────────────────────────────
TODO:
  - [ ] 批量转换 numpy 数组（向量化加速）
  - [ ] 支持 CGCS2000 坐标系
  - [ ] 反向迭代求解精确逆变换（当前逆变换为近似）
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import math
from typing import Tuple, Union
import numpy as np

# 克拉索夫斯基椭球体参数
_A = 6378245.0       # 长半轴
_EE = 0.00669342162296594323  # 偏心率平方


def _out_of_china(lon: float, lat: float) -> bool:
    """判断坐标是否在中国境外（境外不需要偏移）。"""
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(lon: float, lat: float) -> float:
    ret = (
        -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat
        + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
        + (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
        + (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
        + (160.0 * math.sin(lat / 12.0 * math.pi) + 320.0 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    )
    return ret


def _transform_lon(lon: float, lat: float) -> float:
    ret = (
        300.0 + lon + 2.0 * lat + 0.1 * lon * lon
        + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
        + (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
        + (20.0 * math.sin(lon * math.pi) + 40.0 * math.sin(lon / 3.0 * math.pi)) * 2.0 / 3.0
        + (150.0 * math.sin(lon / 12.0 * math.pi) + 300.0 * math.sin(lon * math.pi / 30.0)) * 2.0 / 3.0
    )
    return ret


# ── WGS84 ↔ GCJ02 ────────────────────────────────────────────────────────────

def wgs84_to_gcj02(lon: float, lat: float) -> Tuple[float, float]:
    """WGS84 → GCJ-02（高德/腾讯）。"""
    if _out_of_china(lon, lat):
        return lon, lat
    d_lat = _transform_lat(lon - 105.0, lat - 35.0)
    d_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    d_lon = (d_lon * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lon + d_lon, lat + d_lat


def gcj02_to_wgs84(lon: float, lat: float) -> Tuple[float, float]:
    """GCJ-02 → WGS84（近似逆变换，误差 < 0.00005°）。"""
    if _out_of_china(lon, lat):
        return lon, lat
    # 迭代逼近
    gcj_lon, gcj_lat = wgs84_to_gcj02(lon, lat)
    d_lon = gcj_lon - lon
    d_lat = gcj_lat - lat
    return lon - d_lon, lat - d_lat


# ── GCJ02 ↔ BD09 ──────────────────────────────────────────────────────────────

_X_PI = math.pi * 3000.0 / 180.0


def gcj02_to_bd09(lon: float, lat: float) -> Tuple[float, float]:
    """GCJ-02 → BD-09（百度）。"""
    z   = math.sqrt(lon * lon + lat * lat) + 0.00002 * math.sin(lat * _X_PI)
    theta = math.atan2(lat, lon) + 0.000003 * math.cos(lon * _X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_gcj02(lon: float, lat: float) -> Tuple[float, float]:
    """BD-09 → GCJ-02。"""
    x = lon - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
    return z * math.cos(theta), z * math.sin(theta)


# ── WGS84 ↔ BD09 ──────────────────────────────────────────────────────────────

def wgs84_to_bd09(lon: float, lat: float) -> Tuple[float, float]:
    """WGS84 → BD-09。"""
    gcj = wgs84_to_gcj02(lon, lat)
    return gcj02_to_bd09(*gcj)


def bd09_to_wgs84(lon: float, lat: float) -> Tuple[float, float]:
    """BD-09 → WGS84。"""
    gcj = bd09_to_gcj02(lon, lat)
    return gcj02_to_wgs84(*gcj)


# ── 批量图层转换 ──────────────────────────────────────────────────────────────

_TRANSFORMS = {
    ("wgs84",  "gcj02"): wgs84_to_gcj02,
    ("gcj02",  "wgs84"): gcj02_to_wgs84,
    ("gcj02",  "bd09"):  gcj02_to_bd09,
    ("bd09",   "gcj02"): bd09_to_gcj02,
    ("wgs84",  "bd09"):  wgs84_to_bd09,
    ("bd09",   "wgs84"): bd09_to_wgs84,
}


def transform_layer(
    layer,   # GeoLayer
    from_cs: str,
    to_cs:   str,
) -> "GeoLayer":  # type: ignore
    """
    对整个 GeoLayer 做坐标系转换。

    Args:
        layer   : GeoLayer（Point/LineString/Polygon 均支持）
        from_cs : 源坐标系: "wgs84" / "gcj02" / "bd09"
        to_cs   : 目标坐标系

    Returns:
        转换后的新 GeoLayer（原图层不变）

    TODO:
        - [ ] 向量化实现（当前逐点转换，大数据集较慢）
        - [ ] 支持 Polygon/MultiPolygon 内环
    """
    from shapely.geometry import (
        Point, LineString, Polygon,
        MultiPoint, MultiLineString, MultiPolygon,
        mapping, shape,
    )
    import geopandas as gpd
    from geoclaw_claude.core.layer import GeoLayer

    key = (from_cs.lower(), to_cs.lower())
    if key not in _TRANSFORMS:
        raise ValueError(
            f"不支持的转换: {from_cs} → {to_cs}\n"
            f"支持: {list(_TRANSFORMS.keys())}"
        )
    fn = _TRANSFORMS[key]

    def _transform_coords(coords):
        return [fn(x, y) for x, y in coords]

    def _transform_geom(geom):
        if geom is None or geom.is_empty:
            return geom
        t = geom.geom_type
        if t == "Point":
            return Point(fn(geom.x, geom.y))
        elif t == "LineString":
            return LineString(_transform_coords(geom.coords))
        elif t == "Polygon":
            ext = _transform_coords(geom.exterior.coords)
            holes = [_transform_coords(i.coords) for i in geom.interiors]
            return Polygon(ext, holes)
        elif t == "MultiPoint":
            return MultiPoint([Point(fn(p.x, p.y)) for p in geom.geoms])
        elif t == "MultiLineString":
            return MultiLineString([_transform_coords(ls.coords) for ls in geom.geoms])
        elif t == "MultiPolygon":
            polys = []
            for poly in geom.geoms:
                ext = _transform_coords(poly.exterior.coords)
                holes = [_transform_coords(i.coords) for i in poly.interiors]
                polys.append(Polygon(ext, holes))
            return MultiPolygon(polys)
        else:
            return geom  # 不支持的几何类型原样返回

    gdf = layer.data.copy()
    gdf["geometry"] = gdf["geometry"].apply(_transform_geom)

    print(f"  ✓ 坐标转换: {from_cs.upper()} → {to_cs.upper()}, {len(gdf)} 要素")
    return GeoLayer(gdf, name=f"{layer.name}_{to_cs}", source=f"transform({from_cs}→{to_cs})")
