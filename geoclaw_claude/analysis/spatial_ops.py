"""
geoclaw_claude/analysis/spatial_ops.py
================================
空间分析算法集合

提供常用的矢量空间操作，参考 QGIS Processing 工具箱设计:
  - buffer()           缓冲区分析
  - intersect()        相交分析
  - union()            合并分析
  - clip()             裁剪
  - nearest_neighbor() 最近邻连接（含 UTM 投影正确计算距离）
  - spatial_join()     空间连接
  - calculate_area()   面积计算
  - zonal_stats()      分区统计
  - kde()              核密度估计（返回 numpy 网格 + extent）

所有函数均接受 GeoLayer，返回新的 GeoLayer（不修改输入数据）。
度量单位（米/千米/平方千米）的计算会自动投影到最佳 UTM 分带后完成。

────────────────────────────────────────────────────────
TODO:
  - [ ] 添加 dissolve(layer, by=column) 按属性合并要素
  - [ ] 添加 convex_hull(layer) 凸包计算
  - [ ] 添加 centroid(layer) 质心提取
  - [ ] 添加 voronoi(points) Voronoi 多边形生成
  - [ ] 添加 densify(layer, interval) 折线/面增密
  - [ ] 添加 simplify(layer, tolerance) 几何简化 (Douglas-Peucker)
  - [ ] buffer: 支持 side_buffer (单侧缓冲区) 用于道路缓冲
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import numpy as np
from shapely.ops import unary_union

from geoclaw_claude.core.layer import GeoLayer


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _estimate_utm(layer: GeoLayer) -> str:
    """
    根据图层中心坐标估算最佳 UTM 投影 EPSG 代码。

    策略: 取 bounds 中心经度确定 UTM Zone，纬度确定南北半球。

    TODO:
        - [ ] 处理跨多个 UTM Zone 的大范围数据 (使用等积圆锥投影替代)
        - [ ] 返回 pyproj.CRS 对象而非 EPSG 字符串
    """
    b = layer.bounds
    lon_c = (b[0] + b[2]) / 2
    lat_c = (b[1] + b[3]) / 2
    zone  = int((lon_c + 180) / 6) + 1
    hemi  = "N" if lat_c >= 0 else "S"
    epsg  = 32600 + zone if hemi == "N" else 32700 + zone
    return f"EPSG:{epsg}"


def _align_crs(layer_a: GeoLayer, layer_b: GeoLayer) -> tuple:
    """
    统一两个图层的 CRS（以 layer_a 为基准重投影 layer_b）。

    Returns:
        (gdf_a, gdf_b) — 同一 CRS 的两个 GeoDataFrame
    """
    gdf_a = layer_a.data
    gdf_b = layer_b.data
    if layer_a.epsg != layer_b.epsg:
        gdf_b = gdf_b.to_crs(gdf_a.crs)
    return gdf_a, gdf_b


# ── 公共 API ──────────────────────────────────────────────────────────────────

def buffer(
    layer: GeoLayer,
    distance: float,
    unit: str = "meters",
    dissolve: bool = False,
) -> GeoLayer:
    """
    创建缓冲区图层。

    对于度量单位 (meters/km)，自动投影到最佳 UTM 后计算，再投回原始 CRS。

    Args:
        layer   : 输入图层 (Point/Line/Polygon 均支持)
        distance: 缓冲距离
        unit    : 'meters' | 'km' | 'degrees' (不推荐使用 degrees)
        dissolve: True 时合并所有缓冲区为单一 Polygon

    Returns:
        缓冲区 GeoLayer

    TODO:
        - [ ] 支持 cap_style / join_style 参数控制端头/转角样式
        - [ ] 支持每要素不同缓冲距离 (distance 为字段名时按属性值缓冲)
        - [ ] 添加 side_buffer(side='left'|'right') 用于道路单侧缓冲
    """
    # 单位换算
    unit_multiplier = {"km": 1000, "meters": 1, "m": 1, "degrees": 1}
    dist_m = distance * unit_multiplier.get(unit, 1)

    # 投影到 UTM 做缓冲
    original_crs = layer.crs
    utm_crs = _estimate_utm(layer)
    gdf_utm = layer.data.to_crs(utm_crs)

    if unit == "degrees":
        buffered = gdf_utm.buffer(distance)
    else:
        buffered = gdf_utm.buffer(dist_m)

    gdf_result = gdf_utm.copy()
    gdf_result["geometry"] = buffered

    if dissolve:
        from shapely.ops import unary_union
        merged = unary_union(gdf_result.geometry)
        gdf_result = gpd.GeoDataFrame(
            [{"geometry": merged}], crs=utm_crs
        )

    # 投回原始 CRS
    gdf_result = gdf_result.to_crs(original_crs)
    out = GeoLayer(gdf_result, name=f"{layer.name}_buffer_{distance}{unit}", source=layer.source)
    out._log_event("buffer", f"distance={distance}{unit}, dissolve={dissolve}")
    return out


def intersect(layer_a: GeoLayer, layer_b: GeoLayer) -> GeoLayer:
    """
    相交分析: 计算 layer_a 与 layer_b 的几何交集并合并属性。

    Args:
        layer_a: 输入图层 A
        layer_b: 输入图层 B（遮罩/裁剪层）

    Returns:
        仅包含两层重叠部分的新 GeoLayer

    TODO:
        - [ ] 保留来源图层标识字段 (source_a / source_b)
        - [ ] 处理属性字段名冲突（加前缀 a_ / b_）
    """
    gdf_a, gdf_b = _align_crs(layer_a, layer_b)
    result = gpd.overlay(gdf_a, gdf_b, how="intersection")
    out = GeoLayer(result, name=f"{layer_a.name} ∩ {layer_b.name}")
    out._log_event("intersect", f"{layer_a.name} ∩ {layer_b.name}")
    return out


def union(layer_a: GeoLayer, layer_b: GeoLayer) -> GeoLayer:
    """
    合并分析: 计算 layer_a 与 layer_b 的几何并集。

    TODO:
        - [ ] 处理属性字段 NaN 填充策略 (None / 0 / '' 可配置)
    """
    gdf_a, gdf_b = _align_crs(layer_a, layer_b)
    result = gpd.overlay(gdf_a, gdf_b, how="union")
    out = GeoLayer(result, name=f"{layer_a.name} ∪ {layer_b.name}")
    out._log_event("union", f"{layer_a.name} ∪ {layer_b.name}")
    return out


def clip(layer: GeoLayer, mask: GeoLayer) -> GeoLayer:
    """
    裁剪: 用 mask 裁剪 layer 的几何范围（保留 layer 的属性）。

    Args:
        layer: 被裁剪图层
        mask : 裁剪掩模图层（通常为面要素）

    Returns:
        裁剪后的新 GeoLayer

    TODO:
        - [ ] 支持用 bbox tuple 直接作为 mask 参数
        - [ ] 处理 mask 包含多面时先 dissolve 再裁剪
    """
    gdf_layer, gdf_mask = _align_crs(layer, mask)
    mask_geom = unary_union(gdf_mask.geometry)
    result = gdf_layer.copy()
    result["geometry"] = result.geometry.intersection(mask_geom)
    result = result[~result.geometry.is_empty].reset_index(drop=True)
    out = GeoLayer(result, name=f"{layer.name}_clipped", source=layer.source)
    out._log_event("clip", f"mask={mask.name}")
    return out


def nearest_neighbor(
    source,
    target,
    k: int = 1,
) -> GeoLayer:
    """
    最近邻分析: 为 source 中每个要素找到 target 中距离最近的 k 个要素。

    结果图层新增字段:
        nn_distance (float): 到最近要素的距离（米，UTM 投影后计算）
        nn_index    (int)  : target 中最近要素的原始索引

    Args:
        source: 查询图层（GeoLayer 或 GeoDataFrame）
        target: 被搜索图层（GeoLayer 或 GeoDataFrame）
        k     : 返回最近邻数量（当前仅支持 k=1）

    TODO:
        - [ ] 支持 k>1，返回 nn_distance_1, nn_distance_2 ... 多列
        - [ ] 添加 max_distance 参数：超出阈值则标记为 NaN
        - [ ] 返回 nn_name 字段（target 的指定属性值）
    """
    # 兼容 GeoLayer 和 GeoDataFrame 两种输入
    if isinstance(source, GeoLayer):
        src_gdf  = source.data
        src_name = source.name
        src_src  = source.source
    else:
        src_gdf  = source
        src_name = "source"
        src_src  = ""

    if isinstance(target, GeoLayer):
        tgt_gdf = target.data
        tgt_name = target.name
    else:
        tgt_gdf  = target
        tgt_name = "target"

    # 统一 CRS
    if src_gdf.crs != tgt_gdf.crs:
        tgt_gdf = tgt_gdf.to_crs(src_gdf.crs)

    # 投影到 UTM 以获取正确的米制距离（修复地理坐标下距离为0的BUG）
    # 根据质心估算 UTM zone（先临时投影到 Web Mercator 再取质心，避免 CRS warning）
    src_merc = src_gdf.to_crs(epsg=3857)
    cx = float(src_merc.geometry.centroid.x.mean())
    cy = float(src_merc.geometry.centroid.y.mean())
    # 反算经纬度
    import math
    cx_deg = cx / 20037508.34 * 180
    cy_deg = math.degrees(2 * math.atan(math.exp(cy / 6378137)) - math.pi / 2)
    zone = int((cx_deg + 180) / 6) + 1
    hemisphere = 32600 if cy_deg >= 0 else 32700
    utm_epsg = hemisphere + zone

    src_utm = src_gdf.to_crs(epsg=utm_epsg)
    tgt_utm = tgt_gdf.to_crs(epsg=utm_epsg)

    # 只保留 geometry，避免列名冲突
    tgt_geom = gpd.GeoDataFrame(
        geometry=tgt_utm.geometry.reset_index(drop=True).values,
        crs=utm_epsg,
    )

    joined = gpd.sjoin_nearest(
        src_utm.reset_index(drop=True),
        tgt_geom,
        how="left",
        distance_col="nn_distance",
    )
    # 处理一对多重复行，保留第一个（最近的）
    joined = joined[~joined.index.duplicated(keep="first")]

    result = src_gdf.copy().reset_index(drop=True)
    result["nn_distance"] = joined["nn_distance"].values
    result["nn_index"]    = joined["index_right"].values

    print(f"  最近邻: {src_name}→{tgt_name}, "
          f"均值 {result['nn_distance'].mean():.1f}m, "
          f"最大 {result['nn_distance'].max():.1f}m")

    out = GeoLayer(result, name=f"{src_name}_nn", source=src_src)
    return out


def spatial_join(
    source: GeoLayer,
    target: GeoLayer,
    how: str = "left",
    predicate: str = "intersects",
) -> GeoLayer:
    """
    空间连接: 将 target 的属性连接到 source（基于空间关系）。

    Args:
        source   : 主图层（保留所有要素）
        target   : 连接图层（提供属性）
        how      : 'left' | 'right' | 'inner'
        predicate: 'intersects' | 'contains' | 'within' | 'crosses'

    Returns:
        连接后的新 GeoLayer

    TODO:
        - [ ] 处理一对多连接时的聚合策略 (first / count / list)
        - [ ] 添加 lsuffix / rsuffix 参数处理字段名冲突
    """
    gdf_s, gdf_t = _align_crs(source, target)
    result = gpd.sjoin(gdf_s, gdf_t, how=how, predicate=predicate)
    result = result[~result.index.duplicated(keep="first")]
    out = GeoLayer(result, name=f"{source.name}_joined", source=source.source)
    out._log_event("spatial_join", f"target={target.name}, how={how}, pred={predicate}")
    return out


def calculate_area(
    layer: GeoLayer,
    column: str = "area",
    unit: str = "km2",
) -> GeoLayer:
    """
    计算面要素面积，新增面积字段。

    先投影到 UTM（米单位）后计算，结果按 unit 换算。

    Args:
        layer : 面要素图层
        column: 存储面积的字段名（默认 'area'）
        unit  : 'km2' | 'm2' | 'ha'（公顷）

    Returns:
        新增面积字段的 GeoLayer

    TODO:
        - [ ] 支持线要素的长度计算 (calculate_length)
        - [ ] 添加面积比例 (pct_of_total) 字段
    """
    utm = _estimate_utm(layer)
    gdf_utm = layer.data.to_crs(utm)
    area_m2 = gdf_utm.geometry.area

    divisors = {"m2": 1, "km2": 1e6, "ha": 1e4}
    divisor = divisors.get(unit, 1e6)

    result = layer.data.copy()
    result[column] = (area_m2 / divisor).round(6).values
    # 始终保留 area_m2 便于内部调用
    result["area_m2"] = area_m2.round(2).values
    out = GeoLayer(result, name=f"{layer.name}_area", source=layer.source)
    out._log_event("calculate_area", f"unit={unit}, column={column}")
    return out


def zonal_stats(
    zones: GeoLayer,
    points: GeoLayer,
    stat: str = "count",
    value_col: Optional[str] = None,
) -> GeoLayer:
    """
    分区统计: 统计每个面区域内点要素的数量或属性值。

    Args:
        zones    : 面要素图层（统计区域）
        points   : 点要素图层（被统计数据源）
        stat     : 统计方式 'count' | 'sum' | 'mean' | 'max' | 'min'
        value_col: 统计字段名（stat != 'count' 时必须提供）

    Returns:
        zones 图层新增统计结果字段的 GeoLayer

    TODO:
        - [ ] 支持多统计字段同时输出 (stat 接受 list)
        - [ ] 支持栅格分区统计 (与 raster_ops 集成)
        - [ ] 处理 zones 与 points CRS 不一致问题（目前已处理但需测试）
    """
    gdf_z, gdf_p = _align_crs(zones, points)

    # BUG FIX: 用 left join（zones 为左表），避免 index_right 找不到的问题
    # 将 points sjoin 到 zones，保留 zones 的所有行
    joined = gpd.sjoin(gdf_p, gdf_z, how="inner", predicate="within")

    stat_col = f"zs_{stat}"
    if stat == "count":
        agg = joined.groupby("index_right").size().rename(stat_col)
    elif value_col is None:
        raise ValueError(f"stat='{stat}' 时需要指定 value_col 字段名")
    else:
        agg_map = {"sum": "sum", "mean": "mean", "max": "max", "min": "min"}
        if stat not in agg_map:
            raise ValueError(f"不支持的 stat='{stat}'。支持: {list(agg_map)}")
        agg = joined.groupby("index_right")[value_col].agg(agg_map[stat]).rename(stat_col)

    result = zones.data.copy()
    result[stat_col] = agg.reindex(result.index, fill_value=0)
    out = GeoLayer(result, name=f"{zones.name}_zonal_{stat}", source=zones.source)
    out._log_event("zonal_stats", f"stat={stat}, points={points.name}")
    return out


def kde(
    layer: GeoLayer,
    bandwidth: float = 0.05,
    grid_size: int = 100,
    extent: Optional[tuple] = None,
    weight_col: Optional[str] = None,
) -> dict:
    """
    核密度估计（Kernel Density Estimation）。

    使用 scipy.stats.gaussian_kde 对点要素进行核密度计算，
    返回二维密度网格（numpy array）及其空间范围。

    Args:
        layer      : 点要素图层（GeoLayer）
        bandwidth  : 核带宽（地理度 / 'scott' / 'silverman'）
        grid_size  : 输出网格分辨率（每边格数）
        extent     : (xmin, ymin, xmax, ymax)，默认使用图层范围扩展 10%
        weight_col : 权重字段名（None 则等权）

    Returns:
        dict:
            'grid'    (np.ndarray): shape (grid_size, grid_size) 密度网格
            'extent'  (tuple)    : (xmin, ymin, xmax, ymax)
            'xx'      (np.ndarray): 网格 X 坐标矩阵
            'yy'      (np.ndarray): 网格 Y 坐标矩阵
    """
    try:
        from scipy.stats import gaussian_kde
    except ImportError:
        raise ImportError("kde() 需要 scipy，请执行: pip install scipy")

    import numpy as np

    gdf = layer.data.copy()
    # 提取坐标（仅保留 Point 类型）
    gdf = gdf[gdf.geometry.geom_type == "Point"]
    if len(gdf) == 0:
        raise ValueError("kde() 需要点图层，当前图层无点要素")

    xs = gdf.geometry.x.values.astype(float)
    ys = gdf.geometry.y.values.astype(float)

    # 构建空间范围
    if extent is None:
        pad_x = (xs.max() - xs.min()) * 0.1 or 0.01
        pad_y = (ys.max() - ys.min()) * 0.1 or 0.01
        xmin, xmax = xs.min() - pad_x, xs.max() + pad_x
        ymin, ymax = ys.min() - pad_y, ys.max() + pad_y
    else:
        xmin, ymin, xmax, ymax = extent

    # 网格坐标
    xi = np.linspace(xmin, xmax, grid_size)
    yi = np.linspace(ymin, ymax, grid_size)
    xx, yy = np.meshgrid(xi, yi)
    positions = np.vstack([xx.ravel(), yy.ravel()])

    # 权重
    weights = None
    if weight_col and weight_col in gdf.columns:
        weights = gdf[weight_col].values.astype(float)
        weights = np.where(np.isnan(weights) | (weights <= 0), 1.0, weights)

    # 核密度计算
    kernel = gaussian_kde(
        np.vstack([xs, ys]),
        bw_method=bandwidth,
        weights=weights,
    )
    grid = kernel(positions).reshape(grid_size, grid_size)

    print(f"  KDE: {len(gdf)} 点, bandwidth={bandwidth}, "
          f"grid={grid_size}×{grid_size}, "
          f"密度范围 [{grid.min():.4f}, {grid.max():.4f}]")

    return {
        "grid":   grid,
        "extent": (xmin, ymin, xmax, ymax),
        "xx":     xx,
        "yy":     yy,
    }
