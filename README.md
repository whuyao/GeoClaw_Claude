# GeoClaw-claude

> **UrbanComp Lab** (https://urbancomp.net) 出品的轻量级 Python 地理信息分析工具集。

[![Version](https://img.shields.io/badge/version-2.0.0-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.9+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![Lab](https://img.shields.io/badge/lab-UrbanComp-purple)](https://urbancomp.net)

参考 QGIS Processing Framework 设计，专注于城市地理空间数据分析。支持空间分析、路网分析、栅格处理、AI 驱动的 Skill 脚本系统、跨会话 Memory 记忆系统、内置自动更新，以及**自然语言直接操作 GIS**（v2.0.0 核心功能）。

---

## 快速开始

```bash
# 克隆并安装
git clone https://github.com/whuyao/GeoClaw_Claude.git
cd GeoClaw_Claude
bash install.sh

# 初始化（配置 API Key、数据目录等）
geoclaw-claude onboard

# 直接用自然语言操作 GIS
geoclaw-claude ask "下载武汉市医院数据并做1公里缓冲区"

# 进入多轮对话模式
geoclaw-claude chat
```

---

## 功能模块

| 模块 | 功能 |
|------|------|
| `core/` | `GeoLayer` 核心图层类，`GeoClawProject` 项目管理 |
| `io/` | GeoJSON/SHP 读写，OSM 下载，HTTP/WFS 远程数据 |
| `analysis/spatial_ops` | 缓冲区、叠加、最近邻（UTM 精准距离）、KDE 核密度 |
| `analysis/network` | 最短路径、等时圈、服务区、路网统计 |
| `analysis/raster_ops` | DEM 坡度/坡向、重分类、栅格计算器、分区统计 |
| `cartography/` | 静态制图（4 主题）、Folium 交互地图 |
| `utils/coord_transform` | WGS84 ↔ GCJ-02 ↔ BD-09 坐标互转 |
| `memory/` | 短期记忆（会话缓存）+ 长期记忆（持久化知识库） |
| `nl/` | **自然语言操作**（NLProcessor / NLExecutor / GeoAgent） |
| `skills/` | 用户自定义分析 Skill 脚本系统 + AI 接口 |
| `updater` | 版本自检、自动拉取更新、全面健康检测 |

---

## CLI 命令

### 基础

```bash
geoclaw-claude onboard                           # 交互式初始化向导
geoclaw-claude config set anthropic_api_key KEY  # 设置 AI Key
geoclaw-claude config show                       # 查看配置
geoclaw-claude test                              # 运行环境测试
```

### 数据下载

```bash
geoclaw-claude download osm "武汉市" --type hospital    # 下载 OSM 数据
geoclaw-claude download url https://example.com/a.geojson
```

### Skill 系统

```bash
geoclaw-claude skill list                        # 列出所有 Skill
geoclaw-claude skill run hospital_coverage \     # 运行内置 Skill
    --data hospitals.geojson --ai
geoclaw-claude skill new my_analysis             # 创建 Skill 模板
geoclaw-claude skill install ./my_analysis.py   # 安装自定义 Skill
```

### 🧠 Memory 记忆系统

```bash
geoclaw-claude memory status                     # 查看记忆系统状态
geoclaw-claude memory list                       # 列出长期记忆条目
geoclaw-claude memory list -c knowledge          # 按类别筛选
geoclaw-claude memory search "武汉 医院"          # 关键词检索
geoclaw-claude memory learn "分析结论" "内容"    # 手动存入知识
geoclaw-claude memory forget <entry_id>          # 删除记忆条目
geoclaw-claude memory compact                    # 压缩旧记忆
geoclaw-claude memory export -o backup.json      # 导出为 JSON
```

### 🗣 自然语言操作

```bash
geoclaw-claude ask "对医院做1公里缓冲区"               # 单条自然语言 GIS 指令
geoclaw-claude ask "下载武汉市公园数据"                 # 下载并自动命名图层
geoclaw-claude ask "加载 hospitals.geojson 然后做500米缓冲区"  # 多步流水线
geoclaw-claude ask --dry-run "对医院做核密度分析"        # 只解析意图，输出 JSON
geoclaw-claude ask --rule "裁剪医院到边界范围内"         # 强制规则模式（离线）
geoclaw-claude ask --ai  "叠加医院和地铁站分析覆盖情况"  # 强制 AI 模式
geoclaw-claude chat                                    # 交互式多轮对话
geoclaw-claude chat --ai                               # 强制 AI 模式
```

### 🔄 自我检测与自动更新

```bash
geoclaw-claude check                             # 检测是否有新版本
geoclaw-claude check --json                      # JSON 格式输出
geoclaw-claude update                            # 拉取最新代码并安装
geoclaw-claude update --force                    # 强制更新
geoclaw-claude update --test                     # 更新后运行测试验证
geoclaw-claude self-check                        # 全面健康检测报告
geoclaw-claude self-check --quick                # 快速本地检测
geoclaw-claude self-check --json                 # JSON 格式输出
```

---

## 自然语言操作系统

GeoClaw-claude v2.0.0 的核心特性：用自然语言直接驱动 GIS 分析，无需记忆 API 函数名。

### 工作原理

```
用户输入（自然语言）
        ↓
  NLProcessor.parse()          ← 意图解析层
  · AI 模式：调用 Claude API 理解语义    （有 API Key 时自动启用）
  · 规则模式：关键词 + 正则本地解析       （无 Key 时自动降级，离线可用）
        ↓
  ParsedIntent                 ← 结构化意图
  { action, params, targets, confidence, steps }
        ↓
  NLExecutor.execute_intent()  ← GIS 执行层
  · 映射到 geoclaw_claude 分析函数
  · 图层上下文管理（命名图层字典）
  · 操作自动写入 Memory 系统
        ↓
  ExecutionResult              ← 执行结果
  { success, result, message, duration }
```

### 支持的自然语言操作

| 操作类型 | 示例描述 |
|---------|---------|
| 加载数据 | "加载 hospitals.geojson" |
| 缓冲区分析 | "对医院做1公里缓冲区" / "500米范围" |
| 裁剪 | "用边界裁剪医院数据" |
| 最近邻 | "计算医院到地铁站的最近邻距离" |
| 核密度 | "对医院做核密度分析" / "密度热力图" |
| 分区统计 | "按行政区统计医院数量" |
| 等时圈 | "以医院为中心做10分钟步行等时圈" |
| 最短路径 | "计算两点之间的最短驾车路径" |
| 坐标转换 | "把医院数据从 wgs84 转成 gcj02" |
| 下载 OSM | "下载武汉市公园数据" |
| 制图 | "可视化当前结果" / "用交互地图显示" |
| 多步流水线 | "对医院做1公里缓冲区然后可视化" |

### Python API

```python
from geoclaw_claude.nl import GeoAgent

# 创建代理（自动选择 AI/规则模式）
agent = GeoAgent()

# 多轮对话，图层上下文自动保持
agent.chat("加载 data/wuhan/hospitals.geojson")
# ✓ 已加载 200 个要素  耗时: 0.12s

agent.chat("对医院做1公里缓冲区")
# ✓ 缓冲区完成，200 个要素，半径 1000.0meters  耗时: 0.43s

agent.chat("然后用交互地图显示")
# ✓ 地图生成完成

# 查看对话历史
agent.print_history()

# 结束会话，自动写入长期记忆
agent.end(title="武汉医院缓冲区分析")
```

低置信度时代理会主动确认：

```python
agent.chat("差不多做个热力图那种东西")
# 我理解你想要：KDE 核密度分析（置信度 52%）
# 是否执行？(是/否)

agent.chat("是")
# ✓ 核密度分析完成，100×100 网格
```

---

## Memory 记忆系统

Memory 系统为 GeoClaw-claude 提供跨任务的知识积累能力，分为短期和长期两层：

### 短期记忆（ShortTermMemory）

```python
from geoclaw_claude.memory import get_memory

mem = get_memory()
mem.start_session("wuhan_hospital_analysis")

mem.log_op("buffer", "hospitals, 1km")           # 记录操作步骤
mem.remember("buf_hospitals", buf_layer)          # 缓存中间结果
layer = mem.recall_short("buf_hospitals")         # 读取缓存
mem.set_context("city", "wuhan")                  # 设置上下文
```

### 长期记忆（LongTermMemory）

持久化存储于 `~/.geoclaw_claude/memory/`，跨会话保留知识：

```python
mem.learn(
    title="武汉医院空间分布规律",
    content={"finding": "医院主要集中在三环内，外围覆盖不足"},
    tags=["wuhan", "hospital", "spatial"],
    importance=0.8,
)

results   = mem.recall("武汉 医院")               # 关键词检索
recent    = mem.recall_recent(n=5)                # 最近记忆
important = mem.recall_important(n=5, threshold=0.7)  # 最重要记忆
```

### 会话复盘（自动 flush）

```python
entry_id = mem.end_session(
    title="武汉医院覆盖分析复盘",
    tags=["wuhan", "hospital"],
    importance=0.8,
)
# → 自动记录：操作序列、耗时、成功/失败统计、中间结果列表
```

---

## 自我检测与自动更新

```python
from geoclaw_claude.updater import check, update, self_check, print_self_check

check()        # 检测远程最新版本
update()       # git pull + pip install -e .
print_self_check(self_check())
```

```
╔══ GeoClaw-claude 自我检测报告 ══════════════════════╗
║ 版本       本地: v2.0.0
║ 更新状态   ✓ 已是最新版本 v2.0.0
║            最新提交: [latest] feat: 升级至 v2.0.0
║ 模块完整性 17/17 模块正常
║ 依赖包     11/11 依赖就绪
╚══════════════════════════════════════════════════════╝
```

---

## Skill 系统

```python
# my_skill.py
SKILL_META = {"name": "my_analysis", "version": "1.0.0",
              "author": "your_name", "description": "我的分析脚本"}

def run(ctx):
    layer     = ctx.get_layer("input")
    radius_km = float(ctx.param("radius_km", 5.0))
    ai_result = ctx.ask_ai("请分析这些数据的空间分布特征")
    return ctx.result(output=result_layer)
```

```bash
geoclaw-claude skill install my_skill.py
geoclaw-claude skill run my_analysis --data data.geojson --ai
```

---

## Python API

```python
from geoclaw_claude import GeoLayer, GeoClawProject
from geoclaw_claude.io.vector import load_vector
from geoclaw_claude.analysis.spatial_ops import buffer, nearest_neighbor, kde
from geoclaw_claude.analysis.network import build_network, isochrone, shortest_path
from geoclaw_claude.analysis.raster_ops import load_raster, slope, reclassify, zonal_stats
from geoclaw_claude.utils.coord_transform import wgs84_to_gcj02, transform_layer

# 空间分析
hospitals = load_vector("hospitals.geojson")
buf       = buffer(hospitals, 1000, unit="meters")
result    = nearest_neighbor(hospitals, load_vector("metro_stations.geojson"))
density   = kde(hospitals, bandwidth=0.05, grid_size=100)

# 路网分析
G    = build_network(bbox, network_type="drive")
iso  = isochrone(G, center=(114.30, 30.60), minutes=[5, 10, 15])
path = shortest_path(G, origin=(114.30, 30.60), destination=(114.40, 30.70))

# 栅格分析
dem     = load_raster("dem.tif")
slp     = slope(dem)
reclass = reclassify(slp, [(0, 5, 1), (5, 15, 2), (15, 90, 3)])

# 坐标转换
gcj_layer = transform_layer(hospitals, "wgs84", "gcj02")
```

---

## 项目结构

```
GeoClaw_Claude/
├── geoclaw_claude/
│   ├── __init__.py             # 版本信息，公共导出
│   ├── config.py               # 配置系统（JSON + 环境变量）
│   ├── cli.py                  # Click CLI 入口
│   ├── skill_manager.py        # Skill 加载与运行
│   ├── updater.py              # 版本检测与自动更新        ← v1.2.0
│   ├── core/
│   │   ├── layer.py            # GeoLayer 核心类
│   │   └── project.py          # GeoClawProject 项目管理
│   ├── analysis/
│   │   ├── spatial_ops.py      # buffer / clip / nn / kde
│   │   ├── network.py          # 路网分析
│   │   └── raster_ops.py       # 栅格分析
│   ├── cartography/
│   │   ├── renderer.py         # 静态/交互制图
│   │   └── map_composer.py     # 多图层地图排版
│   ├── io/
│   │   ├── vector.py           # 矢量读写
│   │   ├── osm.py              # OSM 下载
│   │   └── remote.py           # HTTP / WFS / 天地图
│   ├── memory/                 # 跨会话记忆系统            ← v1.1.0
│   │   ├── short_term.py       # 会话内短期记忆（TTL / 操作日志）
│   │   ├── long_term.py        # 持久化长期记忆（JSON / 检索）
│   │   └── manager.py          # 统一管理器 + 全局单例
│   ├── nl/                     # 自然语言操作系统          ← v1.3.0 / v2.0.0
│   │   ├── processor.py        # NLProcessor（AI + 规则双模式）
│   │   ├── executor.py         # NLExecutor 意图→GIS 函数执行
│   │   └── agent.py            # GeoAgent 多轮对话代理
│   ├── utils/
│   │   └── coord_transform.py  # WGS84 / GCJ02 / BD09 互转
│   └── skills/
│       └── builtin/
│           └── hospital_coverage.py
├── data/wuhan/                 # 武汉示例数据（7 个 GeoJSON）
├── tests/
│   ├── test_memory.py          # Memory 测试（37 项）
│   ├── test_updater.py         # Updater 测试（20 项）
│   └── test_nl.py              # NL 模块测试（20 项）
├── install.sh
├── setup.py
└── CHANGELOG.md
```

---

## 依赖

| 包 | 用途 |
|----|------|
| `geopandas` | 核心矢量数据处理 |
| `shapely` | 几何运算 |
| `pyproj` | 坐标投影 |
| `rasterio` | 栅格数据读写 |
| `networkx` / `osmnx` | 路网构建与分析 |
| `scipy` | KDE 核密度估计 |
| `matplotlib` | 静态制图 |
| `folium` | 交互式地图 |
| `click` | CLI 框架 |
| `anthropic` | Claude AI 接口（NL AI 模式 + Skill 系统，可选） |

---

## 版本历史

完整记录详见 [CHANGELOG.md](CHANGELOG.md)

### v2.0.0 (2025-03-07) — 重大版本升级

标志着 GeoClaw-claude 正式迈入**自然语言驱动的智能 GIS 平台**时代。
自然语言操作系统完整测试验证，所有文档与代码同步，API 完全向下兼容 v1.x。

### v1.3.0 (2025-03-07) — 自然语言操作系统

新增 `nl/` 模块：`NLProcessor` 双模式意图解析（AI/规则）、`NLExecutor` GIS 执行引擎、`GeoAgent` 多轮对话代理。CLI 新增 `ask`（单条指令）和 `chat`（交互式对话）两个命令。NL 测试 20/20 通过。

### v1.2.0 (2025-03-07) — 自我检测与自动更新

新增 `updater.py`：`check()` 检测远程最新版本、`update()` 自动拉取安装（git pull + pip install）、`self_check()` 全面健康检测报告。CLI 新增 `check` / `update` / `self-check` 三个命令。Updater 测试 20/20 通过。

### v1.1.0 (2025-03-07) — Memory 记忆系统

新增 `memory/` 模块：`ShortTermMemory`（TTL 缓存 + 操作日志）、`LongTermMemory`（JSON 持久化 + 关键词检索）、`MemoryManager`（全局单例 + 会话复盘 flush）。CLI 新增 `memory` 命令组（8 个子命令）。Memory 测试 37/37 通过。同时修复 `nearest_neighbor()` 距离为 0 的 BUG，新增 `kde()` 函数。

### v1.0.0 (2025-03) — 首个正式版本

完整 CLI（`geoclaw-claude` 命令）、Skill 脚本系统、路网分析（最短路径/等时圈/服务区）、栅格分析（DEM/坡度/重分类/分区统计）、远程数据下载（HTTP/WFS/天地图）、坐标转换（WGS84/GCJ02/BD09）。

### v0.2.0 / v0.1.0

CLI 骨架与 Skill 原型（v0.2.0）；核心图层类、OSM 下载、空间分析初始版本（v0.1.0）。

---

## 关于

**GeoClaw-claude** 由 [UrbanComp Lab](https://urbancomp.net) 开发，服务于城市计算与地理信息科学研究。

MIT License © 2025 UrbanComp Lab
