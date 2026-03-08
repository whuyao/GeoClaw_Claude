# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.primitive_resolver
============================================
地理原语解析器（Phase 2）。

职责：
  从 ReasoningContext（标准化查询 + 数据元信息）中解析出：
    - 地理实体类型（GeoEntityType）
    - 空间关系（SpatialRelation）
    - 目标度量指标（target_metrics）
    - 实体词汇（resolved_entity_names）

  Phase 2 实现：基于多层次规则（关键词 + 数据类型 + 属性字段）进行解析，
  无需 LLM 调用，保证离线稳定性。
  Phase 3 可在此基础上叠加 LLM 深度抽取。

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from geoclaw_claude.reasoning.schemas import (
    GeoEntityType,
    ReasoningContext,
    SpatialRelation,
)

# ══════════════════════════════════════════════════════════════════════════════
#  关键词映射表
# ══════════════════════════════════════════════════════════════════════════════

# 实体类型关键词 → GeoEntityType（中英文）
_ENTITY_KEYWORDS: Dict[str, List[str]] = {
    GeoEntityType.FACILITY.value: [
        "医院", "学校", "站点", "地铁站", "公交站", "消防站", "警察局", "超市", "商场",
        "停车场", "加油站", "公园", "医疗", "教育", "设施", "服务点",
        "hospital", "school", "station", "metro", "bus stop", "facility",
        "clinic", "pharmacy", "shelter", "fire station", "police",
    ],
    GeoEntityType.TRAJECTORY.value: [
        "轨迹", "GPS", "出行", "移动", "行程", "路线", "流", "通勤", "OD", "od",
        "trajectory", "trip", "mobility", "movement", "commute", "flow",
    ],
    GeoEntityType.NETWORK.value: [
        "路网", "道路", "网络", "街道", "管网", "管道", "铁路", "交通网",
        "road", "network", "street", "highway", "railway", "pipe", "grid",
    ],
    GeoEntityType.RASTER.value: [
        "栅格", "影像", "遥感", "DEM", "高程", "NDVI", "地表温度", "热岛",
        "raster", "image", "imagery", "dem", "elevation", "ndvi", "lst",
    ],
    GeoEntityType.POLYGON.value: [
        "多边形", "面", "地块", "区域", "地块", "小区", "街区", "用地",
        "polygon", "parcel", "block", "zone", "district", "boundary",
    ],
    GeoEntityType.REGION.value: [
        "行政区", "街道", "乡镇", "省", "市", "区", "县", "社区",
        "region", "administrative", "township", "province", "city", "county",
    ],
    GeoEntityType.POINT.value: [
        "点", "POI", "兴趣点", "坐标", "位置", "标记",
        "point", "poi", "coordinate", "location", "marker",
    ],
    GeoEntityType.EVENT.value: [
        "事件", "事故", "犯罪", "火灾", "洪涝", "灾害",
        "event", "incident", "accident", "crime", "flood", "disaster",
    ],
    GeoEntityType.LINE.value: [
        "线", "河流", "海岸线", "等高线", "线段",
        "line", "river", "coastline", "contour", "polyline",
    ],
    GeoEntityType.GRID.value: [
        "格网", "格栅", "渔网", "蜂窝格", "栅格化",
        "grid", "fishnet", "hexagon", "tessellation",
    ],
}

# 空间关系关键词 → SpatialRelation
_RELATION_KEYWORDS: Dict[str, List[str]] = {
    SpatialRelation.WITHIN.value: [
        "范围内", "以内", "覆盖", "包含在", "内部", "属于",
        "within", "inside", "coverage", "contained",
    ],
    SpatialRelation.NEAREST.value: [
        "最近", "最邻近", "距离最短", "附近",
        "nearest", "closest", "proximity", "adjacent",
    ],
    SpatialRelation.INTERSECTS.value: [
        "交叉", "相交", "穿越", "重叠",
        "intersect", "cross", "overlap", "traverse",
    ],
    SpatialRelation.ACCESSIBLE_FROM.value: [
        "可达", "通达", "到达", "步行", "驾车", "通勤",
        "accessible", "reachable", "walkable", "drivable",
    ],
    SpatialRelation.CONTAINS.value: [
        "包含", "容纳", "内含",
        "contain", "encompass", "enclose",
    ],
    SpatialRelation.CO_LOCATED_WITH.value: [
        "聚集", "共存", "同区域", "同位",
        "co-located", "collocated", "cluster", "co-occurrence",
    ],
    SpatialRelation.OVERLAPS.value: [
        "叠加", "叠置", "重合",
        "overlay", "overlap", "coincide",
    ],
    SpatialRelation.UPSTREAM.value: [
        "上游", "上风", "来源",
        "upstream", "upwind", "source",
    ],
    SpatialRelation.DOWNSTREAM.value: [
        "下游", "下风", "流向",
        "downstream", "downwind", "sink",
    ],
}

# 目标度量指标关键词
_METRIC_KEYWORDS: Dict[str, List[str]] = {
    "count": ["数量", "个数", "多少", "count", "number", "how many"],
    "density": ["密度", "密集", "密集程度", "density", "concentration"],
    "diversity": ["多样性", "种类", "类别", "diversity", "variety", "category"],
    "distance": ["距离", "远近", "distance", "far", "near"],
    "area": ["面积", "区域大小", "area", "size"],
    "coverage": ["覆盖率", "覆盖", "coverage", "penetration"],
    "accessibility_index": ["可达性指数", "可达性", "accessibility index"],
    "change_rate": ["变化率", "增长率", "变化量", "change", "growth rate", "rate"],
    "ratio": ["比例", "占比", "ratio", "proportion", "percentage"],
    "flow": ["流量", "流向", "flow", "volume", "od flow"],
    "equity": ["公平性", "均等", "不均衡", "equity", "inequality", "fairness"],
    "score": ["评分", "得分", "综合评价", "score", "rating", "index"],
}


# ══════════════════════════════════════════════════════════════════════════════
#  输出结构
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PrimitiveResolution:
    """地理原语解析结果"""
    entities:       List[str]  = field(default_factory=list)   # GeoEntityType values
    relations:      List[str]  = field(default_factory=list)   # SpatialRelation values
    target_metrics: List[str]  = field(default_factory=list)   # metric keys
    entity_names:   List[str]  = field(default_factory=list)   # 原始词汇（如"地铁站"）
    confidence:     float      = 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  主解析函数
# ══════════════════════════════════════════════════════════════════════════════

def resolve_primitives(
    ctx: ReasoningContext,
) -> PrimitiveResolution:
    """
    从 ReasoningContext 中解析地理原语。

    三层解析：
      1. 查询文本关键词匹配
      2. 数据集元信息推断（geometry type / data type）
      3. 属性字段名推断（如字段含 "time" → 时序分析）

    Args:
        ctx: 标准化推理上下文

    Returns:
        PrimitiveResolution
    """
    result = PrimitiveResolution()
    query_lower = (ctx.query or "").lower()

    # ── 1. 文本关键词匹配 ─────────────────────────────────────────────────────
    entities_found: Set[str] = set()
    entity_names: List[str] = []

    for entity_type, keywords in _ENTITY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                entities_found.add(entity_type)
                entity_names.append(kw)

    relations_found: Set[str] = set()
    for rel_type, keywords in _RELATION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                relations_found.add(rel_type)

    metrics_found: Set[str] = set()
    for metric, keywords in _METRIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                metrics_found.add(metric)

    # ── 2. 数据集元信息推断 ───────────────────────────────────────────────────
    for ds in ctx.datasets:
        # 数据类型 → 实体类型
        dtype = (ds.type or "").lower()
        geom = (ds.geometry or "").lower()

        if dtype == "trajectory":
            entities_found.add(GeoEntityType.TRAJECTORY.value)
        elif dtype == "network":
            entities_found.add(GeoEntityType.NETWORK.value)
        elif dtype == "raster":
            entities_found.add(GeoEntityType.RASTER.value)
        elif dtype == "vector":
            if "point" in geom:
                entities_found.add(GeoEntityType.POINT.value)
            elif "line" in geom:
                entities_found.add(GeoEntityType.LINE.value)
            elif "polygon" in geom:
                entities_found.add(GeoEntityType.POLYGON.value)

        # 属性字段名推断
        for attr in ds.attributes:
            attr_lower = attr.lower()
            if any(t in attr_lower for t in ["time", "date", "year", "timestamp", "dt"]):
                if "change_rate" not in metrics_found:
                    metrics_found.add("change_rate")  # 时序暗示变化检测
            if any(t in attr_lower for t in ["pop", "population", "demand", "residents"]):
                metrics_found.add("coverage")
            if any(t in attr_lower for t in ["capacity", "beds", "seats"]):
                metrics_found.add("accessibility_index")

        # 数据集 ID 名称推断
        ds_id_lower = ds.id.lower()
        if any(t in ds_id_lower for t in ["station", "metro", "facility", "hospital", "school"]):
            entities_found.add(GeoEntityType.FACILITY.value)
        if any(t in ds_id_lower for t in ["poi", "commerce", "retail", "shop"]):
            entities_found.add(GeoEntityType.POINT.value)
        if any(t in ds_id_lower for t in ["road", "network", "street"]):
            entities_found.add(GeoEntityType.NETWORK.value)
        if any(t in ds_id_lower for t in ["trajectory", "gps", "trace", "traj"]):
            entities_found.add(GeoEntityType.TRAJECTORY.value)

    # ── 3. geo_terms 补充（由 context_builder 预先抽取）─────────────────────
    for term in ctx.geo_terms:
        term_lower = term.lower()
        for entity_type, keywords in _ENTITY_KEYWORDS.items():
            if term_lower in [kw.lower() for kw in keywords]:
                entities_found.add(entity_type)

    # ── 4. 默认兜底 ───────────────────────────────────────────────────────────
    if not entities_found:
        entities_found.add(GeoEntityType.POINT.value)
    if not relations_found:
        relations_found.add(SpatialRelation.WITHIN.value)
    if not metrics_found:
        metrics_found.add("count")

    # ── 5. 置信度估算 ─────────────────────────────────────────────────────────
    confidence = _estimate_confidence(entities_found, relations_found, metrics_found, ctx)

    result.entities = list(entities_found)
    result.relations = list(relations_found)
    result.target_metrics = list(metrics_found)
    result.entity_names = list(dict.fromkeys(entity_names))  # 去重保序
    result.confidence = confidence

    return result


def _estimate_confidence(
    entities: Set[str],
    relations: Set[str],
    metrics: Set[str],
    ctx: ReasoningContext,
) -> float:
    """简单置信度估算（0-1）"""
    score = 0.0
    if entities:
        score += 0.3
    if relations:
        score += 0.2
    if metrics:
        score += 0.2
    if ctx.datasets:
        score += 0.2
    if ctx.study_area:
        score += 0.1
    return min(score, 1.0)
