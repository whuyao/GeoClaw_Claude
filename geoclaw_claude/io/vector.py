"""
geoclaw_claude/io/vector.py
====================
矢量数据 I/O 模块

支持格式:
  读取: GeoJSON / Shapefile (.shp) / GeoPackage (.gpkg) / CSV（含坐标列）
  写入: GeoJSON / Shapefile / GeoPackage / CSV

使用示例:
    from geoclaw_claude.io.vector import load_vector, save_vector, load_csv_points

    layer = load_vector("hospitals.geojson")
    layer = load_csv_points("points.csv", lon_col="longitude", lat_col="latitude")
    save_vector(layer, "output.gpkg", fmt="gpkg")

────────────────────────────────────────────────────────
TODO:
  - [ ] 支持读取 KML / KMZ 格式（常见于 Google Earth 数据）
  - [ ] 支持读取 DXF / DWG 格式（建筑/规划 CAD 数据）
  - [ ] 支持读取 GML 格式（国内城市开放数据常用）
  - [ ] 支持 URL 路径（HTTP/HTTPS GeoJSON 直接加载）
  - [ ] save_vector: 添加 encoding 参数（Shapefile 中文编码支持）
  - [ ] 添加 validate_geometry=True 参数（保存前修复无效几何）
  - [ ] 支持追加写入 GeoPackage（同一文件多图层）
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import os
from typing import Optional

import geopandas as gpd
import pandas as pd

from geoclaw_claude.core.layer import GeoLayer


# ── 读取 ──────────────────────────────────────────────────────────────────────

def load_vector(
    path: str,
    name: Optional[str] = None,
    encoding: str = "utf-8",
) -> GeoLayer:
    """
    从本地文件加载矢量数据，返回 GeoLayer。

    自动识别格式: .geojson / .json / .shp / .gpkg / .csv（按坐标列自动识别）

    Args:
        path    : 文件路径（绝对路径或相对路径）
        name    : 图层名称（默认使用不含扩展名的文件名）
        encoding: 文件编码（Shapefile 中文通常为 'gbk' 或 'utf-8'）

    Returns:
        GeoLayer

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的文件格式

    TODO:
        - [ ] 支持 layer= 参数读取 GeoPackage 中指定图层
        - [ ] 支持 bbox= 参数只读取指定范围内的要素（大文件优化）
        - [ ] 自动检测 Shapefile 编码（读取 .cpg 文件）
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")

    ext = os.path.splitext(path)[1].lower()
    layer_name = name or os.path.splitext(os.path.basename(path))[0]

    if ext == ".csv":
        # CSV 文件走专用函数自动识别坐标列
        return load_csv_points(path, name=layer_name)
    elif ext in (".geojson", ".json", ".shp", ".gpkg", ".geopackage"):
        try:
            gdf = gpd.read_file(path, encoding=encoding)
        except Exception as e:
            raise ValueError(f"读取文件失败: {path}\n错误: {e}")
    else:
        # TODO: 添加 KML/GML/DXF 支持
        raise ValueError(f"不支持的格式: {ext}。支持: .geojson .shp .gpkg .csv")

    if gdf.crs is None:
        import warnings
        warnings.warn(f"文件 '{path}' 缺少 CRS 信息，已默认设置为 EPSG:4326")
        gdf = gdf.set_crs("EPSG:4326")

    layer = GeoLayer(gdf, name=layer_name, source=path)
    print(f"  ✓ 加载: {layer_name} ({len(gdf)} 要素, {layer.geometry_type})")
    return layer


def load_csv_points(
    path: str,
    lon_col: str = "longitude",
    lat_col: str = "latitude",
    crs: str = "EPSG:4326",
    name: Optional[str] = None,
    encoding: str = "utf-8",
) -> GeoLayer:
    """
    从 CSV 文件加载点数据，自动识别坐标列名。

    自动识别的坐标列名（按优先级）:
        经度: longitude, lon, lng, x, long,经度
        纬度: latitude,  lat, y, lati, 纬度

    Args:
        path    : CSV 文件路径
        lon_col : 经度列名（若自动识别失败则使用此参数）
        lat_col : 纬度列名
        crs     : 坐标系（默认 WGS84）
        name    : 图层名称
        encoding: 文件编码

    Returns:
        点要素 GeoLayer

    TODO:
        - [ ] 支持 DMS 格式坐标自动转换（度°分′秒″ → 十进制度）
        - [ ] 支持 GCJ-02（高德/腾讯坐标系）→ WGS84 自动转换
        - [ ] 添加坐标范围校验（如经度 -180~180，纬度 -90~90）
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")

    df = pd.read_csv(path, encoding=encoding)
    cols_lower = {c.lower(): c for c in df.columns}

    # 自动识别经纬度列
    lon_candidates = ["longitude", "lon", "lng", "x", "long", "经度", "lng_wgs84"]
    lat_candidates = ["latitude",  "lat", "y",   "lati", "纬度", "lat_wgs84"]

    if lon_col not in df.columns:
        for c in lon_candidates:
            if c in cols_lower:
                lon_col = cols_lower[c]
                break

    if lat_col not in df.columns:
        for c in lat_candidates:
            if c in cols_lower:
                lat_col = cols_lower[c]
                break

    if lon_col not in df.columns or lat_col not in df.columns:
        raise ValueError(
            f"无法找到坐标列。可用列: {list(df.columns)}\n"
            f"请手动指定 lon_col= 和 lat_col= 参数。"
        )

    # 过滤无效坐标行
    df = df.dropna(subset=[lon_col, lat_col])
    df = df[(df[lon_col] != 0) & (df[lat_col] != 0)]

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
        crs=crs,
    )

    layer_name = name or os.path.splitext(os.path.basename(path))[0]
    layer = GeoLayer(gdf, name=layer_name, source=path)
    print(f"  ✓ CSV 加载: {layer_name} ({len(gdf)} 点，lon={lon_col}, lat={lat_col})")
    return layer


# ── 写入 ──────────────────────────────────────────────────────────────────────

def save_vector(
    layer: GeoLayer,
    path: str,
    fmt: Optional[str] = None,
    encoding: str = "utf-8",
) -> str:
    """
    将 GeoLayer 保存为本地文件。

    Args:
        layer   : 要保存的 GeoLayer
        path    : 输出文件路径（目录不存在时自动创建）
        fmt     : 格式 'geojson' | 'shapefile' | 'gpkg' | 'csv'
                  默认从文件扩展名自动推断
        encoding: 编码（Shapefile 中文时设为 'gbk'）

    Returns:
        实际保存的文件路径

    TODO:
        - [ ] Shapefile 自动截断超过 10 字符的字段名并输出提示
        - [ ] GeoJSON 支持 precision 参数控制坐标小数位数
        - [ ] 添加 overwrite=False 参数防止意外覆盖
    """
    # 自动推断格式
    if fmt is None:
        ext_map = {".geojson": "geojson", ".json": "geojson",
                   ".shp": "shapefile", ".gpkg": "gpkg", ".csv": "csv"}
        ext = os.path.splitext(path)[1].lower()
        fmt = ext_map.get(ext, "geojson")

    # 创建目录
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    gdf = layer.data

    if fmt == "geojson":
        gdf.to_file(path, driver="GeoJSON")
    elif fmt == "shapefile":
        gdf.to_file(path, driver="ESRI Shapefile", encoding=encoding)
    elif fmt in ("gpkg", "geopackage"):
        gdf.to_file(path, driver="GPKG", layer=layer.name)
    elif fmt == "csv":
        # CSV 输出经纬度列
        df = gdf.copy()
        df["longitude"] = gdf.geometry.x
        df["latitude"]  = gdf.geometry.y
        df.drop(columns=["geometry"]).to_csv(path, index=False, encoding=encoding)
    else:
        raise ValueError(f"不支持的格式: {fmt}。支持: geojson / shapefile / gpkg / csv")

    print(f"  ✓ 保存: {path} ({fmt})")
    return path
