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
| buffer | 缓冲区分析 | distance(距离数值), unit(meters/km, 默认meters), layer, output_name(可选,结果图层名) |
| clip | 裁剪 | layer(被裁剪图层), mask(裁剪边界图层), output_name(可选) |
| intersect | 相交分析 | layer_a, layer_b, output_name(可选) |
| union | 合并分析 | layer_a, layer_b, output_name(可选) |
| nearest_neighbor | 最近邻分析 | source(源图层), target(目标图层), output_name(可选) |
| spatial_join | 空间连接 | source, target, how(left/inner), predicate(intersects/within), output_name(可选) |
| kde | 核密度分析 | layer, bandwidth(默认0.05), grid_size(默认100), output_name(可选) |
| zonal_stats | 分区统计 | zones(区域图层), points(点/面图层), stat(count/sum/mean/max/min,默认count), value_col(可选,数值字段名,stat!=count时自动从图层推断), output_name(可选) |
| calculate_area | 面积计算 | layer, unit(m2/km2/ha) |
| network_build | 构建路网 | bbox或layer, network_type(drive/walk/bike) |
| isochrone | 等时圈 | center(经纬度，格式"lon,lat"如"114.30,30.60"；若用户写"经度X，纬度Y"则center="X,Y"；或拆分为lon和lat字段), minutes(时间列表), network_type, output_name(可选), graph_file(可选,用户指定本地路网graphml文件路径时填入) |
| shortest_path | 最短路径 | origin(起点"lon,lat"), destination(终点"lon,lat"), network_type(drive/walk/bike), output_name(可选), graph_file(可选,用户指定本地路网graphml文件路径时填入) |
| coord_transform | 坐标转换 | layer, from_crs(wgs84/gcj02/bd09), to_crs |
| render | 制图/可视化 | layers(图层列表), title, style(default/dark/satellite) |
| render_interactive | 交互地图 | layers, title |
| download_osm | 下载OSM数据 | place(地名), type(hospital/school/park/...), output_name(可选,结果图层名) |
| check_update | 检测更新 | (无参数) |
| memory_status | 查看记忆状态 | (无参数) |
| memory_search | 搜索记忆 | query(关键词) |
| skill_run | 运行指定 Skill（如 hospital_coverage/vec_kde/net_isochrone 等） | name(Skill名称), 其余为Skill参数 |
| skill_list | 列出所有可用 Skill | (无参数) |
| help | 帮助信息 | topic(可选主题) |
| tool_run | 执行本地工具 | tool(工具名), 工具参数... |
| react   | ReAct智能体完成复杂任务 | task(任务描述), max_steps(可选,默认12) |
| chat    | 自由对话/闲聊 | reply(回复文本) |
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
- **单步操作必须直接返回该 action，禁止包成 pipeline**：
  - "做 500 米缓冲区" → action="buffer"（单步，不是 pipeline）
  - "做 intersect 叠加分析" → action="intersect"（单步）
  - "做 union 合并" → action="union"（单步）
  - "按区县统计各类面积" → action="zonal_stats"（单步，zones=区县图层, points=目标图层）
  - 只有当用户明确要求"先...再..."多步流程时，才用 pipeline
  - "对A做X，同时对B做Y，然后一起渲染" → pipeline，步骤为 [X(A), Y(B), render]
    示例: "对医院做KDE(结果叫h_kde)，对公园做200米缓冲(结果叫p_buf)，然后一起显示静态地图"
    → pipeline steps: [{kde, targets:[hospitals], output_name:h_kde}, {buffer, distance:200, targets:[parks], output_name:p_buf}, {render, targets:[h_kde, p_buf]}]
  - 当用户在一句话里要求针对不同图层的多个操作时，每个操作都必须成为独立步骤，不能省略任何操作
- overlay 操作映射：intersect/相交 → action="intersect"；union/合并 → action="union"；clip/裁剪 → action="clip"
- **pipeline 渲染步骤**：如果用户要求"最后显示/画地图/生成地图"，必须在 steps 末尾加上 render 或 render_interactive 步骤，不能省略
  示例: "...最后把 A 和 B 显示在静态地图上" → 最后一步: {"action":"render","params":{"title":""},"targets":["A","B"]}
  示例: "...最后生成交互地图" → 最后一步: {"action":"render_interactive","params":{},"targets":["<前一步结果>"]}
- zonal_stats 用于"按区域统计"、"分区统计"、"各区/各县统计"等场景，不要映射到 react
- tool_run 示例: "查找 ~/data 下所有 geojson 文件" → action="tool_run", params={"tool":"file_find","pattern":"*.geojson","root":"~/data"}
- kde 示例: "对 hospitals 做核密度分析" → action="kde", params={"layer":"hospitals"}
- kde + output_name 示例: "对 hospitals 做核密度分析，结果图层名叫 hosp_kde" → action="kde", params={"layer":"hospitals","output_name":"hosp_kde"}
- kde + output_name 示例2: "对公园做核密度（结果叫 park_kde）" → action="kde", params={"layer":"parks","output_name":"park_kde"}
- 规则: 当用户提到"结果叫/存为/命名为/图层名叫 X"，必须将 X 填入 output_name
- isochrone 示例: "以某点（经度114.3664，纬度30.5340）为中心，步行5和10分钟等时圈" → action="isochrone", params={"center":"114.3664,30.5340","minutes":[5,10],"network_type":"walk"}
- isochrone 示例: "以(114.30, 30.60)为中心，10分钟等时圈" → action="isochrone", params={"center":"114.30,30.60","minutes":[10],"network_type":"walk"}
- isochrone + graph_file 示例: "以（114.3665, 30.5403）为中心，用本地路网文件 /tmp/x.graphml，计算步行5和10分钟等时圈" → action="isochrone", params={"center":"114.3665,30.5403","minutes":[5,10],"network_type":"walk","graph_file":"/tmp/x.graphml"}
- shortest_path + graph_file 示例: "从（114.36,30.54）到（114.37,30.53），用本地路网 /tmp/x.graphml 计算步行路径" → action="shortest_path", params={"origin":"114.36,30.54","destination":"114.37,30.53","network_type":"walk","graph_file":"/tmp/x.graphml"}
- **关键**: 含"等时圈"/"最短路径"的请求即使同时提到地名，也必须识别为 isochrone/shortest_path，绝对不是 download_osm
- skill_run 示例: "运行 hospital_coverage Skill，radius_km=1.0" → action="skill_run", params={"name":"hospital_coverage","radius_km":"1.0"}
- skill_run 示例: "运行 vec_kde Skill 对医院数据做核密度 bandwidth=0.05" → action="skill_run", params={"name":"vec_kde","bandwidth":"0.05"}
- skill_run 示例: "运行 vec_buffer Skill 对 parks 做1000米缓冲，合并重叠区域" → action="skill_run", params={"name":"vec_buffer","layer":"parks","distance":1000,"dissolve":true}  （"合并" 是Skill内部参数dissolve，不要拆成额外union步骤）
- skill_run 示例: "运行 retail_site_algo Skill，候选点用parks，人口层pop_grid，人口权重0.4，竞争权重0.3，推荐3个" → action="skill_run", params={"name":"retail_site_algo","input":"parks","pop_layer":"pop_grid","w_pop":0.4,"w_comp":0.3,"top_n":3}
- **关键规则**: skill_run 指令中所有参数（含Skill内部参数如dissolve/radius_km/w_pop等）都放在同一个skill_run的params中，绝不拆成pipeline步骤
- **反例（绝对不用 skill_run）**: "对医院做核密度分析 bandwidth=800" → action="kde", params={"bandwidth":800}（没有提到 Skill 名称）
- **反例（绝对不用 skill_run）**: "计算 10 分钟等时圈" → action="isochrone"（没有提到 Skill 名称）
- **区分规则**: skill_run 仅用于用户明确指定了 Skill 名称（如 hospital_coverage/vec_kde/net_isochrone）的场景；否则统一用直接 GIS action
- **路网操作识别规则**: 当用户提到"等时圈"/"isochrone"/"分钟内可达"→ action="isochrone"；提到"最短路径"/"路径规划"→ action="shortest_path"；若同时提到 graph_file 或本地路网文件路径，把路径填入 graph_file 参数，**不要**识别为 download_osm
- **download_osm 识别规则**: 只有当用户明确要求"下载...数据"/"获取...POI"/"从OSM获取"时才用 download_osm；"计算等时圈"/"计算路径"等路网分析操作绝对不能识别为 download_osm
- **重要**: "运行 X Skill"/"执行 X Skill"/"用 X Skill 做" 这类**明确提到 Skill 名称**的指令，才用 action="skill_run"
- **重要**: "做核密度分析"/"缓冲区"/"等时圈"/"下载OSM" 等直接描述 GIS 操作的指令，**不要**用 skill_run，要用对应的 GIS action（kde/buffer/isochrone/download_osm 等）
- react 仅用于需要多工具协作的复杂任务（如文件系统探索、代码执行），普通 GIS 操作不要用 react
- **status action**：查询当前会话状态、图层列表时，使用 action="status"（不要用 chat 自行回答）。
  触发词：「有哪些图层」「查看图层」「当前图层」「图层列表」「列出图层」
  示例：「现在有哪些图层？」→ {"action":"status","params":{},"targets":[],"confidence":0.95,"explanation":"查询图层"}
- **重要**：对于非 GIS 操作的输入（问候、闲聊、感谢、提问、GIS 建议、工具推荐等），使用 action="chat"，
  包含**比较/疑问/建议**性问题，如"XX和YY有什么区别"、"哪种更适合"、"哪种更准确"、"什么时候用XX"等，即使句中出现了 GIS 术语（如"缓冲区"、"等时圈"），也应识别为 chat，**而不是 GIS 操作**。
  - 反例（必须用 chat）: \"等时圈和缓冲区有什么区别？\" → action=\"chat\"（这是提问，不是执行缓冲区操作）
  - 反例（必须用 chat）: \"哪种分析更适合可达性研究？\" → action=\"chat\"（这是咨询建议）
  - 反例（必须用 chat）: \"缓冲区分析和等时圈哪种更准确？\" → action=\"chat\"（含"哪种"的比较提问）
  在 params.reply 中用中文直接回复，不要返回 unknown。
  例如 "你好" → {"action":"chat","params":{"reply":"你好！我是 GeoClaw，由中国地质大学（武汉）UrbanComp Lab 开发的开源智能地理空间分析框架。有什么 GIS 分析需要帮忙？"},"targets":[],"confidence":1.0,"explanation":"问候"}
  例如 "应该用哪种 Skill？" → {"action":"chat","params":{"reply":"根据你的分析需求，建议使用..."},"targets":[],"confidence":0.9,"explanation":"工具建议"}
- 只有真正无法理解的输入才返回 action="unknown"
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
        model:     str = "",
        use_ai:    Optional[bool] = None,
        verbose:   bool = False,
        provider:  Optional[str] = None,
    ):
        """
        Args:
            api_key : API Key（None 则从配置文件读取）
            model   : 使用的模型（空=自动，使用配置默认值）
            use_ai  : True=强制AI, False=强制规则, None=自动选择
            verbose : 打印调试信息
            provider: 指定 LLM provider（anthropic/openai/qwen，None=自动）
        """
        self.verbose = verbose

        # ── 初始化 LLM Provider ──────────────────────────────────────────
        self._llm = None

        try:
            from geoclaw_claude.nl.llm_provider import (
                LLMProvider, ProviderConfig, DEFAULT_MODELS
            )
            if api_key:
                import os as _os
                _pname = provider or _os.environ.get("GEOCLAW_LLM_PROVIDER", "") or "anthropic"
                _model = model or _os.environ.get("GEOCLAW_OPENAI_MODEL", "") or DEFAULT_MODELS.get(_pname, "")
                cfg = ProviderConfig(provider=_pname, api_key=api_key, model=_model)
                self._llm = LLMProvider(cfg, verbose=verbose)
            else:
                self._llm = LLMProvider.from_config(
                    provider=provider, verbose=verbose
                )
        except Exception as e:
            if verbose:
                print(f"  [NLP] LLMProvider 初始化失败: {e}")

        # 兼容旧版属性
        self._api_key = ""
        self.model = model or "claude-sonnet-4-20250514"
        if self._llm is not None:
            self.model = self._llm.model_name

        # ── 工作模式 ────────────────────────────────────────────────────
        if use_ai is None:
            self._use_ai = self._llm is not None
            # 若无 API Key 自动降级规则模式，打印引导提示
            if not self._use_ai:
                print(
                    "⚠  [GeoClaw] 未检测到 API Key，当前以离线规则模式运行。\n"
                    "   AI 模式可大幅提升意图理解精度，强烈建议配置 API Key：\n"
                    "   export OPENAI_API_KEY=sk-...   # OpenAI\n"
                    "   export ANTHROPIC_API_KEY=sk-... # Claude\n"
                    "   GeoClaw 支持 OpenAI / Claude / Gemini / Qwen / Ollama。"
                )
        else:
            self._use_ai = use_ai
            if not use_ai:
                self._llm = None
                if self.verbose:
                    print(
                        "ℹ  [GeoClaw] use_ai=False，已切换离线规则模式。\n"
                        "   如需 AI 语义理解，移除 use_ai=False 并配置 API Key。"
                    )

        if self.verbose:
            mode = "AI模式" if self._use_ai else "规则模式"
            llm_info = (
                f" [{self._llm.provider_name}/{self._llm.model_name}]"
                if self._llm else ""
            )
            print(f"  [NLP] 初始化完成，{mode}{llm_info}")

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
            # 高优先级关键词前置过滤：部分 GIS 操作不需要走 AI，直接规则解析更可靠
            t_lower = text.strip().lower()
            _kde_kw    = ["核密度", "kde", "密度热力", "密度分析"]
            _iso_kw    = ["等时圈", "isochrone", "分钟内可达", "分钟步行圈"]
            _skill_kw  = ["skill", "技能"]
            # 比较/疑问类问题：直接识别为 chat，不走 GIS 解析
            _compare_kw = ["有什么区别", "有何区别", "哪种更", "哪个更", "哪种适合",
                           "哪个适合", "什么区别", "什么不同", "有什么不同",
                           "优缺点", "什么时候用", "如何选择", "怎么选", "建议用哪"]
            if any(k in text for k in _compare_kw):
                # 比较性问题直接交给 LLM 生成 chat 回复
                if self._llm is not None:
                    try:
                        resp = self._llm.chat(
                            messages=[{"role": "user", "content": text}],
                            system="你是 GeoClaw-claude，一个 GIS 智能分析助手。请用专业但简洁的中文回答用户关于 GIS 方法的问题。"
                        )
                        reply = resp.content if resp else "这是个很好的问题！"
                        return ParsedIntent(action="chat", params={"reply": reply},
                                           targets=[], confidence=1.0,
                                           explanation="GIS方法比较问答",
                                           raw_text=text)
                    except Exception:
                        pass
                return ParsedIntent(action="chat",
                                   params={"reply": "这是个很好的分析方法比较问题，建议根据具体需求选择合适的工具。"},
                                   targets=[], confidence=1.0,
                                   explanation="GIS方法比较问答", raw_text=text)
            _has_skill = any(k in t_lower for k in _skill_kw)
            if not _has_skill:
                if any(k in text for k in _kde_kw):
                    intent = self._parse_with_rules(text, context)
                    intent.raw_text = text
                    return intent
                if any(k in text for k in _iso_kw):
                    intent = self._parse_with_rules(text, context)
                    intent.raw_text = text
                    return intent
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
        """调用 LLM（Anthropic/OpenAI/Qwen）解析意图，附带上下文压缩。"""
        if self._llm is None:
            if self.verbose:
                print("  [NLP] 无可用 LLM Provider，降级到规则模式")
            return self._parse_with_rules(text, context)

        # 构建用户消息，附带上下文
        user_msg = text
        if context:
            # soul / user 配置单独提取，其余作为普通上下文
            soul_prompt = context.pop("soul_system_prompt", None)
            user_hint   = context.pop("user_profile_hint", None)

            ctx_items = {k: v for k, v in context.items()}
            if user_hint:
                ctx_items["user_profile"] = user_hint

            ctx_str = "\n".join(f"  - {k}: {v}" for k, v in ctx_items.items())
            user_msg = f"当前上下文:\n{ctx_str}\n\n用户指令: {text}" if ctx_str else text

            # 将 soul system prompt 合并进系统提示词（行为边界，高优先级）
            effective_system = _SYSTEM_PROMPT
            if soul_prompt:
                effective_system = soul_prompt + "\n\n" + _SYSTEM_PROMPT
        else:
            soul_prompt = None
            effective_system = _SYSTEM_PROMPT

        # 上下文压缩（单轮解析只有一条消息，压缩主要用于多轮 agent）
        messages = [{"role": "user", "content": user_msg}]
        try:
            from geoclaw_claude.nl.context_compress import compress_if_needed
            from geoclaw_claude.config import Config
            cfg = Config.load()
            from geoclaw_claude.nl.context_compress import CompressConfig
            cc = CompressConfig(
                max_tokens=cfg.ctx_max_tokens,
                target_tokens=cfg.ctx_target_tokens,
                keep_recent=cfg.ctx_keep_recent,
            )
            messages, report = compress_if_needed(
                messages, effective_system, cc,
                verbose=cfg.ctx_compress_verbose
            )
            if report.level_applied > 0 and self.verbose:
                print(f"  [NLP] {report}")
        except Exception:
            pass  # 压缩失败不影响主流程

        try:
            from geoclaw_claude.nl.llm_provider import parse_json_response
            resp = self._llm.chat(messages=messages, system=effective_system)
            if resp is None:
                raise RuntimeError("LLM 无响应")
            data = parse_json_response(resp.content)
            if data is None:
                raise ValueError(f"JSON 解析失败: {resp.content[:200]}")
            if self.verbose:
                print(f"  [NLP] LLM({resp.provider}/{resp.model}) "
                      f"in={resp.tokens_in} out={resp.tokens_out} tokens")
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

        # 概念解释（在操作规则之前检查，避免被误匹配）
        if ("什么是" in t or "什么叫" in t or "解释" in t) and "缓冲" in t:
            return ParsedIntent(action="chat", params={"reply": "缓冲区分析（Buffer）：在地理要素周围生成指定距离的区域多边形，常用于分析服务影响范围。示例：'对医院做1公里缓冲区'。"}, targets=[], confidence=1.0, explanation="概念解释")
        if ("什么是" in t or "什么叫" in t) and ("等时圈" in t or "isochrone" in t):
            return ParsedIntent(action="chat", params={"reply": "等时圈（Isochrone）：从某点出发，在指定时间/距离内可以到达的区域多边形。示例：'生成地铁站15分钟步行等时圈'。"}, targets=[], confidence=1.0, explanation="概念解释")

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
            out_name = self._extract_output_name(text)
            params = {"layer": layer, "bandwidth": bw, "grid_size": gs}
            if out_name:
                params["output_name"] = out_name
            return ParsedIntent(
                action="kde",
                params=params,
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

        MOBILITY_TR = ["出行段", "tripleg", "出行模式", "transport mode"]
        if any(w in t for w in MOBILITY_TR):
            if any(w in t for w in ["预测", "识别", "分类", "predict", "出行方式", "交通方式"]):
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

        # 预测出行方式（比 triplegs 更早检测）
        TRANSPORT_PREDICT = ["预测出行方式", "出行方式预测", "交通方式预测", "predict transport", "mode prediction"]
        if any(w in t for w in TRANSPORT_PREDICT):
            return ParsedIntent(
                action="mobility_transport",
                params={"method": "simple-coarse"},
                targets=[],
                confidence=0.90,
                explanation="预测出行方式（步行/骑行/驾车/火车）",
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

        MOBILITY_MODAL = ["出行方式图", "modal", "交通构成", "出行构成", "出行方式构成图", "出行构成图"]
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

        # 问候 / 闲聊
        if any(w in t for w in ["你好", "hello", "hi", "嗨", "您好"]):
            return ParsedIntent(action="chat", params={"reply": "你好！我是 GeoClaw，由中国地质大学（武汉）UrbanComp Lab 开发的开源智能地理空间分析框架。你可以用自然语言让我帮你下载地图数据、做缓冲区分析、路网分析、可视化等。输入「帮助」查看更多示例。"}, targets=[], confidence=1.0, explanation="问候")
        if any(w in t for w in ["能做什么", "你是谁", "介绍一下", "有什么功能"]):
            return ParsedIntent(action="chat", params={"reply": "我是 GeoClaw，由中国地质大学（武汉）UrbanComp Lab（城市计算实验室）开发的开源 GIS 分析框架，支持：\n• 下载 OSM 地图数据（城市、POI、路网）\n• 缓冲区 / 叠加 / 最近邻 / 核密度分析\n• 路网最短路 / 等时圈\n• 静态地图 / 交互地图生成\n输入「帮助」查看完整命令列表。"}, targets=[], confidence=1.0, explanation="功能介绍")
        if any(w in t for w in ["谢谢", "感谢", "thank", "太棒了"]):
            return ParsedIntent(action="chat", params={"reply": "不客气！有其他 GIS 分析需求随时告诉我。"}, targets=[], confidence=1.0, explanation="感谢")
        if "缓冲区" in t and "什么" in t:
            return ParsedIntent(action="chat", params={"reply": "缓冲区分析（Buffer）：在地理要素周围生成指定距离的区域多边形，常用于分析服务范围。示例：'对医院做1公里缓冲区'。"}, targets=[], confidence=1.0, explanation="概念解释")
        if "等时圈" in t and "什么" in t:
            return ParsedIntent(action="chat", params={"reply": "等时圈（Isochrone）：从某点出发，在指定时间/距离内可到达的区域。示例：'生成地铁站15分钟步行等时圈'。"}, targets=[], confidence=1.0, explanation="概念解释")

        # 状态查询
        if any(w in t for w in ["status", "状态", "layers", "图层列表", "当前图层"]):
            return ParsedIntent(action="status", params={}, targets=[], confidence=0.9, explanation="查看当前状态")

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

    def _extract_output_name(self, text):
        import re
        kws = "结果图层名叫|结果叫做|命名为|存为|保存为|图层名叫|叫做|叫"
        m = re.search("(?:" + kws + r")\s*[A-Za-z_][A-Za-z0-9_]*", text)
        if m:
            # 提取最后一个空格后的标识符
            word = m.group(0).split()[-1]
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*$", word):
                return word
        m2 = re.search(r"output_name[=:]([A-Za-z_][A-Za-z0-9_]*)", text)
        if m2:
            return m2.group(1)
        return ""

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
