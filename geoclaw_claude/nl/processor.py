"""
geoclaw_claude/nl/processor.py
================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

自然语言处理器 (NLProcessor)

将用户的自然语言指令解析为结构化的 GIS 操作调用。

两种工作模式:
  1. AI 模式  (use_ai=True)  : 调用 Claude API 进行语义理解，精准识别意图、参数、链式操作
  2. 规则模式 (use_ai=False) : 基于关键词和正则表达式的本地解析，无需 API Key，离线可用

解析结果结构 (ParsedIntent):
  - action     : 操作名称 (buffer / clip / nn / kde / load / render / ...)
  - params     : 操作参数字典
  - targets    : 涉及的图层或文件名列表
  - confidence : 解析置信度 0~1
  - raw_text   : 原始用户输入
  - steps      : 多步操作链（支持"加载→缓冲→叠加→制图"一句话触发）

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── 意图数据类 ────────────────────────────────────────────────────────────────

@dataclass
class ParsedIntent:
    """解析后的用户意图，对应一个或多个 GIS 操作。"""
    action:      str              # 主操作 (buffer / clip / load / render / ...)
    params:      Dict[str, Any]   # 参数
    targets:     List[str]        # 目标图层/文件名
    confidence:  float  = 1.0    # 置信度 0~1
    raw_text:    str    = ""      # 原始输入
    steps:       List["ParsedIntent"] = field(default_factory=list)  # 多步链
    explanation: str    = ""      # 解析说明（调试用）

    def is_multi_step(self) -> bool:
        return len(self.steps) > 0

    def to_dict(self) -> dict:
        return {
            "action":      self.action,
            "params":      self.params,
            "targets":     self.targets,
            "confidence":  self.confidence,
            "steps":       [s.to_dict() for s in self.steps],
            "explanation": self.explanation,
        }

    def __repr__(self) -> str:
        p = ", ".join(f"{k}={v}" for k, v in self.params.items())
        t = ", ".join(self.targets) if self.targets else "—"
        return f"ParsedIntent(action={self.action!r}, targets=[{t}], params={{{p}}}, conf={self.confidence:.2f})"


# ── 系统提示（AI 模式） ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是 GeoClaw-claude 的自然语言 GIS 指令解析器。

将用户的自然语言指令解析为结构化 JSON，表示一个或多个 GIS 操作步骤。

## 支持的操作 (action)

| action | 说明 | 关键参数 |
|--------|------|---------|
| load | 加载矢量数据文件 | path(文件路径), name(图层名) |
| save | 保存图层到文件 | path, layer |
| buffer | 缓冲区分析 | distance(距离数值), unit(meters/km, 默认meters), layer |
| clip | 裁剪 | layer(被裁剪图层), mask(裁剪边界图层) |
| intersect | 相交分析 | layer_a, layer_b |
| union | 合并分析 | layer_a, layer_b |
| nearest_neighbor | 最近邻分析 | source(源图层), target(目标图层) |
| spatial_join | 空间连接 | source, target, how(left/inner), predicate(intersects/within) |
| kde | 核密度分析 | layer, bandwidth(默认0.05), grid_size(默认100) |
| zonal_stats | 分区统计 | zones(区域图层), points(点图层), stat(count/sum/mean) |
| calculate_area | 面积计算 | layer, unit(m2/km2/ha) |
| network_build | 构建路网 | bbox或layer, network_type(drive/walk/bike) |
| isochrone | 等时圈 | center(经纬度), minutes(时间列表), network_type |
| shortest_path | 最短路径 | origin(经纬度), destination(经纬度) |
| coord_transform | 坐标转换 | layer, from_crs(wgs84/gcj02/bd09), to_crs |
| render | 制图/可视化 | layers(图层列表), title, style(default/dark/satellite) |
| render_interactive | 交互地图 | layers, title |
| download_osm | 下载OSM数据 | place(地名), type(hospital/school/park/...) |
| check_update | 检测更新 | (无参数) |
| memory_status | 查看记忆状态 | (无参数) |
| memory_search | 搜索记忆 | query(关键词) |
| help | 帮助信息 | topic(可选主题) |
| unknown | 无法识别 | reason(说明) |
| mobility_load | 读入GPS轨迹/移动性数据 | path(文件路径), user_id_col, tracked_at_col |
| mobility_staypoints | 生成停留点 | dist_threshold(米,默认100), time_threshold(分钟,默认5) |
| mobility_triplegs | 生成出行段 | (无额外参数，自动使用已有停留点) |
| mobility_hierarchy | 一键生成完整移动性层级 | dist_threshold, time_threshold, location_epsilon |
| mobility_transport | 预测出行方式 | method(simple-coarse/simple-combined) |
| mobility_locations | 识别重要地点/家工作地 | epsilon(米), method(osna/freq) |
| mobility_summary | 生成移动性指标摘要 | user_id(可选) |
| mobility_plot | 移动性地图可视化 | layers(pf/sp/triplegs/locs), user_id |
| mobility_heatmap | 活动时间热力图 | user_id(可选) |
| mobility_modal | 出行方式构成图 | metric(count/duration) |

## 输出格式

单步操作：
```json
{
  "action": "buffer",
  "params": {"distance": 1000, "unit": "meters"},
  "targets": ["hospitals"],
  "confidence": 0.95,
  "explanation": "对 hospitals 图层做 1000 米缓冲区"
}
```

多步操作链（如"加载医院数据并做1公里缓冲区"）：
```json
{
  "action": "pipeline",
  "params": {},
  "targets": [],
  "confidence": 0.9,
  "explanation": "加载数据 → 缓冲区分析",
  "steps": [
    {"action": "load", "params": {"path": "hospitals.geojson"}, "targets": ["hospitals"], "confidence": 0.9, "explanation": "加载医院数据"},
    {"action": "buffer", "params": {"distance": 1000, "unit": "meters"}, "targets": ["hospitals"], "confidence": 0.9, "explanation": "1公里缓冲区"}
  ]
}
```

## 规则
- 只输出 JSON，不要任何解释文字或代码块包裹
- 距离单位：默认 meters；"公里/km/千米" → km；"米/m" → meters
- 如果用户没有指定图层名，从上下文猜测（如"医院" → hospitals）
- 置信度：确定 ≥0.9，较确定 0.7~0.9，不确定 <0.7
- 对于无法理解的输入，action="unknown"，reason 说明原因
"""


# ── NLProcessor 主类 ─────────────────────────────────────────────────────────

class NLProcessor:
    """
    自然语言指令解析器。

    Usage::

        proc = NLProcessor(api_key="sk-...", use_ai=True)

        # 解析单条指令
        intent = proc.parse("对武汉医院数据做1公里缓冲区")
        print(intent)
        # → ParsedIntent(action='buffer', targets=['hospitals'], params={distance:1000, unit:'meters'})

        # 支持上下文（多轮对话）
        intent2 = proc.parse("再对地铁站做500米", context={"last_layer": "metro"})
    """

    def __init__(
        self,
        api_key:   Optional[str] = None,
        model:     str = "claude-sonnet-4-20250514",
        use_ai:    Optional[bool] = None,
        verbose:   bool = False,
    ):
        """
        Args:
            api_key : Anthropic API Key（None 则从配置文件读取）
            model   : 使用的 Claude 模型
            use_ai  : True=强制AI, False=强制规则, None=自动选择（有key→AI）
            verbose : 打印调试信息
        """
        self.model   = model
        self.verbose = verbose

        # 解析 API Key
        self._api_key = api_key or self._load_api_key()

        # 决定模式
        if use_ai is None:
            self._use_ai = bool(self._api_key)
        else:
            self._use_ai = use_ai

        if self.verbose:
            mode = "AI模式" if self._use_ai else "规则模式"
            print(f"  [NLP] 初始化完成，{mode}")

    def _load_api_key(self) -> str:
        try:
            from geoclaw_claude.config import Config
            return Config.load().anthropic_api_key
        except Exception:
            return ""

    # ── 主解析入口 ────────────────────────────────────────────────────────────

    def parse(
        self,
        text:    str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ParsedIntent:
        """
        解析自然语言指令。

        Args:
            text   : 用户输入文本
            context: 上下文信息（可用图层、上一步结果等）

        Returns:
            ParsedIntent
        """
        text = text.strip()
        if not text:
            return ParsedIntent(action="unknown", params={}, targets=[],
                                confidence=0.0, raw_text=text,
                                explanation="输入为空")

        if self._use_ai:
            intent = self._parse_with_ai(text, context)
        else:
            intent = self._parse_with_rules(text, context)

        intent.raw_text = text

        if self.verbose:
            print(f"  [NLP] 解析结果: {intent}")

        return intent

    # ── AI 解析 ───────────────────────────────────────────────────────────────

    def _parse_with_ai(
        self,
        text:    str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ParsedIntent:
        """调用 Claude API 解析意图。"""
        try:
            import anthropic
        except ImportError:
            if self.verbose:
                print("  [NLP] anthropic 库未安装，降级到规则模式")
            return self._parse_with_rules(text, context)

        # 构建用户消息，附带上下文
        user_msg = text
        if context:
            ctx_str = "\n".join(f"  - {k}: {v}" for k, v in context.items())
            user_msg = f"当前上下文:\n{ctx_str}\n\n用户指令: {text}"

        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw_json = response.content[0].text.strip()

            # 清理可能的 markdown 代码块
            raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json)
            raw_json = re.sub(r"\s*```$", "", raw_json)

            data = json.loads(raw_json)
            return self._dict_to_intent(data)

        except Exception as e:
            if self.verbose:
                print(f"  [NLP] AI 解析失败 ({e})，降级到规则模式")
            return self._parse_with_rules(text, context)

    # ── 规则解析 ──────────────────────────────────────────────────────────────

    def _parse_with_rules(
        self,
        text:    str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ParsedIntent:
        """基于关键词 + 正则表达式的本地规则解析。"""
        t  = text.lower()
        ctx = context or {}

        # ── 检测操作意图 ──────────────────────────────────────────────────────

        # 多步操作：包含连接词
        PIPELINE_WORDS = ["然后", "接着", "再", "并且", "并", "之后", "→", "->", "and then"]
        if any(w in t for w in PIPELINE_WORDS):
            steps = self._split_pipeline(text, ctx)
            if len(steps) > 1:
                return ParsedIntent(
                    action="pipeline",
                    params={},
                    targets=[],
                    confidence=0.8,
                    explanation="多步操作链: " + " → ".join(s.action for s in steps),
                    steps=steps,
                )

        # ── 单步操作规则 ──────────────────────────────────────────────────────

        # 加载数据
        LOAD_WORDS = ["加载", "读取", "打开", "导入", "load"]
        if any(w in t for w in LOAD_WORDS):
            path   = self._extract_filepath(text)
            name   = self._extract_layer_name(text)
            return ParsedIntent(
                action="load",
                params={"path": path or "", "name": name or ""},
                targets=[name] if name else [],
                confidence=0.85 if path else 0.6,
                explanation=f"加载文件: {path or '(未指定路径)'}",
            )

        # 缓冲区
        BUFFER_WORDS = ["缓冲", "buffer", "扩展", "半径", "范围"]
        if any(w in t for w in BUFFER_WORDS):
            dist, unit  = self._extract_distance(text)
            layer_name  = self._extract_layer_name(text) or ctx.get("last_layer", "")
            return ParsedIntent(
                action="buffer",
                params={"distance": dist, "unit": unit},
                targets=[layer_name] if layer_name else [],
                confidence=0.9 if dist > 0 else 0.7,
                explanation=f"缓冲区分析: {dist}{unit}" + (f" → {layer_name}" if layer_name else ""),
            )

        # 裁剪
        CLIP_WORDS = ["裁剪", "clip", "提取", "范围内", "边界内"]
        if any(w in t for w in CLIP_WORDS):
            names = self._extract_multiple_layers(text)
            layer = names[0] if names else ctx.get("last_layer", "")
            mask  = names[1] if len(names) > 1 else ""
            return ParsedIntent(
                action="clip",
                params={"layer": layer, "mask": mask},
                targets=names,
                confidence=0.85 if mask else 0.6,
                explanation=f"裁剪: {layer} ∩ {mask or '(未指定边界)'}",
            )

        # 最近邻
        NN_WORDS = ["最近邻", "最近", "nearest", "距离最近", "近"]
        if any(w in t for w in NN_WORDS) and "最近邻" in t or "nearest" in t:
            names  = self._extract_multiple_layers(text)
            source = names[0] if names else ctx.get("last_layer", "")
            target = names[1] if len(names) > 1 else ""
            return ParsedIntent(
                action="nearest_neighbor",
                params={"source": source, "target": target},
                targets=names,
                confidence=0.85,
                explanation=f"最近邻: {source} → {target}",
            )

        # KDE 核密度
        KDE_WORDS = ["核密度", "密度", "kde", "热点"]  # 注：热力图由 mobility_heatmap 优先处理
        if any(w in t for w in KDE_WORDS):
            layer = self._extract_layer_name(text) or ctx.get("last_layer", "")
            bw    = self._extract_number_with_keyword(text, ["带宽", "bandwidth"], 0.05)
            gs    = int(self._extract_number_with_keyword(text, ["网格", "grid"], 100))
            return ParsedIntent(
                action="kde",
                params={"layer": layer, "bandwidth": bw, "grid_size": gs},
                targets=[layer] if layer else [],
                confidence=0.88,
                explanation=f"KDE 核密度: {layer or '(未指定图层)'}",
            )

        # 坐标转换
        TRANSFORM_WORDS = ["坐标转换", "转坐标", "gcj", "bd09", "wgs84", "偏移校正"]
        if any(w in t for w in TRANSFORM_WORDS):
            from_crs = "wgs84"
            to_crs   = "gcj02"
            if "gcj" in t and ("wgs" in t or "to" in t): to_crs = "gcj02"
            if "bd09" in t or "百度" in t: to_crs = "bd09"
            if "wgs84" in t and "from" in t: from_crs = "gcj02"
            layer = self._extract_layer_name(text) or ctx.get("last_layer", "")
            return ParsedIntent(
                action="coord_transform",
                params={"layer": layer, "from_crs": from_crs, "to_crs": to_crs},
                targets=[layer] if layer else [],
                confidence=0.8,
                explanation=f"坐标转换: {from_crs} → {to_crs}",
            )

        # 面积计算
        AREA_WORDS = ["面积", "计算面积", "area"]
        if any(w in t for w in AREA_WORDS):
            layer = self._extract_layer_name(text) or ctx.get("last_layer", "")
            unit  = "km2" if "平方公里" in t or "km2" in t else \
                    "ha"  if "公顷" in t or "ha" in t else "m2"
            return ParsedIntent(
                action="calculate_area",
                params={"layer": layer, "unit": unit},
                targets=[layer] if layer else [],
                confidence=0.88,
                explanation=f"计算面积 ({unit}): {layer}",
            )

        # 分区统计
        ZONAL_WORDS = ["分区统计", "区域统计", "统计", "zonal"]
        if any(w in t for w in ZONAL_WORDS):
            names  = self._extract_multiple_layers(text)
            zones  = names[0] if names else ctx.get("last_layer", "")
            points = names[1] if len(names) > 1 else ""
            stat   = "count"
            for s in ["count", "sum", "mean", "max", "min", "数量", "总和", "均值"]:
                if s in t:
                    stat = {"数量": "count", "总和": "sum", "均值": "mean"}.get(s, s)
                    break
            return ParsedIntent(
                action="zonal_stats",
                params={"zones": zones, "points": points, "stat": stat},
                targets=names,
                confidence=0.82,
                explanation=f"分区统计 ({stat}): {zones} × {points}",
            )

        # 移动性地图（在普通制图之前检测，避免被 render 抢占）
        if any(w in t for w in ["移动性地图", "轨迹地图", "出行地图"]):
            return ParsedIntent(
                action="mobility_plot",
                params={},
                targets=[],
                confidence=0.88,
                explanation="移动性数据分层地图",
            )

        # 制图 / 可视化
        RENDER_WORDS = ["制图", "可视化", "画图", "绘图", "显示", "render", "地图", "出图"]
        if any(w in t for w in RENDER_WORDS):
            layer = self._extract_layer_name(text) or ctx.get("last_layer", "")
            title = self._extract_quoted_string(text) or ""
            inter = any(w in t for w in ["交互", "folium", "html", "interactive"])
            action = "render_interactive" if inter else "render"
            return ParsedIntent(
                action=action,
                params={"title": title},
                targets=[layer] if layer else [],
                confidence=0.85,
                explanation=f"{'交互' if inter else '静态'}制图: {layer or '(当前图层)'}",
            )

        # 下载 OSM
        DOWNLOAD_WORDS = ["下载", "获取", "download", "osm"]
        if any(w in t for w in DOWNLOAD_WORDS):
            place     = self._extract_place(text)
            poi_type  = self._extract_poi_type(text)
            return ParsedIntent(
                action="download_osm",
                params={"place": place, "type": poi_type},
                targets=[],
                confidence=0.80 if place else 0.5,
                explanation=f"下载 OSM 数据: {place or '(未指定地点)'} / {poi_type}",
            )

        # 等时圈
        ISO_WORDS = ["等时圈", "isochrone", "可达圈", "分钟可达", "步行范围", "骑行范围"]
        if any(w in t for w in ISO_WORDS):
            minutes = self._extract_minutes(text)
            center  = self._extract_coordinates(text)
            ntype   = "walk" if "步行" in t else "bike" if "骑行" in t else "drive"
            return ParsedIntent(
                action="isochrone",
                params={"minutes": minutes, "network_type": ntype, "center": center},
                targets=[],
                confidence=0.85 if minutes else 0.6,
                explanation=f"等时圈: {minutes}分钟 ({ntype})",
            )

        # 移动性分析
        MOBILITY_LOAD = ["轨迹", "gps", "positionfix", "移动数据", "read_pos"]
        if any(w in t for w in MOBILITY_LOAD):
            path = self._extract_filepath(text)
            return ParsedIntent(
                action="mobility_load",
                params={"path": path or ""},
                targets=[],
                confidence=0.85 if path else 0.6,
                explanation=f"读入移动性数据: {path or '(未指定路径)'}",
            )

        MOBILITY_SP = ["停留点", "staypoint", "驻留", "停留检测"]
        if any(w in t for w in MOBILITY_SP):
            dist = self._extract_number_with_keyword(text, ["距离", "dist", "米"], 100)
            time = self._extract_number_with_keyword(text, ["时间", "分钟", "min"], 5)
            return ParsedIntent(
                action="mobility_staypoints",
                params={"dist_threshold": dist, "time_threshold": time},
                targets=[],
                confidence=0.88,
                explanation=f"生成停留点 (dist={dist}m, time={time}min)",
            )

        MOBILITY_H = ["移动性分析", "出行分析", "全层级", "hierarchy",
                      "完整移动", "轨迹分析", "mobility"]
        if any(w in t for w in MOBILITY_H):
            return ParsedIntent(
                action="mobility_hierarchy",
                params={},
                targets=[],
                confidence=0.85,
                explanation="一键生成完整移动性数据层级",
            )

        MOBILITY_TR = ["出行段", "tripleg", "出行模式", "交通方式", "transport", "出行方式", "transport mode"]
        if any(w in t for w in MOBILITY_TR):
            if any(w in t for w in ["预测", "识别", "分类", "predict"]):
                return ParsedIntent(
                    action="mobility_transport",
                    params={"method": "simple-coarse"},
                    targets=[],
                    confidence=0.87,
                    explanation="预测出行方式（步行/骑行/驾车/火车）",
                )
            return ParsedIntent(
                action="mobility_triplegs",
                params={},
                targets=[],
                confidence=0.85,
                explanation="生成出行段",
            )

        MOBILITY_LOC = ["重要地点", "家", "工作地", "location", "聚类地点", "home", "work"]
        if any(w in t for w in MOBILITY_LOC) and any(
            w in t for w in ["识别", "检测", "生成", "聚类"]
        ):
            method = "osna" if any(w in t for w in ["家", "工作", "home", "work"]) else "freq"
            return ParsedIntent(
                action="mobility_locations",
                params={"method": method},
                targets=[],
                confidence=0.85,
                explanation=f"识别重要地点（方法: {method}）",
            )

        MOBILITY_SUM = ["移动性指标", "移动性摘要", "出行摘要", "mobility summary",
                        "回转半径", "跳跃距离"]
        if any(w in t for w in MOBILITY_SUM):
            return ParsedIntent(
                action="mobility_summary",
                params={},
                targets=[],
                confidence=0.87,
                explanation="生成移动性综合指标摘要",
            )

        MOBILITY_PLOT = ["移动性地图", "轨迹地图", "mobility plot", "出行地图", "mobility map"]
        if any(w in t for w in MOBILITY_PLOT):
            return ParsedIntent(
                action="mobility_plot",
                params={},
                targets=[],
                confidence=0.85,
                explanation="移动性数据分层地图",
            )

        MOBILITY_HEAT = ["活动热力图", "时间热力图", "heatmap", "活动时间", "热力图"]
        if any(w in t for w in MOBILITY_HEAT):
            return ParsedIntent(
                action="mobility_heatmap",
                params={},
                targets=[],
                confidence=0.87,
                explanation="活动时间热力图（星期 × 小时）",
            )

        MOBILITY_MODAL = ["出行方式图", "modal", "交通构成", "出行构成"]
        if any(w in t for w in MOBILITY_MODAL):
            return ParsedIntent(
                action="mobility_modal",
                params={},
                targets=[],
                confidence=0.85,
                explanation="出行方式构成图",
            )

        # 检测更新
        if any(w in t for w in ["更新", "check", "检测", "version", "版本"]):
            return ParsedIntent(action="check_update", params={}, targets=[], confidence=0.8,
                                explanation="检测是否有新版本")

        # 记忆系统
        if any(w in t for w in ["记忆", "memory", "历史", "复盘"]):
            query = text
            return ParsedIntent(action="memory_search", params={"query": query}, targets=[],
                                confidence=0.75, explanation="搜索记忆系统")

        # 帮助
        if any(w in t for w in ["帮助", "help", "怎么用", "功能", "命令"]):
            return ParsedIntent(action="help", params={}, targets=[], confidence=0.9,
                                explanation="显示帮助信息")

        # 未识别
        return ParsedIntent(
            action="unknown",
            params={"reason": f"无法识别指令: {text[:50]}"},
            targets=[],
            confidence=0.0,
            explanation="规则引擎无法匹配任何已知操作",
        )

    # ── 辅助解析函数 ──────────────────────────────────────────────────────────

    def _extract_distance(self, text: str) -> Tuple[float, str]:
        """提取距离数值和单位。"""
        # 中文数字转阿拉伯
        text = re.sub(r"一([千百万])", lambda m: {"千": "1000", "百": "100", "万": "10000"}[m.group(1)], text)
        # "1公里" "500米" "1km" "500m" "1.5千米"
        for pat, unit in [
            (r"(\d+\.?\d*)\s*(?:公里|千米|km|KM)", "meters"),
            (r"(\d+\.?\d*)\s*(?:米|m\b|M\b)", "meters"),
        ]:
            m = re.search(pat, text)
            if m:
                val = float(m.group(1))
                if "公里" in text[m.start():m.end()+2] or "千米" in text[m.start():m.end()+2] \
                        or "km" in text[m.start():m.end()+2].lower():
                    val *= 1000  # 转为米
                return val, "meters"
        # 纯数字 fallback
        m = re.search(r"(\d+\.?\d*)", text)
        if m:
            return float(m.group(1)), "meters"
        return 1000.0, "meters"  # 默认 1km

    def _extract_layer_name(self, text: str) -> str:
        """从文本中猜测图层名称。"""
        LAYER_MAP = {
            "医院": "hospitals", "hospital": "hospitals",
            "地铁": "metro_stations", "metro": "metro_stations", "地铁站": "metro_stations",
            "学校": "schools", "公园": "parks", "公路": "roads", "道路": "roads",
            "水体": "water", "边界": "boundary", "行政": "boundary",
            "建筑": "buildings", "poi": "pois",
        }
        t = text.lower()
        for zh, en in LAYER_MAP.items():
            if zh in text or en in t:
                return en
        # 尝试提取 .geojson/.shp 文件名
        m = re.search(r"([\w\-]+)\.(?:geojson|shp|json|csv)", text, re.IGNORECASE)
        if m:
            return m.group(1)
        return ""

    def _extract_filepath(self, text: str) -> str:
        """提取文件路径。"""
        m = re.search(r"([\w\-./\\]+\.(?:geojson|shp|json|csv|tif|tiff))", text, re.IGNORECASE)
        return m.group(1) if m else ""

    def _extract_multiple_layers(self, text: str) -> List[str]:
        """提取多个图层名称。"""
        LAYER_KEYWORDS = {
            "医院": "hospitals", "地铁": "metro_stations", "学校": "schools",
            "公园": "parks", "道路": "roads", "边界": "boundary",
            "水体": "water", "建筑": "buildings",
        }
        found = []
        for kw, name in LAYER_KEYWORDS.items():
            if kw in text and name not in found:
                found.append(name)
        # 也提取文件名
        for m in re.finditer(r"([\w\-]+)\.(?:geojson|shp|json)", text, re.IGNORECASE):
            nm = m.group(1)
            if nm not in found:
                found.append(nm)
        return found

    def _extract_number_with_keyword(self, text: str, keywords: List[str], default: float) -> float:
        """在关键词附近提取数字。"""
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0:
                m = re.search(r"(\d+\.?\d*)", text[idx:idx+20])
                if m:
                    return float(m.group(1))
        return default

    def _extract_quoted_string(self, text: str) -> str:
        """提取引号内的字符串。"""
        m = re.search(r'["\'""](.+?)["\'""]', text)
        return m.group(1) if m else ""

    def _extract_place(self, text: str) -> str:
        """提取地名。"""
        # 常见地名模式
        for pat in [r"([\u4e00-\u9fff]{2,6}(?:市|区|县|省|镇|乡|街道))", r"([\u4e00-\u9fff]{2,8})"]:
            m = re.search(pat, text)
            if m:
                place = m.group(1)
                if place not in ["加载", "读取", "下载", "数据", "分析", "计算"]:
                    return place
        return ""

    def _extract_poi_type(self, text: str) -> str:
        """提取 POI 类型。"""
        POI_MAP = {
            "医院": "hospital", "学校": "school", "公园": "park",
            "餐厅": "restaurant", "银行": "bank", "超市": "supermarket",
            "停车场": "parking", "加油站": "fuel", "酒店": "hotel",
        }
        for zh, en in POI_MAP.items():
            if zh in text:
                return en
        return "poi"

    def _extract_minutes(self, text: str) -> List[int]:
        """提取时间（分钟）列表。"""
        numbers = re.findall(r"(\d+)\s*分钟?", text)
        if numbers:
            return [int(n) for n in numbers]
        m = re.search(r"(\d+)", text)
        if m:
            return [int(m.group(1))]
        return [5, 10, 15]

    def _extract_coordinates(self, text: str) -> Optional[Tuple[float, float]]:
        """提取经纬度坐标。"""
        m = re.search(r"(\d{2,3}\.\d+)[,，\s]+(\d{2}\.\d+)", text)
        if m:
            return float(m.group(1)), float(m.group(2))
        return None

    def _split_pipeline(self, text: str, ctx: Dict) -> List[ParsedIntent]:
        """将多步描述拆分为独立的操作步骤。"""
        SPLIT_WORDS = ["然后", "接着", "再", "并且", "之后", "→", "->"]
        parts = [text]
        for w in SPLIT_WORDS:
            new_parts = []
            for part in parts:
                new_parts.extend(part.split(w))
            parts = [p.strip() for p in new_parts if p.strip()]

        steps = []
        for part in parts:
            # 递归解析每个子步骤（强制规则模式，避免 AI 递归调用）
            sub = NLProcessor(use_ai=False, verbose=False)._parse_with_rules(part, ctx)
            if sub.action != "unknown":
                steps.append(sub)
        return steps

    # ── dict → ParsedIntent ───────────────────────────────────────────────────

    def _dict_to_intent(self, data: dict) -> ParsedIntent:
        """将 API 返回的 dict 转为 ParsedIntent。"""
        sub_steps = []
        for s in data.get("steps", []):
            sub_steps.append(self._dict_to_intent(s))

        return ParsedIntent(
            action=data.get("action", "unknown"),
            params=data.get("params", {}),
            targets=data.get("targets", []),
            confidence=float(data.get("confidence", 0.8)),
            explanation=data.get("explanation", ""),
            steps=sub_steps,
        )
