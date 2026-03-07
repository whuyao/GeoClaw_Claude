# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude/analysis/mobility/metrics.py
=============================================
人类移动性定量指标计算

指标体系:
  个体移动性:
    - radius_of_gyration   回转半径（活动范围大小）
    - jump_length          跳跃距离分布（出行距离统计）
    - modal_split          交通方式占比
    - home_work_detection  家/工作地识别

  群体质量:
    - tracking_quality     轨迹追踪覆盖率
    - temporal_coverage    时间覆盖统计

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

import geopandas as gpd
import pandas as pd
import numpy as np


def _require_trackintel():
    try:
        import trackintel as ti
        return ti
    except ImportError:
        raise ImportError("trackintel 未安装，请运行: pip install trackintel")


# ── 个体移动性指标 ────────────────────────────────────────────────────────────

def radius_of_gyration(
    staypoints: gpd.GeoDataFrame,
    method: str = "count",
    print_progress: bool = False,
) -> pd.DataFrame:
    """
    计算用户的回转半径（Radius of Gyration, RoG）。

    回转半径反映用户的整体活动范围大小：
      - 数值大 → 活动范围广（频繁长途出行）
      - 数值小 → 活动范围窄（本地化生活模式）

    基于停留点与其重心的加权均方根距离计算。

    Args:
        staypoints    : 含 user_id、geometry 的停留点
        method        : 权重方法
                        'count'    按访问次数加权
                        'duration' 按停留时长加权
        print_progress: 是否显示进度

    Returns:
        DataFrame，列: user_id, radius_of_gyration（单位：米）
    """
    ti = _require_trackintel()
    result = ti.analysis.radius_gyration(staypoints, method=method,
                                          print_progress=print_progress)
    return result.reset_index()


def jump_lengths(
    staypoints: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    计算停留点间的跳跃距离分布（出行距离统计）。

    跳跃距离：相邻两个停留点之间的直线距离（米），
    反映用户的单次出行距离特征。

    Args:
        staypoints: 含 user_id、geometry 的停留点

    Returns:
        DataFrame，列: user_id, jump_length（单位：米）
    """
    ti = _require_trackintel()
    result = ti.analysis.jump_length(staypoints)
    return result.reset_index()


def modal_split(
    triplegs: gpd.GeoDataFrame,
    *,
    metric: str = "count",
    per_user: bool = False,
) -> pd.DataFrame:
    """
    计算出行方式构成（Modal Split）。

    统计各交通方式（步行/自行车/汽车/火车）在所有出行中的占比。

    前提：triplegs 已包含 mode 列（通过 predict_transport_mode 生成）。

    Args:
        triplegs : 含 mode 列的出行段
        metric   : 统计口径
                   'count'    按出行次数
                   'duration' 按出行时长
                   'distance' 按出行距离
        per_user : True 则分用户计算，False 则汇总全体

    Returns:
        出行方式占比 DataFrame
    """
    ti = _require_trackintel()
    if "mode" not in triplegs.columns:
        raise ValueError(
            "triplegs 缺少 mode 列，请先运行 predict_transport_mode()"
        )
    result = ti.analysis.calculate_modal_split(
        triplegs, metric=metric, per_user=per_user
    )
    return result


def tracking_quality(
    source: gpd.GeoDataFrame,
    granularity: str = "all",
) -> pd.DataFrame:
    """
    计算轨迹数据的时间覆盖率（Tracking Quality）。

    反映数据完整性：在观测时间段内，有 GPS 数据覆盖的时间比例。
    数值越高 → 数据越完整，缺失越少。

    Args:
        source     : positionfixes 或 triplegs
        granularity: 统计粒度
                     'all'   总体覆盖率
                     'day'   按天统计
                     'week'  按周统计
                     'weekday' 按工作日/周末

    Returns:
        DataFrame，列: user_id, tracking_quality（0~1）
    """
    ti = _require_trackintel()
    # positionfixes 用 tracked_at；staypoints/triplegs 用 started_at/finished_at
    if "tracked_at" in source.columns and "started_at" not in source.columns:
        # 转换 positionfixes 为可供 tracking_quality 使用的格式
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            src = source.copy()
            src["started_at"]  = src["tracked_at"]
            src["finished_at"] = src["tracked_at"]
            return ti.analysis.temporal_tracking_quality(src, granularity=granularity)
    return ti.analysis.temporal_tracking_quality(source, granularity=granularity)


def mobility_summary(
    hierarchy: dict,
    *,
    user_id: Optional[Union[int, str]] = None,
) -> Dict:
    """
    生成用户移动性综合摘要报告。

    汇总回转半径、跳跃距离、出行方式、数据质量等核心指标。

    Args:
        hierarchy: generate_full_hierarchy() 的返回值
        user_id  : 筛选特定用户（None 则汇总所有用户）

    Returns:
        摘要字典，含各项移动性指标统计
    """
    sp   = hierarchy.get("staypoints",    gpd.GeoDataFrame())
    tpls = hierarchy.get("triplegs",      gpd.GeoDataFrame())
    locs = hierarchy.get("locations",     gpd.GeoDataFrame())
    pfs  = hierarchy.get("positionfixes", gpd.GeoDataFrame())

    if user_id is not None:
        sp   = sp[sp.user_id == user_id]   if len(sp)   else sp
        tpls = tpls[tpls.user_id == user_id] if len(tpls) else tpls

    summary = {
        "n_users":       int(sp["user_id"].nunique()) if len(sp) else 0,
        "n_positionfixes": len(pfs),
        "n_staypoints":  len(sp),
        "n_triplegs":    len(tpls),
        "n_locations":   len(locs),
    }

    # 时间跨度
    if len(sp) and "started_at" in sp.columns:
        summary["time_range"] = {
            "start": str(sp["started_at"].min()),
            "end":   str(sp["finished_at"].max() if "finished_at" in sp.columns
                         else sp["started_at"].max()),
        }

    # 回转半径
    try:
        rog = radius_of_gyration(sp)
        summary["radius_of_gyration_m"] = {
            "mean":   float(rog["radius_gyration"].mean()),
            "median": float(rog["radius_gyration"].median()),
            "max":    float(rog["radius_gyration"].max()),
        }
    except Exception:
        pass

    # 跳跃距离
    try:
        jl = jump_lengths(sp)
        summary["jump_length_m"] = {
            "mean":   float(jl["jump_length"].mean()),
            "median": float(jl["jump_length"].median()),
            "p90":    float(jl["jump_length"].quantile(0.9)),
        }
    except Exception:
        pass

    # 出行方式
    if len(tpls) and "mode" in tpls.columns:
        try:
            ms = tpls["mode"].value_counts(normalize=True).round(3).to_dict()
            summary["modal_split"] = ms
        except Exception:
            pass

    # 数据质量
    try:
        tq = tracking_quality(pfs if len(pfs) else tpls)
        summary["tracking_quality_mean"] = float(
            tq["tracking_quality"].mean() if "tracking_quality" in tq.columns
            else tq.iloc[:, -1].mean()
        )
    except Exception:
        pass

    return summary


# ── 地点语义识别 ──────────────────────────────────────────────────────────────

def identify_home_work(
    staypoints: gpd.GeoDataFrame,
    locations: gpd.GeoDataFrame,
    *,
    method: str = "osna",
) -> gpd.GeoDataFrame:
    """
    识别用户的家（home）和工作地（work）。

    方法:
      'osna' : 基于在线社交网络作息模式（夜间→家，工作日白天→工作地）
      'freq' : 基于访问频率（访问最多→家或工作地）

    Args:
        staypoints: 停留点（需含 started_at / finished_at）
        locations : 地点
        method    : 识别方法（'osna' / 'freq'）

    Returns:
        含 purpose 列的地点 GeoDataFrame（'home' / 'work' / None）
    """
    ti = _require_trackintel()
    if method == "osna":
        identifier = ti.analysis.osna_method
    elif method == "freq":
        identifier = ti.analysis.freq_method
    else:
        raise ValueError(f"未知方法: {method}，支持 'osna' / 'freq'")

    sp_labeled, locs_labeled = ti.analysis.location_identifier(
        staypoints, locations, identifier
    )
    return locs_labeled
