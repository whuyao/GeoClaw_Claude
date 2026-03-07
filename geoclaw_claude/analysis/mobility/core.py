# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude/analysis/mobility/core.py
==========================================
人类移动性数据核心处理模块（基于 trackintel）

数据层级模型:
  positionfixes (GPS 原始轨迹点)
      ↓ generate_staypoints()
  staypoints   (停留点：停留超过阈值时间的位置)
      ↓ generate_triplegs()
  triplegs     (出行段：两个停留点之间的连续移动)
      ↓ generate_trips()
  trips        (出行：相邻活动停留点间的所有出行段组合)
      ↓ generate_locations()
  locations    (地点：多次访问的聚类重要地点，如家/工作地)

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional, Tuple, Union

import geopandas as gpd
import pandas as pd


def _require_trackintel():
    try:
        import trackintel as ti
        return ti
    except ImportError:
        raise ImportError(
            "trackintel 未安装，请运行: pip install trackintel\n"
            "详情: https://github.com/mie-lab/trackintel"
        )


# ── 数据读入 ──────────────────────────────────────────────────────────────────

def read_positionfixes(
    source: Union[str, Path, gpd.GeoDataFrame, pd.DataFrame],
    *,
    user_id_col:  str = "user_id",
    tracked_at_col: str = "tracked_at",
    lon_col: str = "longitude",
    lat_col: str = "latitude",
    crs: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    """
    读入 GPS 轨迹点（positionfixes），规范化为 trackintel 格式。

    支持:
      - CSV 文件路径（含经纬度列）
      - GeoDataFrame（含 geometry 列）
      - 普通 DataFrame（自动从经纬度构建 geometry）

    Args:
        source        : 数据源（文件路径 / GeoDataFrame / DataFrame）
        user_id_col   : 用户ID列名
        tracked_at_col: 时间戳列名
        lon_col       : 经度列名（DataFrame 时使用）
        lat_col       : 纬度列名（DataFrame 时使用）
        crs           : 坐标参考系

    Returns:
        符合 trackintel 格式的 positionfixes GeoDataFrame
        必含列: geometry, tracked_at, user_id
    """
    ti = _require_trackintel()

    # ── 读取数据 ──────────────────────────────────────────────────────────────
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
            return read_positionfixes(
                df, user_id_col=user_id_col, tracked_at_col=tracked_at_col,
                lon_col=lon_col, lat_col=lat_col, crs=crs
            )
        elif path.suffix.lower() in (".geojson", ".json", ".gpkg", ".shp"):
            gdf = gpd.read_file(path)
            return read_positionfixes(gdf, user_id_col=user_id_col,
                                       tracked_at_col=tracked_at_col, crs=crs)
        else:
            raise ValueError(f"不支持的文件格式: {path.suffix}")

    if isinstance(source, pd.DataFrame) and not isinstance(source, gpd.GeoDataFrame):
        # 从经纬度构建 geometry
        if lon_col not in source.columns or lat_col not in source.columns:
            raise ValueError(f"DataFrame 中找不到经纬度列: {lon_col}, {lat_col}")
        from shapely.geometry import Point
        gdf = gpd.GeoDataFrame(
            source,
            geometry=[Point(xy) for xy in zip(source[lon_col], source[lat_col])],
            crs=crs,
        )
    else:
        gdf = source.copy()
        if gdf.crs is None:
            gdf.set_crs(crs, inplace=True)

    # ── 列名规范化 ────────────────────────────────────────────────────────────
    rename = {}
    if user_id_col != "user_id" and user_id_col in gdf.columns:
        rename[user_id_col] = "user_id"
    if tracked_at_col != "tracked_at" and tracked_at_col in gdf.columns:
        rename[tracked_at_col] = "tracked_at"
    if rename:
        gdf = gdf.rename(columns=rename)

    # 确保 user_id 存在
    if "user_id" not in gdf.columns:
        gdf["user_id"] = 0

    # 确保 tracked_at 是 datetime（带时区）
    if "tracked_at" in gdf.columns:
        gdf["tracked_at"] = pd.to_datetime(gdf["tracked_at"], utc=True, format="mixed")

    # 设置索引
    if gdf.index.name != "id":
        gdf.index.name = "id"

    # 导入 trackintel 格式验证
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pfs = ti.io.read_positionfixes_gpd(gdf, geom_col="geometry", crs=crs)

    return pfs


def read_positionfixes_csv(
    path: Union[str, Path],
    *,
    sep: str = ",",
    **kwargs,
) -> gpd.GeoDataFrame:
    """直接读取 trackintel 标准格式 CSV 文件。"""
    ti = _require_trackintel()
    return ti.io.read_positionfixes_csv(str(path), sep=sep, **kwargs)


# ── 数据层级生成 ──────────────────────────────────────────────────────────────

def generate_staypoints(
    positionfixes: gpd.GeoDataFrame,
    *,
    dist_threshold: float = 100.0,
    time_threshold: float = 5.0,
    gap_threshold: float = 15.0,
    method: str = "sliding",
    n_jobs: int = 1,
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    从 GPS 轨迹点生成停留点（staypoints）。

    停留点定义：用户在某位置停留时间超过 time_threshold（分钟），
    且在该时间段内移动距离不超过 dist_threshold（米）。

    Args:
        positionfixes : GPS 轨迹点（来自 read_positionfixes）
        dist_threshold: 停留判定空间阈值（米），默认 100
        time_threshold: 停留判定时间阈值（分钟），默认 5
        gap_threshold : 数据缺口阈值（分钟），超过则认为数据中断，默认 15
        method        : 检测方法（'sliding' 滑动窗口）
        n_jobs        : 并行进程数（-1 使用全部 CPU）

    Returns:
        (positionfixes_updated, staypoints)
        staypoints 含列: geometry, started_at, finished_at, user_id
    """
    ti = _require_trackintel()
    pfs, sp = positionfixes.generate_staypoints(
        method=method,
        dist_threshold=dist_threshold,
        time_threshold=time_threshold,
        gap_threshold=gap_threshold,
        n_jobs=n_jobs,
    )
    return pfs, sp


def generate_triplegs(
    positionfixes: gpd.GeoDataFrame,
    staypoints: gpd.GeoDataFrame,
    *,
    gap_threshold: float = 15.0,
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    从停留点间的轨迹点生成出行段（triplegs）。

    出行段：两个停留点之间的连续移动轨迹，
    不含具体交通方式（需通过 predict_transport_mode 进一步标注）。

    Args:
        positionfixes: GPS 轨迹点（已生成停留点后的版本）
        staypoints   : 停留点
        gap_threshold: 数据缺口阈值（分钟）

    Returns:
        (positionfixes_updated, triplegs)
        triplegs 含列: geometry (LineString), started_at, finished_at, user_id
    """
    ti = _require_trackintel()
    pfs, tpls = positionfixes.generate_triplegs(
        staypoints, gap_threshold=gap_threshold
    )
    return pfs, tpls


def generate_trips(
    staypoints: gpd.GeoDataFrame,
    triplegs: gpd.GeoDataFrame,
    *,
    gap_threshold: float = 15.0,
    add_geometry: bool = True,
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    从停留点 + 出行段生成完整出行（trips）。

    出行：相邻两个活动停留点之间的所有出行段，
    代表一次完整的从 A 到 B 的出行过程。

    Args:
        staypoints   : 停留点
        triplegs     : 出行段
        gap_threshold: 缺口阈值（分钟）
        add_geometry : 是否生成出行路径几何

    Returns:
        (staypoints_updated, triplegs_updated, trips)
    """
    ti = _require_trackintel()
    # trackintel ≥1.3 需要 is_activity 列
    sp_in = staypoints
    if "is_activity" not in sp_in.columns:
        sp_in = sp_in.copy()
        sp_in["is_activity"] = True
    sp, tpls, trips = ti.preprocessing.generate_trips(
        sp_in, triplegs, gap_threshold=gap_threshold, add_geometry=add_geometry
    )
    return sp, tpls, trips


def generate_locations(
    staypoints: gpd.GeoDataFrame,
    *,
    epsilon: float = 100.0,
    num_samples: int = 1,
    method: str = "dbscan",
    activities_only: bool = False,
    agg_level: str = "user",
    n_jobs: int = 1,
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    从停留点聚类生成重要地点（locations）。

    地点定义：被用户多次访问的空间位置集合（如家、工作地、常去餐厅）。
    使用 DBSCAN 聚类算法识别。

    Args:
        staypoints    : 停留点
        epsilon       : DBSCAN 空间聚类半径（米），默认 100
        num_samples   : 最小样本数（形成地点所需的最少停留次数），默认 1
        method        : 聚类方法（'dbscan'）
        activities_only: 仅对活动停留点聚类
        agg_level     : 聚合层级（'user' 按用户，'dataset' 全局）
        n_jobs        : 并行数

    Returns:
        (staypoints_with_location_id, locations)
        locations 含列: geometry (center), user_id, location_id
    """
    ti = _require_trackintel()
    sp, locs = ti.preprocessing.generate_locations(
        staypoints,
        method=method,
        epsilon=epsilon,
        num_samples=num_samples,
        agg_level=agg_level,
        activities_only=activities_only,
        n_jobs=n_jobs,
    )
    return sp, locs


def generate_full_hierarchy(
    positionfixes: gpd.GeoDataFrame,
    *,
    dist_threshold: float = 100.0,
    time_threshold: float = 5.0,
    gap_threshold: float = 15.0,
    location_epsilon: float = 100.0,
    predict_mode: bool = True,
) -> dict:
    """
    一键生成完整的移动性数据层级结构。

    从原始 GPS 轨迹点，自动依次生成：
    positionfixes → staypoints → triplegs → trips → locations

    Args:
        positionfixes    : 原始 GPS 轨迹点
        dist_threshold   : 停留空间阈值（米）
        time_threshold   : 停留时间阈值（分钟）
        gap_threshold    : 数据缺口阈值（分钟）
        location_epsilon : 地点聚类半径（米）
        predict_mode     : 是否自动预测出行方式

    Returns:
        dict，含键: positionfixes, staypoints, triplegs, trips, locations
    """
    print("[Mobility] 生成停留点...")
    pfs, sp = generate_staypoints(
        positionfixes,
        dist_threshold=dist_threshold,
        time_threshold=time_threshold,
        gap_threshold=gap_threshold,
    )

    print(f"[Mobility] 生成出行段...  停留点: {len(sp)}")
    pfs, tpls = generate_triplegs(pfs, sp, gap_threshold=gap_threshold)

    # 标注活动停留点（用于生成 trips）
    if "activity" not in sp.columns:
        sp = sp.copy()
        sp["activity"] = True

    print(f"[Mobility] 生成出行...    出行段: {len(tpls)}")
    # generate_trips 需要 is_activity 列（trackintel ≥1.3 要求）
    if "is_activity" not in sp.columns:
        sp = sp.copy()
        sp["is_activity"] = True
    sp, tpls, trips = generate_trips(sp, tpls, gap_threshold=gap_threshold)

    print(f"[Mobility] 生成地点...    出行: {len(trips)}")
    sp, locs = generate_locations(sp, epsilon=location_epsilon)

    if predict_mode and len(tpls) > 0:
        print("[Mobility] 预测出行方式...")
        try:
            tpls = predict_transport_mode(tpls)
        except Exception as e:
            print(f"[Mobility] 出行方式预测跳过: {e}")

    print(f"[Mobility] 完成: {len(pfs)} pf | {len(sp)} sp | "
          f"{len(tpls)} tpl | {len(trips)} trips | {len(locs)} locs")

    return {
        "positionfixes": pfs,
        "staypoints":    sp,
        "triplegs":      tpls,
        "trips":         trips,
        "locations":     locs,
    }


# ── 出行方式 ──────────────────────────────────────────────────────────────────

def predict_transport_mode(
    triplegs: gpd.GeoDataFrame,
    method: str = "simple-coarse",
) -> gpd.GeoDataFrame:
    """
    基于速度特征预测出行方式（交通模式）。

    方法:
      'simple-coarse'  : 基于平均速度简单分类（步行/自行车/汽车/火车）
      'simple-combined': 结合速度+加速度的精细分类

    出行方式标签:
      walk（步行）/ bike（自行车）/ car（汽车）/ train（火车）/ unknown

    Args:
        triplegs: 出行段
        method  : 预测方法

    Returns:
        含 mode 列的出行段 GeoDataFrame
    """
    ti = _require_trackintel()
    return ti.analysis.predict_transport_mode(triplegs, method=method)


def label_activity_staypoints(
    staypoints: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    标注停留点的活动语义（是否为有目的停留）。

    Args:
        staypoints: 停留点

    Returns:
        含 activity 布尔列的停留点
    """
    ti = _require_trackintel()
    return ti.analysis.create_activity_flag(staypoints)
