# GeoClaw-claude

> **UrbanComp Lab** (https://urbancomp.net) 出品的轻量级 Python 地理信息分析工具集。

[![Version](https://img.shields.io/badge/version-1.3.0-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.9+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![Lab](https://img.shields.io/badge/lab-UrbanComp-purple)](https://urbancomp.net)

参考 QGIS Processing Framework 设计，专注于城市地理空间数据分析。支持空间分析、路网分析、栅格处理、AI 驱动的 Skill 脚本系统、跨会话 Memory 记忆系统，以及内置自动更新机制。

---

## 快速开始

```bash
# 克隆并安装
git clone https://github.com/whuyao/GeoClaw_Claude.git
cd GeoClaw_Claude
bash install.sh

# 初始化（配置 API Key、数据目录等）
geoclaw-claude onboard

# 检查是否有新版本
geoclaw-claude check

# 一键更新到最新版
geoclaw-claude update
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
| `skills/` | 用户自定义分析 Skill 脚本系统 + AI 接口 |
| `nl/` | 自然语言操作（NLProcessor / NLExecutor / GeoAgent） |
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
geoclaw-claude ask "对医院做1公里缓冲区"      # 单条自然语言 GIS 指令
geoclaw-claude ask "下载武汉市公园数据"        # 下载 + 命名图层
geoclaw-claude ask "加载data/h.geojson 然后做500米缓冲区"  # 多步流水线
geoclaw-claude ask --dry-run "核密度分析"      # 只解析意图，输出 JSON
geoclaw-claude ask --rule "裁剪到边界范围"     # 强制规则模式（离线）
geoclaw-claude chat                            # 交互式多轮对话
geoclaw-claude chat --ai                       # 强制 AI 模式
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

## Memory 记忆系统

Memory 系统为 GeoClaw-claude 提供跨任务的知识积累能力，分为短期和长期两层：

### 短期记忆（ShortTermMemory）

存活于单次任务会话内，会话结束后自动清除或转入长期记忆：

```python
from geoclaw_claude.memory import get_memory

mem = get_memory()
mem.start_session("wuhan_hospital_analysis")

# 记录操作步骤
mem.log_op("buffer", "hospitals, 1km")

# 缓存中间结果（支持 GeoLayer、ndarray、dict 等任意类型）
mem.remember("buf_hospitals", buf_layer)

# 读取缓存
layer = mem.recall_short("buf_hospitals")

# 设置会话上下文
mem.set_context("city", "wuhan")
```

### 长期记忆（LongTermMemory）

持久化存储于 `~/.geoclaw_claude/memory/`，跨会话保留知识：

```python
# 存入领域知识
mem.learn(
    title="武汉医院空间分布规律",
    content={"finding": "医院主要集中在三环内，外围覆盖不足"},
    tags=["wuhan", "hospital", "spatial"],
    importance=0.8,
)

# 关键词检索（标题 + 标签 + 内容 三层搜索）
results = mem.recall("武汉 医院")

# 获取最近记忆 / 最重要记忆
recent    = mem.recall_recent(n=5)
important = mem.recall_important(n=5, threshold=0.7)
```

### 会话复盘（自动 flush）

```python
# 结束会话时自动将操作摘要转入长期记忆
entry_id = mem.end_session(
    title="武汉医院覆盖分析复盘",
    tags=["wuhan", "hospital"],
    importance=0.8,
)
# → 自动记录：操作序列、耗时、成功/失败统计、中间结果列表
```

---

## 自我检测与自动更新

### 版本检测

```python
from geoclaw_claude.updater import check

result = check()
# [Check] 本地版本: v1.2.0
# [Check] 远程版本: v1.2.0
# [Check] 已是最新版本 v1.2.0 ✓
```

### 自动更新

```python
from geoclaw_claude.updater import update

result = update(run_tests=True)
# 步骤：版本检测 → git pull → pip install -e . → 打印 CHANGELOG → 运行测试
```

### 全面健康检查

```python
from geoclaw_claude.updater import self_check, print_self_check

print_self_check(self_check())
```

```
╔══ GeoClaw-claude 自我检测报告 ══════════════════════╗
║ 版本       本地: v1.2.0
║ 更新状态   ✓ 已是最新版本 v1.2.0
║            最新提交: [527182b] feat: 自我检测与自动更新
║ 模块完整性 17/17 模块正常
║ 依赖包     11/11 依赖就绪
║ Git        527182b feat: 自我检测与自动更新 v1.2.0
╚══════════════════════════════════════════════════════╝
```

---

## Skill 系统

用户可编写符合规范的 Python 脚本，通过 CLI 或 API 运行，支持调用 Claude AI 进行智能分析：

```python
# my_skill.py
SKILL_META = {
    "name":        "my_analysis",
    "version":     "1.0.0",
    "author":      "your_name",
    "description": "我的分析脚本",
}

def run(ctx):
    layer     = ctx.get_layer("input")
    radius_km = float(ctx.param("radius_km", 5.0))
    # ... 分析逻辑 ...
    ai_result = ctx.ask_ai("请分析这些数据的空间分布特征")
    return ctx.result(output=result_layer)
```

```bash
geoclaw-claude skill install my_skill.py
geoclaw-claude skill run my_analysis --data data.geojson --ai
```

---

## Python API

### 空间分析

```python
from geoclaw_claude import GeoLayer, GeoClawProject
from geoclaw_claude.io.vector import load_vector
from geoclaw_claude.analysis.spatial_ops import buffer, nearest_neighbor, kde

hospitals = load_vector("hospitals.geojson")

# 缓冲区分析（自动 UTM 投影，精准米制距离）
buf = buffer(hospitals, 1000, unit="meters")

# 最近邻分析（nn_distance 字段，单位：米）
metros = load_vector("metro_stations.geojson")
result = nearest_neighbor(hospitals, metros)

# KDE 核密度
density = kde(hospitals, bandwidth=0.05, grid_size=100)
# → {"grid": ndarray(100,100), "extent": (xmin,ymin,xmax,ymax), ...}
```

### 路网分析

```python
from geoclaw_claude.analysis.network import build_network, shortest_path, isochrone

G   = build_network(bbox, network_type="drive")
iso = isochrone(G, center=(114.30, 30.60), minutes=[5, 10, 15])
path = shortest_path(G, origin=(114.30, 30.60), destination=(114.40, 30.70))
```

### 栅格分析

```python
from geoclaw_claude.analysis.raster_ops import load_raster, slope, reclassify, zonal_stats

dem     = load_raster("dem.tif")
slp     = slope(dem)
reclass = reclassify(slp, [(0, 5, 1), (5, 15, 2), (15, 90, 3)])
stats   = zonal_stats(districts, hospitals, stat="count")
```

### 坐标转换

```python
from geoclaw_claude.utils.coord_transform import wgs84_to_gcj02, transform_layer

gcj_lon, gcj_lat = wgs84_to_gcj02(114.30, 30.60)
gcj_layer = transform_layer(hospitals, "wgs84", "gcj02")
```

### Memory 集成工作流

```python
from geoclaw_claude.memory import get_memory

mem = get_memory()
mem.start_session("my_analysis_task")
mem.log_op("load", "hospitals.geojson")
mem.remember("hospitals", hospitals)

# ... 执行分析 ...

mem.learn("武汉医院覆盖率", {"coverage": "82%"}, tags=["wuhan"])
mem.end_session(title="分析复盘")

# 下次会话中检索历史知识
results = mem.recall("武汉 医院")
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
│   ├── updater.py              # 版本检测与自动更新  ← v1.2.0
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
│   ├── memory/                 # ← v1.1.0
│   │   ├── short_term.py       # 会话内短期记忆（TTL / 操作日志）
│   │   ├── long_term.py        # 持久化长期记忆（JSON / 检索）
│   │   └── manager.py          # 统一管理器 + 全局单例
│   ├── utils/
│   │   └── coord_transform.py  # WGS84 / GCJ02 / BD09 互转
│   └── skills/
│       └── builtin/
│           └── hospital_coverage.py
├── data/wuhan/                 # 武汉示例数据（7 个 GeoJSON）
├── tests/
│   ├── test_memory.py          # Memory 测试（37 项）
│   └── test_updater.py         # Updater 测试（20 项）
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
| `anthropic` | Claude AI 接口（可选） |

---

## 版本历史

详见 [CHANGELOG.md](CHANGELOG.md)

| 版本 | 亮点 |
|------|------|
| **v1.3.0** | 自然语言操作（`ask` / `chat` 命令，AI+规则双模式解析） |
| **v1.2.0** | `check` / `update` / `self-check` 自动更新机制 |
| **v1.1.0** | Memory 系统（短期 + 长期记忆，`memory` CLI 命令组） |
| **v1.0.0** | 正式版本：完整 CLI、Skill 系统、路网/栅格分析 |
| v0.2.0 | CLI 骨架、Skill 原型 |
| v0.1.0 | 初始内部版本 |

---

## 关于

**GeoClaw-claude** 由 [UrbanComp Lab](https://urbancomp.net) 开发，服务于城市计算与地理信息科学研究。

MIT License © 2025 UrbanComp Lab
