# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.reasoning.context_builder
=====================================
ReasoningInput → ReasoningContext 预处理层。

预处理任务（文档 1.3）：
  1. 语言标准化（zh-CN / en-US → "zh" / "en"）
  2. 地理术语抽取（城市名、行政区、地物类型等）
  3. 数据元信息补齐（推断缺失字段）
  4. 查询歧义标记
  5. 将 Planner hints 结构化
  6. 研究区 / 时间范围对齐

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import re
from typing import List, Optional

from geoclaw_claude.reasoning.schemas import (
    ReasoningContext,
    ReasoningInput,
)


# ── 常用地名词典（轻量，可后续从文件加载扩展）─────────────────────────────────
_CITY_NAMES_ZH = {
    "武汉", "上海", "北京", "广州", "深圳", "成都", "重庆", "杭州",
    "南京", "西安", "天津", "苏州", "长沙", "郑州", "青岛", "济南",
    "合肥", "福州", "昆明", "哈尔滨", "大连", "厦门", "宁波", "无锡",
}

_CITY_NAMES_EN = {
    "wuhan", "shanghai", "beijing", "guangzhou", "shenzhen", "chengdu",
    "chongqing", "hangzhou", "nanjing", "xi'an", "xian", "tianjin",
    "london", "new york", "paris", "tokyo", "berlin", "sydney",
}

# 地物类型词汇
_GEO_FEATURE_TERMS_ZH = {
    "地铁站", "公交站", "医院", "学校", "公园", "商场", "超市",
    "餐厅", "POI", "道路", "河流", "建筑", "土地", "用地",
    "居住区", "行政区", "社区", "网格", "格网", "站点",
    "轨道交通", "地铁线", "铁路",
}

_GEO_FEATURE_TERMS_EN = {
    "station", "hospital", "school", "park", "mall", "road", "river",
    "building", "land", "poi", "transit", "subway", "metro", "district",
    "neighborhood", "grid", "facility", "network",
}

# 分析方法词汇（用于辅助任务类型识别）
_ANALYSIS_TERMS_ZH = {
    "缓冲区", "核密度", "叠加", "最近邻", "等时圈", "服务范围",
    "选址", "可达性", "变化检测", "空间自相关", "热点", "聚类",
    "差异", "分布", "比较", "统计", "面积", "密度",
}

# 歧义触发词
_AMBIGUITY_TRIGGERS_ZH = [
    (r"附近|周边|周围", "空间范围模糊，需明确距离阈值"),
    (r"最近\d*年|近年来|历年", "时间范围模糊，需明确年份区间"),
    (r"合适|最好|推荐", "优化目标不明确，需明确评价指标"),
    (r"比较.*差异|差异.*比较", "比较维度不明确"),
    (r"影响.*因素|因素.*影响", "因果分析超出描述性 GIS 范围，可能需要统计模型"),
]


def build_reasoning_context(ri: ReasoningInput) -> ReasoningContext:
    """
    将 ReasoningInput 预处理为 ReasoningContext。

    Args:
        ri: 标准化输入对象

    Returns:
        ReasoningContext — 供规则层和 LLM 层使用的推理上下文
    """
    query = ri.query

    # 1. 语言标准化
    normalized_lang = _normalize_language(ri.user_context.language)

    # 2. 地理术语抽取
    geo_terms = _extract_geo_terms(query, normalized_lang)

    # 3. 查询歧义标记
    ambiguities = _detect_ambiguities(query, normalized_lang)

    # 4. 研究区对齐：query > project_context > dataset extent
    study_area = (
        _extract_study_area_from_query(query, normalized_lang)
        or ri.project_context.study_area
    )

    # 5. 时间范围对齐
    time_range = (
        _extract_time_range_from_query(query)
        or ri.project_context.extra.get("time_range")
        or _infer_time_range_from_datasets(ri)
    )

    # 6. 数据集 ID 列表
    dataset_ids = [d.id for d in ri.datasets]

    return ReasoningContext(
        source               = ri,
        normalized_language  = normalized_lang,
        geo_terms            = geo_terms,
        ambiguities          = ambiguities,
        study_area           = study_area,
        time_range           = time_range,
        dataset_ids          = dataset_ids,
    )


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────

def _normalize_language(lang: str) -> str:
    """zh-CN / zh / chinese → 'zh' ; en-US / en / english → 'en'"""
    lang_l = lang.lower()
    if lang_l.startswith("zh"):
        return "zh"
    if lang_l.startswith("en"):
        return "en"
    return "zh"   # 默认中文


def _extract_geo_terms(query: str, lang: str) -> List[str]:
    """从查询中抽取地理实体词"""
    found: List[str] = []
    if lang == "zh":
        for term in _CITY_NAMES_ZH | _GEO_FEATURE_TERMS_ZH | _ANALYSIS_TERMS_ZH:
            if term in query:
                found.append(term)
    else:
        query_lower = query.lower()
        for term in _CITY_NAMES_EN | _GEO_FEATURE_TERMS_EN:
            if term in query_lower:
                found.append(term)
    return list(dict.fromkeys(found))  # 保序去重


def _detect_ambiguities(query: str, lang: str) -> List[str]:
    """检测查询中的歧义点"""
    ambiguities: List[str] = []
    if lang == "zh":
        for pattern, msg in _AMBIGUITY_TRIGGERS_ZH:
            if re.search(pattern, query):
                ambiguities.append(msg)
    return ambiguities


def _extract_study_area_from_query(query: str, lang: str) -> Optional[str]:
    """从查询中抽取研究区名称"""
    if lang == "zh":
        for city in _CITY_NAMES_ZH:
            if city in query:
                return city
    else:
        query_lower = query.lower()
        for city in _CITY_NAMES_EN:
            if city in query_lower:
                return city.capitalize()
    return None


def _extract_time_range_from_query(query: str) -> Optional[str]:
    """从查询中抽取时间范围描述"""
    # 匹配：近五年、近3年、2020-2024、2023年、最近10年
    patterns = [
        r"近(\d+)年",
        r"(\d{4})\s*[-—至到]\s*(\d{4})",
        r"(\d{4})年",
        r"最近(\d+)年",
    ]
    for pattern in patterns:
        m = re.search(pattern, query)
        if m:
            return m.group(0)
    return None


def _infer_time_range_from_datasets(ri: ReasoningInput) -> Optional[str]:
    """从数据集元信息中推断时间范围"""
    time_ranges = [d.time_range for d in ri.datasets if d.has_temporal()]
    if not time_ranges:
        return None
    if len(time_ranges) == 1:
        return time_ranges[0]
    return f"{min(time_ranges)} — {max(time_ranges)}"
