# GeoClaw-claude

> **UrbanComp Lab** 出品的轻量级 Python 城市地理信息分析工具集
> https://urbancomp.net

[![Version](https://img.shields.io/badge/version-2.3.0-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.9+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-128%2F128-brightgreen)](#测试矩阵)
[![LLM](https://img.shields.io/badge/LLM-Claude%20%7C%20Gemini%20%7C%20GPT%20%7C%20Qwen-blueviolet)](#1-多-llm-provider含-gemini)
[![trackintel](https://img.shields.io/badge/mobility-trackintel-9cf)](https://github.com/mie-lab/trackintel)

参考 QGIS Processing Framework 设计，专注于城市地理空间数据分析。核心理念是用**自然语言**直接驱动 GIS 操作：一句话完成从数据加载、空间分析到制图输出的完整流水线。

**v2.3.0 重点更新：** 新增 Google Gemini API 支持、会话记忆存档系统、向量语义检索、多模型 onboard 配置向导。

---

## 目录

- [快速开始](#快速开始)
- [v2.3.0 新特性](#v230-新特性)
  - [多 LLM Provider（含 Gemini）](#1-多-llm-provider含-gemini)
  - [记忆存档系统](#2-记忆存档系统memoryarchive)
  - [向量语义检索](#3-向量语义检索vectorsearch)
  - [自动上下文压缩](#4-自动上下文压缩)
  - [Onboard 多模型向导](#5-onboard-多模型配置向导)
- [自然语言操作系统](#自然语言操作系统)
- [人类移动性分析](#人类移动性分析)
- [Memory 记忆系统](#memory-记忆系统)
- [功能模块总览](#功能模块总览)
- [安装与依赖](#安装与依赖)
- [项目结构](#项目结构)
- [测试矩阵](#测试矩阵)
- [版本历史](#版本历史)
- [算法来源声明](#算法来源声明trackintel)

---

## 快速开始

```bash
git clone https://github.com/whuyao/GeoClaw_Claude.git
cd GeoClaw_Claude && bash install.sh

# 交互式初始化向导（配置所有模型 API Key、目录、压缩参数等）
geoclaw-claude onboard

# 自然语言 GIS 分析
geoclaw-claude ask "下载武汉市医院数据，做1公里缓冲区，用交互地图显示"

# 人类移动性分析
geoclaw-claude ask "读入 data/mobility/wuhan_gps_tracks.csv"
geoclaw-claude ask "一键完成移动性分析"
geoclaw-claude ask "轨迹地图"

# 向量语义搜索历史记忆
geoclaw-claude memory vsearch "武汉医院空间分析"
```

---

## v2.3.0 新特性

### 1. 多 LLM Provider（含 Gemini）

v2.3.0 新增 **Google Gemini** 支持，现已覆盖四大主流 LLM Provider，通过统一接口调用，切换模型零成本。

| Provider | 代表模型 | 安装 |
|----------|---------|------|
| **Anthropic Claude** | `claude-sonnet-4-20250514` | `pip install anthropic` |
| **Google Gemini** ✨新 | `gemini-2.0-flash` · `gemini-1.5-pro` · `gemini-2.5-pro-preview-03-25` | `pip install google-genai` |
| **OpenAI GPT** | `gpt-4o` · `gpt-4o-mini` | `pip install openai` |
| **通义千问 Qwen** | `qwen-max` · `qwen-plus` · `qwen-turbo` | `pip install openai` |

**自动优先级（留空时按此顺序）：** `anthropic` → `gemini` → `openai` → `qwen`

**配置 Gemini：**

```bash
# 方式一：onboard 向导一次配置所有模型（推荐）
geoclaw-claude onboard

# 方式二：直接设置
geoclaw-claude config set gemini_api_key  AIza...
geoclaw-claude config set gemini_model    gemini-2.0-flash
geoclaw-claude config set llm_provider   gemini    # 强制指定（留空=自动）

# 方式三：环境变量
export GEOCLAW_GEMINI_API_KEY=AIza...
export GEOCLAW_LLM_PROVIDER=gemini
```

**Python API：**

```python
from geoclaw_claude.nl.llm_provider import LLMProvider, ProviderConfig

# 自动选择最高优先级的可用 Provider
llm = LLMProvider.from_config()
print(llm.provider_name, llm.model_name)   # gemini / gemini-2.0-flash

# 显式指定 Gemini
llm = LLMProvider(ProviderConfig(
    provider="gemini",
    api_key="AIza...",
    model="gemini-2.0-flash",      # 或 gemini-1.5-pro / gemini-2.5-pro-preview-03-25
))

resp = llm.chat(
    system="你是 GIS 分析助手",
    messages=[{"role": "user", "content": "分析武汉市医院的空间分布"}],
)
print(resp.content)
# resp.provider / resp.model / resp.tokens_in / resp.tokens_out 均可访问
```

---

### 2. 记忆存档系统（MemoryArchive）

✨ **v2.3.0 全新功能** — 将完整会话快照持久化到磁盘，支持跨会话检索、全量备份与迁移。

**存档目录结构：**

```
~/.geoclaw_claude/archives/
  ├── index.json           ← 全局索引（标题 / 时间 / 标签 / 摘要）
  ├── 2025-03/
  │   ├── arc_a1b2c3d4.json  ← 完整会话快照（操作序列 + 上下文）
  │   └── ...
  └── ...
```

**CLI：**

```bash
# 存档当前会话
geoclaw-claude memory archive save -t "武汉医院分析" -s "缓冲区+核密度" --tags "wuhan,hospital"

# 查看所有存档
geoclaw-claude memory archive list
geoclaw-claude memory archive list --tag wuhan

# 搜索存档
geoclaw-claude memory archive search "武汉 医院"

# 全量备份（可跨机器迁移）
geoclaw-claude memory archive export -o backup_2025.json
geoclaw-claude memory archive import backup_2025.json

# 统计
geoclaw-claude memory archive stats
```

**Python API：**

```python
from geoclaw_claude.memory import get_archive

arc = get_archive()

# 存档一次完整会话
entry = arc.save_session(
    title="武汉医院覆盖分析",
    ops_log=[
        {"action": "load",   "detail": "hospitals.geojson"},
        {"action": "buffer", "detail": "1km"},
        {"action": "kde",    "detail": "bandwidth=0.05"},
    ],
    summary="完成医院1公里服务圈与核密度分析，主城区覆盖率约92%",
    tags=["wuhan", "hospital", "coverage"],
)
print(entry.archive_id, entry.date_str)

# 关键词搜索
for r in arc.search("武汉 医院"):
    print(r.title, "→", r.summary)

# 加载完整快照
entry = arc.load(archive_id)
ops   = entry.content["ops_log"]    # 操作序列
ctx   = entry.content["context"]    # 会话上下文

print(arc.stats())
# {"total": 15, "size_human": "42.3 KB", "sources": {"session": 15, ...}}
```

---

### 3. 向量语义检索（VectorSearch）

✨ **v2.3.0 全新功能** — 让记忆检索从「关键词命中」升级为「语义理解」，无需安装任何额外依赖即可使用。

| 特性 | 说明 |
|------|------|
| **零外部依赖** | 纯 Python 标准库实现 TF-IDF，中英文字符级混合分词 |
| **稀疏向量检索** | 余弦相似度 + 重要度加权（score = tfidf×0.85 + importance×0.15） |
| **可选神经增强** | 安装 `sentence-transformers` 后自动切换为多语言嵌入，检索质量显著提升 |
| **增量更新** | 新增/删除无需重建全量索引 |
| **持久化** | 索引自动保存至 `~/.geoclaw_claude/vector_index/` |
| **来源过滤** | 可分别检索 `memory`（长期知识）或 `archive`（会话快照）来源 |

```bash
# 可选：安装神经网络嵌入增强（多语言，中文效果更好）
pip install sentence-transformers
```

**CLI：**

```bash
# 语义搜索（比 memory search 更智能，理解同义词和语义关联）
geoclaw-claude memory vsearch "武汉医院空间分析"
geoclaw-claude memory vsearch "人类移动性出行模式" --top 5
geoclaw-claude memory vsearch "buffer analysis" --source memory

# 首次使用或新增大量记忆后重建索引
geoclaw-claude memory vsearch "任意词" --rebuild
```

**Python API：**

```python
from geoclaw_claude.memory import get_vector_search

vs = get_vector_search()
vs.load()                      # 加载持久化索引

# 添加文档（系统自动调用，也可手动）
vs.add(
    doc_id    = "ltm_abc123",
    text      = "武汉市医院空间分布：主城区密度显著高于郊区，三环内覆盖率约92%",
    title     = "武汉医院覆盖分析",
    tags      = ["wuhan", "hospital"],
    source    = "memory",
    importance= 0.8,
)

# 语义检索
results = vs.search("武汉医院覆盖", top_k=5)
for r in results:
    print(f"[{r.score:.3f}] {r.meta['title']}")
    print(f"         {r.snippet}")

# 按来源过滤
archive_hits = vs.search("空间分析", source_filter="archive", min_score=0.1)

vs.save()      # 持久化索引到磁盘

print(vs.stats())
# {"documents": 42, "vocab_size": 1856, "backend": "tfidf (zero-dependency)"}
# 安装 sentence-transformers 后 → "neural (sentence-transformers)"
```

---

### 4. 自动上下文压缩

对话历史超过 Token 阈值时，`GeoAgent` 在每轮前**自动**触发三级压缩，无需手动干预。

**三级压缩策略（按严重程度递进）：**

| 级别 | 策略 | 效果 |
|------|------|------|
| Level 1 | 摘要旧轮次，保留最近 N 条原文 | 轻度压缩，保留上下文语义 |
| Level 2 | 语义去重（删除连续相似消息） | 中度压缩，去除重复内容 |
| Level 3 | 强制截断，只保留最近 K 条 | 重度压缩，确保不超出限制 |

**配置（onboard 向导第 2 步，或随时手动修改）：**

```bash
geoclaw-claude config set ctx_max_tokens       6000   # 触发压缩的 token 阈值
geoclaw-claude config set ctx_target_tokens    4000   # 压缩后目标 token 数
geoclaw-claude config set ctx_keep_recent      6      # 始终保留最近 N 条原文
geoclaw-claude config set ctx_compress_verbose true   # 打印压缩日志
```

**手动调用（高级用法）：**

```python
from geoclaw_claude.nl.context_compress import compress_if_needed, CompressConfig

messages, report = compress_if_needed(
    messages,
    system_prompt = system_prompt,
    config = CompressConfig(max_tokens=6000, target_tokens=4000, keep_recent=6),
)
if report.level_applied > 0:
    print(report)
    # [压缩] Level 1 | 8200 → 3900 tokens (48%) | 20 → 7 条消息
```

---

### 5. Onboard 多模型配置向导

`geoclaw-claude onboard` 完全重构为 **6 步交互向导**，首次使用即可完成所有配置。

```
【1/6】AI 模型配置
  ├─ 首选 Provider（anthropic / gemini / openai / qwen，留空=自动优先级）
  ├─ Anthropic Claude  — API Key + 模型
  ├─ Google Gemini ✨  — API Key + 模型（含可选模型列表提示）
  ├─ OpenAI GPT        — API Key + 模型 + 自定义 base_url（支持代理）
  └─ 通义千问 Qwen     — API Key + 模型
  ✓ 保存后可选：立即发送测试请求验证 API 连接是否正常

【2/6】上下文压缩配置    — 触发阈值 / 目标大小 / 保留条数 / 日志开关
【3/6】数据目录配置      — data / cache / output / skill 四个目录
【4/6】网络配置          — HTTP 代理 / Overpass URL / 缓存 TTL
【5/6】制图配置          — 默认 CRS / 输出 DPI
【6/6】日志配置          — 日志级别
```

后期随时修改单项：

```bash
geoclaw-claude config set llm_provider gemini
geoclaw-claude config set gemini_api_key AIza...
geoclaw-claude config set gemini_model gemini-1.5-pro
geoclaw-claude config show
```

---

## 自然语言操作系统

GeoClaw-claude 的核心功能：用自然语言描述 GIS 操作，系统自动解析意图并执行。

### 工作原理

```
用户输入（自然语言）
       │
       ▼
  NLProcessor（意图解析）
  ├─ AI 模式    调用配置的 LLM（Claude / Gemini / GPT / Qwen）进行语义理解
  └─ 规则模式   关键词 + 正则本地解析（无 Key 时自动降级，完全离线）
       │
       ▼
  ParsedIntent { action, params, targets, confidence, steps }
       │
       ▼
  NLExecutor（GIS 执行）
  ├─ 映射到 geoclaw_claude 分析函数
  ├─ 图层上下文跨轮自动传递
  ├─ 操作结果自动写入 Memory 记忆系统
  └─ 上下文长度超限时自动触发三级压缩
       │
       ▼
  ExecutionResult { success, result, message, duration_ms }
```

### CLI 用法

```bash
# 单条指令
geoclaw-claude ask "对医院数据做1公里缓冲区"
geoclaw-claude ask "加载 hospitals.geojson 然后做500米缓冲区然后可视化"

# 调试模式：只解析意图，不实际执行
geoclaw-claude ask --dry-run "对医院做核密度分析"

# 指定模式
geoclaw-claude ask --rule "裁剪医院到边界范围"          # 强制规则模式（离线）
geoclaw-claude ask --ai   "叠加医院和地铁站分析服务覆盖"  # 强制 AI 模式

# 多轮对话（图层上下文在整个会话中保持）
geoclaw-claude chat
```

### Python API

```python
from geoclaw_claude.nl import GeoAgent

agent = GeoAgent()   # 自动选择 AI / 规则模式，自动压缩上下文

agent.chat("加载 data/wuhan/hospitals.geojson")
# ✓ 已加载 hospitals 图层，共 200 个要素  耗时: 0.12s

agent.chat("对医院做1公里缓冲区")
# ✓ 缓冲区完成，200 个要素，半径 1000.0m  耗时: 0.43s

agent.chat("用交互地图显示")
agent.end(title="武汉医院分析")   # 结束会话，自动写入长期记忆
```

### 支持的操作（30+）

| 类别 | 自然语言示例 |
|------|------------|
| 数据加载 | `"加载 hospitals.geojson"` · `"下载武汉市公园 OSM 数据"` |
| 缓冲区 | `"对医院做1公里缓冲区"` · `"做500米步行圈"` |
| 叠加分析 | `"用边界裁剪医院数据"` · `"取医院和地铁站的交集"` |
| 统计分析 | `"对医院做核密度分析"` · `"按行政区统计医院数量"` |
| 路网分析 | `"计算两点最短路径"` · `"做10分钟步行等时圈"` |
| 坐标转换 | `"把数据从 wgs84 转成 gcj02"` |
| 移动性 | `"读入 gps.csv"` · `"生成停留点"` · `"一键完成移动性分析"` |
| 移动性可视化 | `"轨迹地图"` · `"时间热力图"` · `"出行方式构成图"` |
| 可视化 | `"可视化当前结果"` · `"用交互地图显示"` |
| 多步流水线 | `"读入数据然后缓冲区然后叠加然后制图"` |

---

## 人类移动性分析

`geoclaw_claude/analysis/mobility/` 整合了 [trackintel](https://github.com/mie-lab/trackintel) 框架，提供从原始 GPS 轨迹到移动性指标的完整分析流水线。

> ⚠️ 核心轨迹处理算法来自 **trackintel**（ETH Zurich · mie-lab），详见文末[声明](#算法来源声明trackintel)。

### 数据层级

```
positionfixes   原始 GPS 轨迹点（CSV / GeoDataFrame）
      │  generate_staypoints()    空间阈值80m + 时间阈值5min
      ▼
staypoints      停留点
      │  generate_triplegs() + predict_transport_mode()
      ▼
triplegs        出行段（含交通方式：步行 / 骑行 / 公交 / 地铁）
      │  generate_trips()
      ▼
trips           完整出行（A → B）
      │  generate_locations()    DBSCAN 聚类（epsilon=120m）
      ▼
locations       重要地点（家 / 工作地 / 常去场所）
```

### 自然语言调用

```bash
# 逐步分析
geoclaw-claude ask "读入 data/mobility/wuhan_gps_tracks.csv"
geoclaw-claude ask "生成停留点"
geoclaw-claude ask "预测出行方式"
geoclaw-claude ask "识别家和工作地"

# 一键完成全部层级
geoclaw-claude ask "一键完成移动性分析"

# 可视化
geoclaw-claude ask "轨迹地图"
geoclaw-claude ask "时间热力图"
geoclaw-claude ask "出行方式构成图"
geoclaw-claude ask "移动性指标摘要"
```

### Python API

```python
from geoclaw_claude.analysis.mobility import (
    read_positionfixes, generate_full_hierarchy,
    identify_home_work, mobility_summary,
    plot_mobility_layers, plot_activity_heatmap,
    plot_modal_split, plot_mobility_metrics,
)

pfs = read_positionfixes(
    "data/mobility/wuhan_gps_tracks.csv",
    user_id_col="user_id", tracked_at_col="tracked_at",
    lon_col="longitude",   lat_col="latitude",
)

hierarchy = generate_full_hierarchy(
    pfs,
    dist_threshold=80, time_threshold=5,
    location_epsilon=120, predict_mode=True,
)
# 返回字典，包含: positionfixes / staypoints / triplegs / trips / locations

summary = mobility_summary(hierarchy)
locs    = identify_home_work(hierarchy["staypoints"], hierarchy["locations"])

plot_mobility_layers(hierarchy,                save_path="01_map.png")
plot_activity_heatmap(hierarchy["staypoints"], save_path="02_heatmap.png")
plot_modal_split(hierarchy["triplegs"],        save_path="03_modal.png")
plot_mobility_metrics(summary,                 save_path="04_dashboard.png")
```

### Demo 数据集

```bash
python examples/wuhan_mobility_demo.py   # 7 步流水线 + 6 张图表
```

| 字段 | 值 |
|------|----|
| 轨迹点数 | 37,549 |
| 用户数 | 5（金融 / IT / 贸易 / 科研 / 医疗） |
| 时间跨度 | 10 天（2024-01-15 ~ 2024-01-25） |
| 覆盖区域 | 武汉三镇（汉口 / 武昌 / 汉阳） |
| 出行方式 | 步行 / 骑行 / 公交 / 地铁 |

---

## Memory 记忆系统

四层记忆架构，从会话内状态到跨机器备份全覆盖：

```
ShortTermMemory    会话内操作日志 + 对象缓存（内存）
      │  session end → flush
      ▼
LongTermMemory     持久化 JSON 知识库  ~/.geoclaw_claude/memory/
      │  auto-index
      ▼
MemoryArchive      完整会话快照存档   ~/.geoclaw_claude/archives/      ← v2.3.0 ✨
      │  vectorize
      ▼
VectorSearch       TF-IDF / 神经网络语义索引  ~/.geoclaw_claude/vector_index/  ← v2.3.0 ✨
```

**Python API：**

```python
from geoclaw_claude.memory import get_memory, get_archive, get_vector_search

mem = get_memory()
mem.start_session("wuhan_analysis")

# 短期记忆
mem.log_op("buffer", "hospitals, 1km")
mem.remember("buf_result", buf_layer)
mem.set_context("city", "wuhan")

# 长期记忆
mem.learn(
    title="武汉医院分布规律",
    content={"finding": "医院集中在三环内，郊区密度低"},
    tags=["wuhan", "hospital"],
    importance=0.8,
)
results = mem.recall("武汉 医院")
mem.end_session(title="武汉医院覆盖分析复盘")

# 存档（v2.3.0）
arc = get_archive()
arc.save_session("武汉医院分析", ops_log=ops, tags=["wuhan"])
arc.search("武汉 医院")

# 向量检索（v2.3.0）
vs = get_vector_search()
vs.load()
results = vs.search("武汉医院核密度", top_k=5)
for r in results:
    print(f"[{r.score:.3f}] {r.meta['title']}")
```

**CLI 命令：**

```bash
# 长期记忆
geoclaw-claude memory status
geoclaw-claude memory search "武汉 医院"               # 关键词搜索
geoclaw-claude memory vsearch "武汉医院核密度分析"     # 向量语义搜索 ✨
geoclaw-claude memory list -c knowledge
geoclaw-claude memory learn "武汉人口密度" "约1万/km²" -t wuhan,population
geoclaw-claude memory export -o memory_backup.json

# 会话存档 ✨
geoclaw-claude memory archive list
geoclaw-claude memory archive list --tag wuhan
geoclaw-claude memory archive search "武汉 医院"
geoclaw-claude memory archive save -t "分析标题" -s "摘要说明"
geoclaw-claude memory archive export -o full_backup.json
geoclaw-claude memory archive import full_backup.json
geoclaw-claude memory archive stats
```

---

## 功能模块总览

| 模块 | 说明 |
|------|------|
| `core/` | `GeoLayer` 核心图层类，`GeoClawProject` 项目管理 |
| `io/` | GeoJSON / SHP 读写，OSM Overpass 下载，HTTP / WFS 远程数据 |
| `analysis/spatial_ops` | 缓冲区、裁剪、最近邻、KDE 核密度、面积统计 |
| `analysis/network` | 最短路径、等时圈、服务区（基于 OSMnx） |
| `analysis/raster_ops` | DEM 坡度/坡向、栅格重分类、分区统计（基于 rasterio） |
| `analysis/mobility/` | 人类移动性分析（trackintel 集成） |
| `cartography/` | 静态制图（4 主题）、Folium 交互地图 |
| `utils/coord_transform` | WGS84 ↔ GCJ-02 ↔ BD-09 坐标互转（纯数学实现） |
| `nl/processor` | NLProcessor：AI + 规则双模式意图解析 |
| `nl/executor` | NLExecutor：ParsedIntent → GIS 执行 |
| `nl/agent` | GeoAgent：多轮对话，自动压缩上下文 |
| `nl/context_compress` | ContextCompressor：三级自动上下文压缩 |
| `nl/llm_provider` | LLMProvider：Claude / Gemini / GPT / Qwen 统一适配 ✨ |
| `memory/short_term` | ShortTermMemory：会话内操作日志 + 对象缓存 |
| `memory/long_term` | LongTermMemory：持久化 JSON 知识库 |
| `memory/manager` | MemoryManager：统一管理入口 |
| `memory/archive` | MemoryArchive：会话快照存档系统 ✨ |
| `memory/vector_search` | VectorSearch：TF-IDF / 神经网络语义检索 ✨ |
| `skills/` | 用户自定义分析 Skill 脚本系统 |
| `updater` | 版本自检、自动更新、健康检测 |

---

## 安装与依赖

```bash
# 核心依赖
pip install geopandas osmnx rasterio trackintel scipy matplotlib folium click

# AI 模型（至少安装一个以启用 NL AI 模式，留空则使用离线规则模式）
pip install anthropic          # Claude
pip install google-genai       # Gemini ✨
pip install openai             # GPT / Qwen（共用同一个包）

# 可选增强
pip install sentence-transformers   # 神经网络向量检索（替代默认 TF-IDF）✨
```

| 包 | 用途 | 类型 |
|----|------|------|
| `geopandas` · `shapely` | 核心矢量处理 | 必须 |
| `pyproj` · `rasterio` | 投影与栅格分析 | 必须 |
| `networkx` · `osmnx` | 路网与等时圈分析 | 必须 |
| `trackintel ≥ 1.4.2` | 人类移动性分析 | 必须 |
| `scipy` | KDE 核密度等统计计算 | 必须 |
| `matplotlib` · `folium` | 静态图 + 交互地图 | 必须 |
| `click` | CLI 框架 | 必须 |
| `anthropic` | Claude AI（NL AI 模式） | 可选 |
| `google-genai` | Gemini AI（NL AI 模式）✨ | 可选 |
| `openai` | GPT / Qwen（NL AI 模式） | 可选 |
| `sentence-transformers` | 神经网络向量检索增强 ✨ | 可选 |

> **离线模式**：不安装任何 AI 包时，NL 系统自动降级为规则模式（关键词+正则），全部 GIS 功能仍然可用。

---

## 项目结构

```
GeoClaw_Claude/
├── geoclaw_claude/
│   ├── cli.py                        # CLI 入口（ask / chat / memory / check / ...）
│   ├── config.py                     # 配置管理（含 Gemini、上下文压缩所有参数）
│   ├── nl/
│   │   ├── processor.py              # NLProcessor：意图解析
│   │   ├── executor.py               # NLExecutor：GIS 执行
│   │   ├── agent.py                  # GeoAgent：多轮对话 + 自动压缩
│   │   ├── context_compress.py       # ContextCompressor：三级压缩策略
│   │   └── llm_provider.py           # LLMProvider：Claude/Gemini/GPT/Qwen ✨
│   ├── analysis/
│   │   ├── spatial_ops.py
│   │   ├── network.py
│   │   ├── raster_ops.py
│   │   └── mobility/                 # 人类移动性（trackintel）
│   │       ├── core.py               #   层级生成
│   │       ├── metrics.py            #   指标计算
│   │       └── visualization.py      #   可视化
│   ├── memory/
│   │   ├── short_term.py             # 会话内缓存
│   │   ├── long_term.py              # 持久化知识库
│   │   ├── manager.py                # 统一入口
│   │   ├── archive.py                # 会话存档 ✨ v2.3.0
│   │   └── vector_search.py          # 向量语义检索 ✨ v2.3.0
│   ├── cartography/
│   ├── io/
│   ├── core/
│   └── utils/
├── data/
│   ├── wuhan/                        # 武汉 GIS 示例数据（7 个 GeoJSON）
│   └── mobility/                     # GPS 轨迹测试数据（37,549 点）
├── examples/
│   └── wuhan_mobility_demo.py
├── tests/
│   ├── test_memory.py    (37)
│   ├── test_updater.py   (20)
│   ├── test_nl.py        (20)
│   ├── test_mobility.py  (20)
│   └── test_v230_new.py  (31)   ← G01-G10 Gemini · A01-A10 Archive · V01-V10 VectorSearch
├── docs/
│   ├── GeoClaw-claude_User_Guide_v2.2.1.pdf
│   └── GeoClaw-claude_Technical_Reference_v2.2.1.pdf
└── CHANGELOG.md
```

---

## 自我检测与自动更新

```bash
geoclaw-claude check            # 检测是否有新版本
geoclaw-claude update           # 拉取最新代码并重新安装
geoclaw-claude update --test    # 更新后自动运行测试套件
geoclaw-claude self-check       # 完整健康检测报告
```

---

## 测试矩阵

| 测试文件 | 项目数 | 覆盖范围 |
|---------|--------|---------|
| `test_memory.py` | 37 | ShortTermMemory / LongTermMemory / MemoryManager |
| `test_updater.py` | 20 | VersionInfo.parse / check / update / self_check |
| `test_nl.py` | 20 | NLProcessor / NLExecutor / GeoAgent / 30+ 操作 |
| `test_mobility.py` | 20 | GPS 层级生成 / 移动性指标 / 可视化 |
| `test_v230_new.py` | 31 | G01-G10 Gemini · A01-A10 Archive · V01-V10 VectorSearch |
| **合计** | **128** | **全部 ✅** |

---

## 版本历史

| 版本 | 亮点 |
|------|------|
| **v2.3.0** | Google Gemini API，MemoryArchive 会话存档，VectorSearch 向量检索，onboard 多模型 6 步向导，上下文压缩自动集成 |
| v2.2.1 | README 重组，NL 关键词映射修复，97/97 测试全绿 |
| v2.2.0 | 武汉 GPS 轨迹 Demo 数据集（37,549 点），完整 Demo 脚本，trackintel 来源声明 |
| v2.1.0 | `analysis/mobility/` 模块（trackintel 集成），10 类 NL 移动性操作 |
| v2.0.0 | 重大升级：自然语言 GIS 平台，多 Provider（Anthropic/OpenAI/Qwen），安全机制 |
| v1.3.0 | 自然语言操作系统（`nl/` 模块，`ask` / `chat` CLI） |
| v1.2.0 | 自我检测与自动更新（`check` / `update` / `self-check`） |
| v1.1.0 | Memory 记忆系统（短期+长期，`memory` CLI） |
| v1.0.0 | 首个正式版本：CLI、Skill 系统、路网/栅格分析 |

完整变更记录详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 算法来源声明：trackintel

`geoclaw_claude/analysis/mobility/` 中的核心轨迹处理算法来自 **trackintel** 开源框架：

| | |
|--|--|
| **GitHub** | https://github.com/mie-lab/trackintel |
| **开发团队** | Mobility Information Engineering Lab, ETH Zurich |
| **版本要求** | trackintel ≥ 1.4.2 |

引用论文：

> Martin, H., Hong, Y., Wiedemann, N., Bucher, D., & Raubal, M. (2023).
> Trackintel: An open-source Python library for human mobility analysis.
> *Computers, Environment and Urban Systems*, 101, 101938.
> https://doi.org/10.1016/j.compenvurbsys.2023.101938

GeoClaw-claude 在其基础上提供：统一 API 封装、GeoLayer 生态集成、**自然语言操作接口**、UrbanComp Lab 风格可视化输出。

---

## 关于

**GeoClaw-claude** 由 [UrbanComp Lab](https://urbancomp.net) 开发，服务于城市计算与地理信息科学研究。

MIT License © 2025 UrbanComp Lab
