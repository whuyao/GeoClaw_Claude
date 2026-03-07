"""
geoclaw_claude/analysis/raster_ops.py
=======================================
栅格数据空间分析模块 — 基于 rasterio + numpy 实现。

主要功能:
  - load_raster()        读取 GeoTIFF 等栅格文件
  - slope()              从 DEM 计算坡度
  - aspect()             从 DEM 计算坡向
  - hillshade()          生成山体阴影
  - reclassify()         栅格重分类（按区间映射值）
  - raster_calc()        栅格计算器（支持表达式）
  - zonal_stats()        分区统计（矢量区划×栅格值）
  - clip_raster()        按矢量范围裁剪栅格
  - resample()           栅格重采样
  - raster_to_vector()   栅格转矢量（等值线/面）
  - save_raster()        保存栅格到 GeoTIFF

使用示例:
    from geoclaw_claude.analysis.raster_ops import load_raster, slope, zonal_stats

    dem   = load_raster("dem.tif")
    slp   = slope(dem)
    stats = zonal_stats(slp, boundary_layer)

────────────────────────────────────────────────────────
TODO:
  - [ ] 支持 NetCDF 格式 (气象/海洋数据)
  - [ ] 核密度估计输出为栅格 (点→栅格)
  - [ ] 视域分析 (viewshed)
  - [ ] 成本路径分析 (cost path)
  - [ ] 栅格插值 (IDW / Kriging)
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import geopandas as gpd
from shapely.geometry import box

from geoclaw_claude.core.layer import GeoLayer


# ── 栅格数据结构 ──────────────────────────────────────────────────────────────

@dataclass
class RasterLayer:
    """
    轻量级栅格数据容器。

    Attributes:
        data      : numpy array, shape (bands, rows, cols)
        transform : affine.Affine 变换矩阵
        crs       : 坐标参考系 (rasterio CRS)
        nodata    : 无数据值
        meta      : 完整 rasterio meta 字典
        name      : 图层名称
        source    : 数据来源描述
    """
    data:      np.ndarray
    transform: Any          # affine.Affine
    crs:       Any          # rasterio.crs.CRS
    nodata:    Optional[float] = None
    meta:      Dict         = field(default_factory=dict)
    name:      str          = "raster"
    source:    str          = ""

    # ── 基本属性 ──────────────────────────────────────────────────────────────

    @property
    def shape(self) -> Tuple[int, int]:
        """(rows, cols)"""
        return self.data.shape[-2], self.data.shape[-1]

    @property
    def bands(self) -> int:
        return self.data.shape[0] if self.data.ndim == 3 else 1

    @property
    def band1(self) -> np.ndarray:
        """返回第一波段的 2D 数组（masked array）。"""
        arr = self.data[0] if self.data.ndim == 3 else self.data
        if self.nodata is not None:
            return np.ma.masked_equal(arr, self.nodata)
        return arr

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """(west, south, east, north) 地理范围。"""
        from rasterio.transform import array_bounds
        rows, cols = self.shape
        return array_bounds(rows, cols, self.transform)

    @property
    def resolution(self) -> Tuple[float, float]:
        """(x_res, y_res) 像元大小（单位同 CRS）。"""
        return abs(self.transform.a), abs(self.transform.e)

    def masked(self) -> np.ndarray:
        """返回 masked array，将 nodata 值掩盖。"""
        if self.nodata is not None:
            return np.ma.masked_equal(self.data, self.nodata)
        return self.data

    def summary(self) -> str:
        arr = self.band1.compressed() if np.ma.is_masked(self.band1) else self.band1.ravel()
        valid = arr[np.isfinite(arr)]
        return (
            f"栅格: {self.name} | {self.bands}波段 | "
            f"{self.shape[1]}×{self.shape[0]} px | "
            f"分辨率 {self.resolution[0]:.5f}° | "
            f"值域 [{valid.min():.2f}, {valid.max():.2f}] 均值 {valid.mean():.2f}"
            if len(valid) > 0 else f"栅格: {self.name} (空)"
        )


# ── 读写 ──────────────────────────────────────────────────────────────────────

def load_raster(path: str, band: Optional[int] = None) -> RasterLayer:
    """
    读取栅格文件（GeoTIFF / IMG / GRID 等 GDAL 支持格式）。

    Args:
        path : 文件路径
        band : 读取指定波段（默认读取全部）

    Returns:
        RasterLayer
    """
    try:
        import rasterio
    except ImportError:
        raise ImportError("需要安装 rasterio: pip install rasterio")

    with rasterio.open(path) as src:
        if band is not None:
            data = src.read(band)[np.newaxis, ...]  # 保持 (1, rows, cols)
        else:
            data = src.read()
        meta      = src.meta.copy()
        transform = src.transform
        crs       = src.crs
        nodata    = src.nodata

    name = Path(path).stem
    print(f"  ✓ 读取栅格: {name} {data.shape} nodata={nodata}")
    return RasterLayer(data=data, transform=transform, crs=crs,
                       nodata=nodata, meta=meta, name=name, source=path)


def save_raster(raster: RasterLayer, path: str) -> str:
    """
    将 RasterLayer 保存为 GeoTIFF。

    Returns:
        保存后的文件路径
    """
    try:
        import rasterio
    except ImportError:
        raise ImportError("需要安装 rasterio: pip install rasterio")

    meta = raster.meta.copy()
    meta.update({
        "driver":   "GTiff",
        "count":    raster.bands,
        "height":   raster.shape[0],
        "width":    raster.shape[1],
        "dtype":    str(raster.data.dtype),
        "crs":      raster.crs,
        "transform": raster.transform,
    })
    if raster.nodata is not None:
        meta["nodata"] = raster.nodata

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = raster.data if raster.data.ndim == 3 else raster.data[np.newaxis, ...]

    with rasterio.open(path, "w", **meta) as dst:
        dst.write(data)

    size_kb = Path(path).stat().st_size / 1024
    print(f"  ✓ 保存栅格: {path} ({size_kb:.1f} KB)")
    return path


# ── 地形分析 ──────────────────────────────────────────────────────────────────

def slope(dem: RasterLayer, units: str = "degrees") -> RasterLayer:
    """
    从 DEM 计算坡度。

    Args:
        dem   : 高程栅格 (RasterLayer)
        units : "degrees" 或 "percent"

    Returns:
        坡度栅格（同分辨率）

    TODO:
        - [ ] 支持 Horn 算法（更平滑，默认）和 Zevenbergen-Thorne 算法
        - [ ] 处理边缘像元
    """
    arr = dem.band1.astype(float)
    if dem.nodata is not None:
        arr = np.where(arr == dem.nodata, np.nan, arr)

    # 像元大小（投影到米）
    res_x, res_y = _get_resolution_meters(dem)

    # Sobel 梯度
    dz_dx = np.gradient(arr, axis=1) / res_x
    dz_dy = np.gradient(arr, axis=0) / res_y

    slope_rad = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))

    if units == "degrees":
        result = np.degrees(slope_rad)
    elif units == "percent":
        result = np.tan(slope_rad) * 100
    else:
        raise ValueError("units 必须是 'degrees' 或 'percent'")

    if dem.nodata is not None:
        result = np.where(np.isnan(arr), dem.nodata, result)

    print(f"  ✓ 坡度: {units}, 最大值 {np.nanmax(result):.1f}")
    return RasterLayer(
        data=result[np.newaxis, ...].astype(np.float32),
        transform=dem.transform, crs=dem.crs,
        nodata=dem.nodata, name="slope", source="slope(dem)",
    )


def aspect(dem: RasterLayer) -> RasterLayer:
    """
    从 DEM 计算坡向（0-360°，0/360=北，顺时针）。

    Returns:
        坡向栅格，-1 表示平地

    TODO:
        - [ ] 坡向分类（8方向/16方向）
    """
    arr = dem.band1.astype(float)
    if dem.nodata is not None:
        arr = np.where(arr == dem.nodata, np.nan, arr)

    res_x, res_y = _get_resolution_meters(dem)
    dz_dx = np.gradient(arr, axis=1) / res_x
    dz_dy = np.gradient(arr, axis=0) / res_y

    asp = np.degrees(np.arctan2(-dz_dy, dz_dx))
    asp = 90 - asp          # 转为地理方位角
    asp = np.where(asp < 0, asp + 360, asp)
    asp = np.where(np.isnan(arr), -1, asp)

    print(f"  ✓ 坡向计算完成")
    return RasterLayer(
        data=asp[np.newaxis, ...].astype(np.float32),
        transform=dem.transform, crs=dem.crs,
        nodata=-1, name="aspect", source="aspect(dem)",
    )


def hillshade(
    dem: RasterLayer,
    azimuth: float = 315.0,
    altitude: float = 45.0,
) -> RasterLayer:
    """
    从 DEM 生成山体阴影。

    Args:
        dem      : 高程栅格
        azimuth  : 光源方位角（°，默认西北 315°）
        altitude : 光源高度角（°，默认 45°）

    Returns:
        山体阴影栅格 (0-255)
    """
    arr = dem.band1.astype(float)
    if dem.nodata is not None:
        arr = np.where(arr == dem.nodata, np.nan, arr)

    res_x, res_y = _get_resolution_meters(dem)
    dz_dx = np.gradient(arr, axis=1) / res_x
    dz_dy = np.gradient(arr, axis=0) / res_y

    slp_rad = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))
    asp_rad = np.arctan2(-dz_dy, dz_dx)

    azi_rad = np.radians(360 - azimuth + 90)
    alt_rad = np.radians(altitude)

    hs = (
        np.cos(alt_rad) * np.cos(slp_rad)
        + np.sin(alt_rad) * np.sin(slp_rad) * np.cos(azi_rad - asp_rad)
    )
    hs = np.clip(hs * 255, 0, 255)
    if dem.nodata is not None:
        hs = np.where(np.isnan(arr), 0, hs)

    print(f"  ✓ 山体阴影: azimuth={azimuth}°, altitude={altitude}°")
    return RasterLayer(
        data=hs[np.newaxis, ...].astype(np.uint8),
        transform=dem.transform, crs=dem.crs,
        nodata=0, name="hillshade", source="hillshade(dem)",
    )


# ── 栅格重分类 ────────────────────────────────────────────────────────────────

def reclassify(
    raster: RasterLayer,
    breaks: List[Tuple[float, float, float]],
    nodata_out: float = -9999,
) -> RasterLayer:
    """
    按区间重分类栅格值。

    Args:
        raster    : 输入栅格
        breaks    : 区间映射列表 [(min, max, new_value), ...]
                    区间为左闭右开 [min, max)
        nodata_out: 未被任何区间覆盖的像元值

    Returns:
        重分类后栅格

    示例:
        # 将坡度分为 3 类
        breaks = [(0, 15, 1), (15, 30, 2), (30, 90, 3)]
        result = reclassify(slope_layer, breaks)
    """
    arr    = raster.band1.astype(float)
    result = np.full_like(arr, nodata_out, dtype=np.float32)

    for lo, hi, new_val in breaks:
        mask = (arr >= lo) & (arr < hi)
        result[mask] = new_val

    # 保留原 nodata
    if raster.nodata is not None:
        orig_nodata_mask = (arr == raster.nodata) | np.isnan(arr)
        result[orig_nodata_mask] = nodata_out

    classes = len(breaks)
    print(f"  ✓ 重分类: {classes} 个区间 → 值 {[b[2] for b in breaks]}")
    return RasterLayer(
        data=result[np.newaxis, ...],
        transform=raster.transform, crs=raster.crs,
        nodata=nodata_out, name=f"{raster.name}_reclass", source="reclassify()",
    )


# ── 栅格计算器 ────────────────────────────────────────────────────────────────

def raster_calc(
    expression: str,
    **layers: RasterLayer,
) -> RasterLayer:
    """
    栅格计算器 — 用 numpy 表达式操作多个栅格。

    Args:
        expression : numpy 表达式字符串，变量名对应 layers 参数
        **layers   : 关键字参数，键为变量名，值为 RasterLayer

    Returns:
        计算结果 RasterLayer

    示例:
        # NDVI = (nir - red) / (nir + red)
        ndvi = raster_calc("(nir - red) / (nir + red)", nir=nir_layer, red=red_layer)

        # 坡度坡向复合指数
        result = raster_calc("slp * 0.7 + (1 - asp/360) * 0.3", slp=slope_r, asp=aspect_r)

    TODO:
        - [ ] 支持条件表达式 np.where(...)
        - [ ] 支持更大栅格的分块计算（内存优化）
    """
    # 检查所有栅格形状一致
    shapes = {k: v.shape for k, v in layers.items()}
    if len(set(shapes.values())) > 1:
        raise ValueError(f"栅格形状不一致: {shapes}，请先重采样到相同分辨率")

    # 构建计算上下文
    context = {k: v.band1.astype(float) for k, v in layers.items()}
    context["np"] = np

    try:
        result = eval(expression, {"__builtins__": {}}, context)
    except Exception as e:
        raise ValueError(f"表达式执行错误: {e}\n  表达式: {expression}")

    result = np.asarray(result, dtype=np.float32)

    # 取第一个图层的地理参考
    ref = next(iter(layers.values()))
    print(f"  ✓ 栅格计算: {expression[:60]}...")
    return RasterLayer(
        data=result[np.newaxis, ...] if result.ndim == 2 else result,
        transform=ref.transform, crs=ref.crs,
        nodata=ref.nodata, name="calc_result", source=f"raster_calc({expression[:30]})",
    )


# ── 分区统计 ──────────────────────────────────────────────────────────────────

def zonal_stats(
    raster: RasterLayer,
    zones: GeoLayer,
    stats: List[str] = ["mean", "min", "max", "std", "count"],
    prefix: str = "",
) -> GeoLayer:
    """
    分区统计 — 按矢量区划计算栅格统计值。

    Args:
        raster : 输入栅格
        zones  : 分区矢量图层（Polygon/MultiPolygon）
        stats  : 统计指标列表: mean/min/max/std/sum/count/median/range
        prefix : 输出字段名前缀

    Returns:
        含统计结果字段的 GeoLayer（原属性 + 统计字段）

    TODO:
        - [ ] 支持 rasterstats 库（更快）
        - [ ] 支持百分位数 (p10, p90 等)
        - [ ] 支持多波段批量统计
    """
    try:
        import rasterio
        import rasterio.mask
        from rasterio.transform import rowcol
    except ImportError:
        raise ImportError("需要安装 rasterio: pip install rasterio")

    import io
    import tempfile

    # 将 RasterLayer 写入临时文件（rasterio.mask 需要文件或 DatasetReader）
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    save_raster(raster, tmp_path)

    result_rows = []
    with rasterio.open(tmp_path) as src:
        # 统一 CRS
        zones_crs = zones.data.to_crs(src.crs.to_epsg() or 4326)

        for _, row in zones_crs.iterrows():
            geom = [row.geometry.__geo_interface__]
            try:
                masked_data, _ = rasterio.mask.mask(src, geom, crop=True, nodata=raster.nodata)
                arr = masked_data[0].astype(float)

                # 过滤 nodata
                if raster.nodata is not None:
                    arr = arr[arr != raster.nodata]
                arr = arr[np.isfinite(arr)]

                stat_row = {}
                if len(arr) > 0:
                    for s in stats:
                        k = f"{prefix}{s}" if prefix else s
                        if s == "mean":   stat_row[k] = round(float(np.mean(arr)), 4)
                        elif s == "min":  stat_row[k] = round(float(np.min(arr)), 4)
                        elif s == "max":  stat_row[k] = round(float(np.max(arr)), 4)
                        elif s == "std":  stat_row[k] = round(float(np.std(arr)), 4)
                        elif s == "sum":  stat_row[k] = round(float(np.sum(arr)), 4)
                        elif s == "count": stat_row[k] = int(len(arr))
                        elif s == "median": stat_row[k] = round(float(np.median(arr)), 4)
                        elif s == "range": stat_row[k] = round(float(np.max(arr) - np.min(arr)), 4)
                else:
                    for s in stats:
                        k = f"{prefix}{s}" if prefix else s
                        stat_row[k] = None
            except Exception:
                stat_row = {(f"{prefix}{s}" if prefix else s): None for s in stats}

            result_rows.append(stat_row)

    # 清理临时文件
    import os
    try:
        os.unlink(tmp_path)
    except Exception:
        pass

    stats_df = gpd.pd.DataFrame(result_rows)
    result_gdf = gpd.GeoDataFrame(
        gpd.pd.concat([zones.data.reset_index(drop=True), stats_df], axis=1),
        geometry="geometry",
        crs=zones.data.crs,
    )
    print(f"  ✓ 分区统计: {len(result_gdf)} 区划 × {stats} 指标")
    return GeoLayer(result_gdf, name=f"zonal_stats_{raster.name}", source="zonal_stats()")


# ── 裁剪 ──────────────────────────────────────────────────────────────────────

def clip_raster(
    raster: RasterLayer,
    mask: Union[GeoLayer, tuple],
    crop: bool = True,
) -> RasterLayer:
    """
    按矢量边界或 bbox 裁剪栅格。

    Args:
        raster : 输入栅格
        mask   : GeoLayer（多边形）或 (west,south,east,north) 元组
        crop   : 是否裁剪到最小外接矩形

    Returns:
        裁剪后栅格
    """
    try:
        import rasterio
        import rasterio.mask
        from rasterio.transform import from_bounds
        import tempfile, os
    except ImportError:
        raise ImportError("需要安装 rasterio")

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    save_raster(raster, tmp_path)

    with rasterio.open(tmp_path) as src:
        if isinstance(mask, tuple):
            west, south, east, north = mask
            geoms = [box(west, south, east, north).__geo_interface__]
        else:
            mask_reproj = mask.data.to_crs(src.crs.to_epsg() or 4326)
            geoms = [g.__geo_interface__ for g in mask_reproj.geometry]

        clipped, new_transform = rasterio.mask.mask(src, geoms, crop=crop, nodata=raster.nodata)
        new_meta = src.meta.copy()
        new_meta.update({"height": clipped.shape[1], "width": clipped.shape[2],
                         "transform": new_transform})

    try:
        os.unlink(tmp_path)
    except Exception:
        pass

    print(f"  ✓ 裁剪: {raster.shape} → {clipped.shape[1:]} px")
    return RasterLayer(
        data=clipped, transform=new_transform, crs=raster.crs,
        nodata=raster.nodata, meta=new_meta,
        name=f"{raster.name}_clip", source="clip_raster()",
    )


# ── 重采样 ────────────────────────────────────────────────────────────────────

def resample(
    raster: RasterLayer,
    scale: float = 0.5,
    method: str = "bilinear",
) -> RasterLayer:
    """
    栅格重采样（缩放分辨率）。

    Args:
        raster : 输入栅格
        scale  : 缩放比例（<1=降分辨率，>1=升分辨率）
        method : "nearest" / "bilinear" / "cubic" / "average"

    Returns:
        重采样后栅格

    TODO:
        - [ ] 支持指定目标分辨率（米/度）
        - [ ] 支持对齐到参考栅格
    """
    try:
        import rasterio
        from rasterio.enums import Resampling
        import tempfile, os
    except ImportError:
        raise ImportError("需要安装 rasterio")

    method_map = {
        "nearest":  Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic":    Resampling.cubic,
        "average":  Resampling.average,
    }
    resamp = method_map.get(method, Resampling.bilinear)

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    save_raster(raster, tmp_path)

    with rasterio.open(tmp_path) as src:
        new_h = int(src.height * scale)
        new_w = int(src.width  * scale)
        new_data = src.read(
            out_shape=(src.count, new_h, new_w),
            resampling=resamp,
        )
        new_transform = src.transform * src.transform.scale(
            src.width / new_w, src.height / new_h
        )

    try:
        os.unlink(tmp_path)
    except Exception:
        pass

    print(f"  ✓ 重采样: {raster.shape} → ({new_h}, {new_w}) scale={scale}")
    return RasterLayer(
        data=new_data, transform=new_transform, crs=raster.crs,
        nodata=raster.nodata, name=f"{raster.name}_resamp", source="resample()",
    )


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_resolution_meters(raster: RasterLayer) -> Tuple[float, float]:
    """
    获取栅格像元大小（米）。
    若 CRS 为地理坐标系则近似换算。
    """
    res_x, res_y = raster.resolution
    try:
        if raster.crs and raster.crs.is_geographic:
            # 近似：1° ≈ 111320m（纬度方向），经度方向随纬度变化
            bounds = raster.bounds
            mid_lat = (bounds[1] + bounds[3]) / 2
            res_x_m = res_x * 111320 * np.cos(np.radians(mid_lat))
            res_y_m = res_y * 111320
            return res_x_m, res_y_m
    except Exception:
        pass
    return res_x, res_y
