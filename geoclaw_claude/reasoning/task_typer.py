# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.task_typer
=====================================
任务类型识别器。

将 ReasoningContext 分类为：
  - AnalysisIntent（9 种分析意图）
  - GeoEntityType（10 种地理实体类型）
  - SpatialRelation（9 种空间关系）
  - OutputType（6 种输出类型）

实现策略（Phase 1）：
  关键词规则匹配（中英文双语）。
  Phase 2 将由 LLM Task Interpreter 取代或辅助本层。

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from geoclaw_claude.reasoning.schemas import (
    AnalysisIntent,
    GeoEntityType,
    OutputType,
    ReasoningContext,
    SpatialRelation,
    TaskProfile,
)


# ══════════════════════════════════════════════════════════════════════════════
#  分析意图关键词规则
#  格式：(中文关键词列表, 英文关键词列表)
# ══════════════════════════════════════════════════════════════════════════════

_INTENT_RULES: List[Tuple[AnalysisIntent, List[str], List[str]]] = [
    (AnalysisIntent.CHANGE_DETECTION,
     ["变化", "变迁", "扩张", "增减", "历年", "前后对比", "时序", "时间序列", "动态"],
     ["change", "detection", "temporal", "expansion", "growth", "transition", "before after"]),

    (AnalysisIntent.OPTIMIZATION,
     ["选址", "最优", "优化", "规划", "配置", "最大覆盖", "最小距离", "选点"],
     ["site selection", "optimization", "optimal", "allocation", "location-allocation",
      "coverage", "best location"]),

    (AnalysisIntent.ACCESSIBILITY,
     ["可达性", "可达", "服务范围", "服务区", "等时圈", "通达", "到达时间", "交通时间"],
     ["accessibility", "reachability", "service area", "isochrone", "travel time",
      "catchment", "coverage area"]),

    (AnalysisIntent.CLUSTERING,
     ["聚集", "集聚", "热点", "冷点", "空间分布", "聚类", "集中", "离散", "密度"],
     ["cluster", "hotspot", "spatial distribution", "density", "kde",
      "kernel density", "concentration"]),

    (AnalysisIntent.COMPARISON,
     ["比较", "对比", "差异", "排名", "排序", "相比", "高于", "低于", "差距"],
     ["compare", "comparison", "difference", "rank", "contrast", "versus", "higher", "lower"]),

    (AnalysisIntent.PREDICTION,
     ["预测", "预估", "模拟", "推演", "未来", "趋势预测", "机器学习"],
     ["predict", "prediction", "forecast", "simulate", "model", "future trend"]),

    (AnalysisIntent.EXPLANATION,
     ["解释", "原因", "为什么", "影响因素", "相关性", "回归", "驱动力"],
     ["explain", "why", "reason", "factor", "correlation", "regression", "driver"]),

    (AnalysisIntent.SUMMARIZATION,
     ["统计", "汇总", "总结", "概况", "概览", "分布情况", "整体"],
     ["summarize", "summary", "statistics", "overview", "distribution", "general"]),

    # 最后兜底：proximity / selection
    (AnalysisIntent.SELECTION,
     ["筛选", "过滤", "选取", "找出", "识别", "哪些", "查找"],
     ["select", "filter", "find", "identify", "which", "query"]),
]

# proximity 不在枚举里，但文档中大量使用，映射到 COMPARISON 或 CLUSTERING
_PROXIMITY_KEYWORDS_ZH = ["周边", "附近", "周围", "缓冲区", "距离", "邻近", "最近"]
_PROXIMITY_KEYWORDS_EN = ["proximity", "buffer", "distance", "nearby", "adjacent", "nearest"]


# ══════════════════════════════════════════════════════════════════════════════
#  地理实体类型关键词规则
# ══════════════════════════════════════════════════════════════════════════════

_ENTITY_RULES: List[Tuple[GeoEntityType, List[str], List[str]]] = [
    (GeoEntityType.TRAJECTORY,
     ["轨迹", "GPS", "移动", "出行", "OD", "位置序列", "签到"],
     ["trajectory", "gps", "mobility", "trip", "od matrix", "check-in", "movement"]),

    (GeoEntityType.NETWORK,
     ["道路网", "路网", "交通网", "管网", "网络分析"],
     ["road network", "network", "routing", "graph", "topology"]),

    (GeoEntityType.RASTER,
     ["栅格", "DEM", "影像", "遥感", "高程", "坡度", "像素"],
     ["raster", "dem", "image", "remote sensing", "elevation", "slope", "pixel", "grid"]),

    (GeoEntityType.REGION,
     ["区域", "行政区", "省", "市", "县", "街道", "社区", "分区"],
     ["region", "district", "administrative", "zone", "area", "boundary"]),

    (GeoEntityType.FACILITY,
     ["设施", "医院", "学校", "公园", "商场", "站点", "AED", "消防站"],
     ["facility", "hospital", "school", "park", "station", "aed", "fire station"]),

    (GeoEntityType.POLYGON,
     ["面", "多边形", "地块", "建筑轮廓", "用地"],
     ["polygon", "parcel", "footprint", "land use"]),

    (GeoEntityType.LINE,
     ["线", "路段", "管线", "河流", "道路"],
     ["line", "linestring", "road", "river", "pipe"]),

    (GeoEntityType.POINT,
     ["点", "位置", "坐标", "POI", "地铁站", "公交站"],
     ["point", "location", "coordinate", "poi", "station"]),
]


# ══════════════════════════════════════════════════════════════════════════════
#  空间关系关键词规则
# ══════════════════════════════════════════════════════════════════════════════

_RELATION_RULES: List[Tuple[SpatialRelation, List[str], List[str]]] = [
    (SpatialRelation.WITHIN,
     ["以内", "内部", "范围内", "在…内", "包含于"],
     ["within", "inside", "contained in"]),

    (SpatialRelation.NEAREST,
     ["最近", "最近的", "距离最短", "最邻近"],
     ["nearest", "closest", "nearest neighbor"]),

    (SpatialRelation.ACCESSIBLE_FROM,
     ["可达", "能到达", "通达", "步行可达", "驾车可达"],
     ["accessible", "reachable", "within walk", "drivable"]),

    (SpatialRelation.INTERSECTS,
     ["穿过", "相交", "跨越", "经过"],
     ["intersect", "cross", "traverse", "pass through"]),

    (SpatialRelation.OVERLAPS,
     ["叠加", "重叠", "交叉", "覆盖"],
     ["overlap", "overlay", "cover"]),

    (SpatialRelation.CO_LOCATED_WITH,
     ["共同出现", "同一区域", "空间共现", "协同分布"],
     ["co-located", "co-occurrence", "spatial co-presence"]),
]


# ══════════════════════════════════════════════════════════════════════════════
#  输出类型关键词规则
# ══════════════════════════════════════════════════════════════════════════════

_OUTPUT_RULES: List[Tuple[OutputType, List[str], List[str]]] = [
    (OutputType.MAP,
     ["地图", "可视化", "制图", "分布图", "热力图", "示意图"],
     ["map", "visualize", "visualization", "plot"]),

    (OutputType.TABLE,
     ["表格", "统计表", "数据表", "汇总表", "排名表"],
     ["table", "spreadsheet", "statistics", "ranking"]),

    (OutputType.REPORT,
     ["报告", "摘要", "总结", "分析报告"],
     ["report", "summary", "analysis report"]),

    (OutputType.GEOFILE,
     ["shapefile", "geojson", "数据文件", "空间数据", "输出文件"],
     ["shapefile", "geojson", "geopackage", "output file", "geofile"]),

    (OutputType.WORKFLOW,
     ["工作流", "流程", "步骤", "可复现"],
     ["workflow", "pipeline", "steps", "reproducible"]),
]


# ══════════════════════════════════════════════════════════════════════════════
#  主函数
# ══════════════════════════════════════════════════════════════════════════════

def classify_task(ctx: ReasoningContext) -> TaskProfile:
    """
    对推理上下文进行任务类型识别。

    Args:
        ctx: 预处理后的 ReasoningContext

    Returns:
        TaskProfile — 含意图、实体、关系、输出类型、置信度
    """
    query = ctx.query
    lang  = ctx.normalized_language

    # 1. 识别分析意图（含 proximity 特殊处理）
    intents, confidence = _classify_intents(query, lang, ctx)

    primary_intent = intents[0] if intents else AnalysisIntent.UNKNOWN
    sub_intents    = intents[1:] if len(intents) > 1 else []

    # 2. 识别地理实体类型（从 query + datasets）
    entities = _classify_entities(query, lang, ctx)

    # 3. 识别空间关系
    relations = _classify_relations(query, lang)

    # 4. 识别输出类型
    outputs = _classify_outputs(query, lang, ctx)

    # 5. 领域推断
    domain = _infer_domain(query, lang, ctx)

    return TaskProfile(
        task_type     = primary_intent,
        subtask_types = sub_intents,
        entities      = entities,
        relations     = relations,
        domain        = domain,
        analysis_goal = ctx.project_context.analysis_goal,
        output_intent = outputs,
        confidence    = confidence,
    )


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────

def _score_query(query: str, lang: str,
                 zh_kws: List[str], en_kws: List[str]) -> int:
    """计算关键词命中得分"""
    score = 0
    if lang == "zh":
        for kw in zh_kws:
            if kw in query:
                score += 1
    else:
        query_lower = query.lower()
        for kw in en_kws:
            if kw in query_lower:
                score += 1
    return score


def _classify_intents(
    query: str,
    lang: str,
    ctx: ReasoningContext,
) -> Tuple[List[AnalysisIntent], float]:
    """识别分析意图，返回 (有序意图列表, 置信度)"""
    scores: Dict[AnalysisIntent, int] = {}

    # 规则评分
    for intent, zh_kws, en_kws in _INTENT_RULES:
        s = _score_query(query, lang, zh_kws, en_kws)
        if s > 0:
            scores[intent] = s

    # proximity 特殊：映射到 COMPARISON（站点周边比较）或 CLUSTERING（密度）
    prox_score = _score_query(query, lang, _PROXIMITY_KEYWORDS_ZH, _PROXIMITY_KEYWORDS_EN)
    if prox_score > 0:
        # 如果已有 COMPARISON，加权；否则单独加
        if AnalysisIntent.COMPARISON in scores:
            scores[AnalysisIntent.COMPARISON] += prox_score
        elif AnalysisIntent.CLUSTERING in scores:
            scores[AnalysisIntent.CLUSTERING] += prox_score
        else:
            # 新增 COMPARISON（proximity 的默认语义）
            scores[AnalysisIntent.COMPARISON] = scores.get(
                AnalysisIntent.COMPARISON, 0) + prox_score

    # Planner hints 加权
    hint_type = ctx.planner_hints.candidate_task_type
    if hint_type:
        for intent in AnalysisIntent:
            if intent.value in hint_type.lower():
                scores[intent] = scores.get(intent, 0) + 2

    if not scores:
        return [AnalysisIntent.UNKNOWN], 0.1

    # 按得分降序排列
    sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_intents    = [i for i, _ in sorted_intents if _ > 0]

    # 置信度：top 分与总分之比
    total = sum(scores.values())
    top_s = sorted_intents[0][1]
    confidence = min(top_s / max(total, 1), 1.0)
    # 若只有一种意图且得分 ≥ 2，置信度上调
    if len(top_intents) == 1 and top_s >= 2:
        confidence = min(confidence + 0.2, 1.0)

    return top_intents, round(confidence, 2)


def _classify_entities(
    query: str,
    lang: str,
    ctx: ReasoningContext,
) -> List[GeoEntityType]:
    """识别地理实体类型"""
    found: Dict[GeoEntityType, int] = {}

    # 从 query 关键词识别
    for etype, zh_kws, en_kws in _ENTITY_RULES:
        s = _score_query(query, lang, zh_kws, en_kws)
        if s > 0:
            found[etype] = s

    # 从 datasets 类型推断
    for ds in ctx.datasets:
        ds_type = ds.type.lower() if ds.type else ""
        geom    = (ds.geometry or "").lower()
        if "trajectory" in ds_type or "gps" in ds_type:
            found[GeoEntityType.TRAJECTORY] = found.get(GeoEntityType.TRAJECTORY, 0) + 1
        elif "raster" in ds_type or "dem" in ds_type:
            found[GeoEntityType.RASTER] = found.get(GeoEntityType.RASTER, 0) + 1
        elif "network" in ds_type:
            found[GeoEntityType.NETWORK] = found.get(GeoEntityType.NETWORK, 0) + 1
        elif "point" in geom:
            found[GeoEntityType.POINT] = found.get(GeoEntityType.POINT, 0) + 1
        elif "polygon" in geom or "multipolygon" in geom:
            found[GeoEntityType.POLYGON] = found.get(GeoEntityType.POLYGON, 0) + 1
        elif "line" in geom:
            found[GeoEntityType.LINE] = found.get(GeoEntityType.LINE, 0) + 1

    # 按得分降序
    return [e for e, _ in sorted(found.items(), key=lambda x: x[1], reverse=True)]


def _classify_relations(query: str, lang: str) -> List[SpatialRelation]:
    """识别空间关系"""
    found: Dict[SpatialRelation, int] = {}
    for rel, zh_kws, en_kws in _RELATION_RULES:
        s = _score_query(query, lang, zh_kws, en_kws)
        if s > 0:
            found[rel] = s
    return [r for r, _ in sorted(found.items(), key=lambda x: x[1], reverse=True)]


def _classify_outputs(
    query: str,
    lang: str,
    ctx: ReasoningContext,
) -> List[OutputType]:
    """识别期望输出类型"""
    found: Dict[OutputType, int] = {}

    for otype, zh_kws, en_kws in _OUTPUT_RULES:
        s = _score_query(query, lang, zh_kws, en_kws)
        if s > 0:
            found[otype] = s

    # 从 user_context.output_preference 补充
    for pref in ctx.user_context.output_preference:
        for otype in OutputType:
            if otype.value in pref.lower():
                found[otype] = found.get(otype, 0) + 1

    # 若什么都没识别，默认 MAP + REPORT
    if not found:
        return [OutputType.MAP, OutputType.REPORT]

    return [o for o, _ in sorted(found.items(), key=lambda x: x[1], reverse=True)]


def _infer_domain(query: str, lang: str, ctx: ReasoningContext) -> str:
    """推断分析领域"""
    domain_keywords: Dict[str, List[str]] = {
        "urban_computing":    ["城市", "地铁", "公交", "轨道", "商业", "住宅", "建设用地"],
        "ecology":            ["生态", "植被", "森林", "湿地", "生物多样性"],
        "transportation":     ["交通", "路网", "拥堵", "出行", "OD"],
        "public_health":      ["医疗", "卫生", "疾病", "健康", "医院", "AED"],
        "disaster_risk":      ["灾害", "洪涝", "地震", "风险", "防灾"],
        "land_use":           ["土地", "用地", "地块", "地类"],
    }
    for domain, kws in domain_keywords.items():
        if any(kw in query for kw in kws):
            return domain
    if ctx.project_context.analysis_goal:
        goal_l = ctx.project_context.analysis_goal.lower()
        for domain, kws in domain_keywords.items():
            if any(kw.lower() in goal_l for kw in kws):
                return domain
    return "general"
