# GeoClaw-claude

> **UrbanComp Lab** 出品的轻量级 Python 城市地理信息分析工具集。
> https://urbancomp.net

[![Version](https://img.shields.io/badge/version-2.2.1-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.9+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![trackintel](https://img.shields.io/badge/mobility-trackintel-9cf)](https://github.com/mie-lab/trackintel)
[![Lab](https://img.shields.io/badge/lab-UrbanComp-purple)](https://urbancomp.net)

参考 QGIS Processing Framework 设计，专注于城市地理空间数据分析。用**自然语言**直接驱动 GIS 操作，内置**人类移动性分析**（基于 trackintel）、跨会话记忆系统与自动更新机制。

---

## 快速开始

```bash
git clone https://github.com/whuyao/GeoClaw_Claude.git
cd GeoClaw_Claude && bash install.sh
geoclaw-claude onboard        # 初始化配置

# 自然语言 GIS
geoclaw-claude ask "下载武汉市医院数据并做1公里缓冲区"

# 自然语言移动性分析
geoclaw-claude ask "读入 data/mobility/wuhan_gps_tracks.csv"
geoclaw-claude ask "一键完成移动性分析"
geoclaw-claude ask "轨迹地图"
```

---

## 功能模块

| 模块 | 说明 |
|------|------|
| `core/` | `GeoLayer` 核心图层类，`GeoClawProject` 项目管理 |
| `io/` | GeoJSON/SHP 读写，OSM 下载，HTTP/WFS 远程数据 |
| `analysis/spatial_ops` | 缓冲区、叠加、最近邻、KDE 核密度 |
| `analysis/network` | 最短路径、等时圈、服务区 |
| `analysis/raster_ops` | DEM 坡度/坡向、栅格计算、分区统计 |
| `analysis/mobility/` | **人类移动性分析**（基于 trackintel，见下文详述） |
| `cartography/` | 静态制图（4 主题）、Folium 交互地图 |
| `utils/coord_transform` | WGS84 ↔ GCJ-02 ↔ BD-09 坐标互转 |
| `nl/` | **自然语言操作系统**（AI + 规则双模式，见下文详述） |
| `memory/` | 短期记忆（会话缓存）+ 长期记忆（持久化知识库） |
| `skills/` | 用户自定义分析 Skill 脚本系统 |
| `updater` | 版本自检、自动更新、健康检测 |

---

## 🗣 自然语言操作系统

GeoClaw-claude 的核心特性：**用自然语言直接驱动 GIS 分析，无需记忆 API 函数名**。

### 工作原理

```
用户输入（自然语言）
       ↓
  NLProcessor（意图解析）
  ├─ AI 模式   ── 调用 Claude API 理解语义（有 API Key 时自动启用）
  └─ 规则模式  ── 关键词+正则本地解析（无 Key 时降级，完全离线可用）
       ↓
  ParsedIntent { action, params, targets, confidence, steps }
       ↓
  NLExecutor（GIS 执行）
  ├─ 映射到 geoclaw_claude 分析函数
  ├─ 图层上下文自动传递（命名图层字典跨轮保持）
  └─ 操作自动写入 Memory 记忆系统
       ↓
  ExecutionResult { success, result, message, duration_ms }
```

### CLI 用法

```bash
# 单条指令
geoclaw-claude ask "对医院做1公里缓冲区"
geoclaw-claude ask "加载 hospitals.geojson 然后做500米缓冲区然后可视化"

# 调试：只解析意图，不执行
geoclaw-claude ask --dry-run "对医院做核密度分析"

# 强制规则模式（离线）/ 强制 AI 模式
geoclaw-claude ask --rule "裁剪医院到边界范围内"
geoclaw-claude ask --ai   "叠加医院和地铁站分析服务覆盖"

# 交互式多轮对话（图层上下文跨轮保持）
geoclaw-claude chat
```

### Python API

```python
from geoclaw_claude.nl import GeoAgent

agent = GeoAgent()   # 自动选择 AI / 规则模式

agent.chat("加载 data/wuhan/hospitals.geojson")
# ✓ 已加载 200 个要素  耗时: 0.12s

agent.chat("对医院做1公里缓冲区")
# ✓ 缓冲区完成，200 个要素，半径 1000.0m  耗时: 0.43s

agent.chat("用交互地图显示结果")
# ✓ 地图生成完成

agent.end(title="武汉医院分析")   # 结束会话，自动写入长期记忆
```

低置信度时代理会主动请求确认：

```python
agent.chat("差不多做个热力图那种东西")
# 我理解你想要：KDE 核密度分析（置信度 52%）
# 是否执行？(是/否)
agent.chat("是")
# ✓ 核密度分析完成，100×100 网格
```

### 支持操作（30+）

| 类别 | 自然语言示例 |
|------|------------|
| 数据加载 | `"加载 hospitals.geojson"` / `"下载武汉市公园数据"` |
| 空间分析 | `"对医院做1公里缓冲区"` / `"用边界裁剪医院数据"` |
| 统计分析 | `"对医院做核密度分析"` / `"按行政区统计医院数量"` |
| 路网分析 | `"计算两点间最短路径"` / `"做10分钟步行等时圈"` |
| 坐标转换 | `"把医院数据从 wgs84 转成 gcj02"` |
| **移动性** | `"读入 gps_tracks.csv"` / `"生成停留点"` / `"一键完成移动性分析"` |
| **移动性** | `"预测出行方式"` / `"时间热力图"` / `"轨迹地图"` / `"移动性指标摘要"` |
| 可视化 | `"可视化当前结果"` / `"用交互地图显示"` |
| 多步流水线 | `"读入数据然后生成停留点然后轨迹地图"` |

---

## 🚶 人类移动性分析（基于 trackintel）

`geoclaw_claude/analysis/mobility/` 整合了 [trackintel](https://github.com/mie-lab/trackintel) 框架，
提供从原始 GPS 轨迹到移动性指标的完整分析流水线，并支持**自然语言调用**。

> ⚠️ 核心轨迹处理算法来自 **trackintel**（ETH Zurich · mie-lab），详见文末[算法来源声明](#算法来源声明trackintel)。

### 数据层级模型

```
positionfixes  ← 原始 GPS 轨迹点（CSV / GeoDataFrame / DataFrame）
      ↓  generate_staypoints()     空间阈值 + 时间阈值双判定
staypoints     ← 停留点（在某位置停留超过 N 分钟）
      ↓  generate_triplegs()
triplegs       ← 出行段（含 predict_transport_mode() 交通方式标注）
      ↓  generate_trips()
trips          ← 出行（A→B 的一次完整出行）
      ↓  generate_locations()      DBSCAN 聚类
locations      ← 重要地点（家、工作地、常去场所）
```

### 自然语言调用（CLI）

```bash
# Step 1：读入 GPS 数据
geoclaw-claude ask "读入 data/mobility/wuhan_gps_tracks.csv"

# Step 2：逐步分析
geoclaw-claude ask "生成停留点"                  # 默认：距离 100m，时间 5min
geoclaw-claude ask "生成出行段"
geoclaw-claude ask "预测出行方式"
geoclaw-claude ask "识别重要地点"
geoclaw-claude ask "识别家和工作地"

# —— 或者：一句话完成全部层级 ——
geoclaw-claude ask "一键完成移动性分析"

# Step 3：可视化
geoclaw-claude ask "轨迹地图"                    # 停留点+出行段+重要地点叠加图
geoclaw-claude ask "时间热力图"                  # Weekday × Hour 活动矩阵
geoclaw-claude ask "出行方式构成图"
geoclaw-claude ask "移动性指标摘要"              # 回转半径、跳跃距离、覆盖率

# 多步流水线（一句话完成）
geoclaw-claude ask "读入 gps_tracks.csv 然后一键完成移动性分析然后轨迹地图"
```

### Python API

```python
from geoclaw_claude.analysis.mobility import (
    read_positionfixes,
    generate_full_hierarchy,
    predict_transport_mode,
    identify_home_work,
    mobility_summary,
    plot_mobility_layers,
    plot_activity_heatmap,
    plot_modal_split,
    plot_mobility_metrics,
)

# ① 读入数据
pfs = read_positionfixes(
    "data/mobility/wuhan_gps_tracks.csv",
    user_id_col="user_id",
    tracked_at_col="tracked_at",
    lon_col="longitude",
    lat_col="latitude",
)

# ② 一键生成完整层级
hierarchy = generate_full_hierarchy(
    pfs,
    dist_threshold=80,     # 停留判定：80m 范围内
    time_threshold=5,      # 停留判定：至少 5min
    location_epsilon=120,  # 地点聚类：120m 半径
    predict_mode=True,     # 自动预测出行方式
)
# 包含: positionfixes / staypoints / triplegs / trips / locations

# ③ 指标计算
summary = mobility_summary(hierarchy)
# {n_users, n_staypoints, radius_of_gyration_m, jump_length_m, modal_split, ...}

# ④ 识别家 / 工作地（OSNA 方法）
locs = identify_home_work(hierarchy["staypoints"], hierarchy["locations"], method="osna")

# ⑤ 可视化（输出图表均为英文标签）
plot_mobility_layers(hierarchy, save_path="01_mobility_map.png")
plot_activity_heatmap(hierarchy["staypoints"], save_path="02_heatmap.png")
plot_modal_split(hierarchy["triplegs"], save_path="03_modal.png")
plot_mobility_metrics(summary, save_path="04_dashboard.png")
```

### 可用指标

| 函数 | 说明 |
|------|------|
| `radius_of_gyration()` | 回转半径（活动范围大小，km） |
| `jump_lengths()` | 跳跃距离分布（单次出行距离，km） |
| `modal_split()` | 出行方式构成（次数/时长/距离口径） |
| `tracking_quality()` | 轨迹时间覆盖率（数据完整性，0~1） |
| `identify_home_work()` | 家/工作地识别（OSNA / 频率法） |
| `mobility_summary()` | 综合摘要（汇总以上所有核心指标） |

### Demo 数据集与完整案例

`data/mobility/` 提供武汉城市 GPS 轨迹测试数据：

| 项目 | 内容 |
|------|------|
| 文件 | `wuhan_gps_tracks.csv` |
| 规模 | 37,549 个轨迹点，5 位用户，10 天 |
| 地域 | 武汉三镇（汉口/武昌/汉阳） |
| 用户 | 金融从业者 / 互联网工程师 / 商贸从业者 / 高校研究员 / 医疗从业者 |
| 出行方式 | 地铁 / 公交 / 步行 / 骑行 |

运行完整 Demo（7 步分析 + 5 张图表）：

```bash
python examples/wuhan_mobility_demo.py
```

输出图表（`output/mobility_demo/`）：

| 图表文件 | 内容 |
|---------|------|
| `01_mobility_layers_map.png` | 分层地图：停留点 + 出行段（按交通方式上色）+ 重要地点 |
| `02_modal_split.png` | 出行方式构成：饼图 + 条形图 |
| `03_activity_heatmap_all.png` | 全体用户活动时间热力图（Weekday × Hour） |
| `03b_activity_heatmap_u0.png` | 单用户（Finance）活动热力图 |
| `04_mobility_metrics_dashboard.png` | 指标仪表盘：回转半径/跳跃距离/出行方式/覆盖率 |
| `05_user1_trajectory.png` | 单用户（IT Engineer·Optics Valley）个人轨迹图 |

---

## 🧠 Memory 记忆系统

```python
from geoclaw_claude.memory import get_memory

mem = get_memory()
mem.start_session("wuhan_analysis")

# 短期记忆（会话内）
mem.log_op("buffer", "hospitals, 1km")
mem.remember("buf_result", buf_layer)
mem.set_context("city", "wuhan")

# 长期记忆（跨会话持久化至 ~/.geoclaw_claude/memory/）
mem.learn(title="武汉医院分布规律",
          content={"finding": "医院集中在三环内"},
          tags=["wuhan", "hospital"], importance=0.8)
mem.recall("武汉 医院")
mem.end_session(title="本次分析复盘")   # 自动 flush
```

```bash
geoclaw-claude memory status
geoclaw-claude memory search "武汉 医院"
geoclaw-claude memory list -c knowledge
geoclaw-claude memory export -o backup.json
```

---

## 🔄 自我检测与自动更新

```bash
geoclaw-claude check            # 检测新版本
geoclaw-claude update           # 拉取最新代码并安装
geoclaw-claude update --test    # 更新后自动运行测试
geoclaw-claude self-check       # 全面健康检测报告
```

```python
from geoclaw_claude.updater import self_check, print_self_check
print_self_check(self_check())
# ╔══ GeoClaw-claude Self-Check ══════════════════╗
# ║ Version     local: v2.2.1  remote: v2.2.1 ✓
# ║ Modules     18/18 OK
# ║ Dependencies 12/12 OK
# ╚═══════════════════════════════════════════════╝
```

---

## Python API 速查

```python
# 空间分析
from geoclaw_claude.analysis.spatial_ops import buffer, nearest_neighbor, kde
from geoclaw_claude.analysis.network import build_network, isochrone, shortest_path
from geoclaw_claude.analysis.raster_ops import slope, reclassify, zonal_stats
from geoclaw_claude.utils.coord_transform import transform_layer

buf     = buffer(hospitals, 1000, unit="meters")
density = kde(hospitals, bandwidth=0.05, grid_size=100)
iso     = isochrone(G, center=(114.30, 30.60), minutes=[5, 10, 15])
gcj     = transform_layer(hospitals, "wgs84", "gcj02")

# Skill 脚本
# my_skill.py
SKILL_META = {"name": "my_analysis", "version": "1.0.0"}
def run(ctx):
    layer = ctx.get_layer("input")
    result = ctx.ask_ai("请分析数据的空间分布特征")
    return ctx.result(output=layer)
```

```bash
geoclaw-claude skill install my_skill.py
geoclaw-claude skill run my_analysis --data data.geojson --ai
```

---

## 项目结构

```
GeoClaw_Claude/
├── geoclaw_claude/
│   ├── cli.py                       # CLI（ask/chat/memory/check/update/...）
│   ├── nl/                          # 自然语言操作系统
│   │   ├── processor.py             #   NLProcessor（AI+规则双模式）
│   │   ├── executor.py              #   NLExecutor（意图→GIS 执行）
│   │   └── agent.py                 #   GeoAgent（多轮对话）
│   ├── analysis/
│   │   ├── spatial_ops.py
│   │   ├── network.py
│   │   ├── raster_ops.py
│   │   └── mobility/                # 人类移动性分析（trackintel）
│   │       ├── core.py              #   层级生成
│   │       ├── metrics.py           #   指标计算
│   │       └── visualization.py    #   可视化（英文标签）
│   ├── memory/                      # 记忆系统
│   ├── cartography/
│   ├── io/
│   ├── core/
│   └── utils/
├── data/
│   ├── wuhan/                       # 武汉 GIS 示例数据（7 个 GeoJSON）
│   └── mobility/                    # GPS 轨迹测试数据
│       ├── wuhan_gps_tracks.csv     #   37,549 个轨迹点
│       └── README.md
├── examples/
│   └── wuhan_mobility_demo.py       # 完整移动性分析 Demo
├── tests/
│   ├── test_memory.py    (37 项)
│   ├── test_updater.py   (20 项)
│   ├── test_nl.py        (20 项)
│   └── test_mobility.py  (20 项)
└── CHANGELOG.md
```

---

## 依赖

```bash
pip install geopandas osmnx rasterio trackintel anthropic
```

| 包 | 用途 |
|----|------|
| `geopandas` / `shapely` | 核心矢量处理 |
| `pyproj` / `rasterio` | 投影与栅格 |
| `networkx` / `osmnx` | 路网分析 |
| `trackintel ≥ 1.4.2` | 人类移动性分析 |
| `scipy` | KDE / 统计 |
| `matplotlib` / `folium` | 可视化 |
| `click` | CLI |
| `anthropic` | Claude AI（NL AI 模式，可选） |

---

## 版本历史

完整记录详见 [CHANGELOG.md](CHANGELOG.md)

| 版本 | 亮点 |
|------|------|
| **v2.2.1** | README 重组，移动性分析专节完善，NL 调用说明与 Demo 补全，NL 关键词映射修复 |
| v2.2.0 | 武汉 GPS 轨迹测试数据集，完整 Demo 脚本，trackintel 算法来源声明 |
| v2.1.0 | `analysis/mobility/` 模块（trackintel 集成），NL 移动性操作支持（10 类） |
| v2.0.0 | 重大升级，自然语言 GIS 平台，文档与代码全面同步 |
| v1.3.0 | 自然语言操作系统（`nl/` 模块，`ask` / `chat` 命令） |
| v1.2.0 | 自我检测与自动更新（`check` / `update` / `self-check`） |
| v1.1.0 | Memory 记忆系统（短期+长期，`memory` CLI） |
| v1.0.0 | 首个正式版本：CLI、Skill、路网/栅格分析 |

---

## 算法来源声明：trackintel

`geoclaw_claude/analysis/mobility/` 中的核心轨迹处理算法来自 **trackintel** 开源框架：

| | |
|--|--|
| **GitHub** | https://github.com/mie-lab/trackintel |
| **开发团队** | Mobility Information Engineering Lab, ETH Zurich (mie-lab.ethz.ch) |
| **版本要求** | trackintel ≥ 1.4.2 |

引用论文：

> Martin, H., Hong, Y., Wiedemann, N., Bucher, D., & Raubal, M. (2023).
> Trackintel: An open-source Python library for human mobility analysis.
> *Computers, Environment and Urban Systems*, 101, 101938.
> https://doi.org/10.1016/j.compenvurbsys.2023.101938

trackintel 提供的核心算法：`generate_staypoints` / `generate_triplegs` / `generate_trips` / `generate_locations` / `predict_transport_mode` / `location_identifier` / `radius_gyration` / `jump_length` / `temporal_tracking_quality`

GeoClaw-claude 在其基础上提供：统一 API 封装、GeoLayer 生态集成、**自然语言操作接口**、UrbanComp Lab 风格可视化。原始算法实现归属 trackintel 项目及其作者。

---

## 关于

**GeoClaw-claude** 由 [UrbanComp Lab](https://urbancomp.net) 开发，服务于城市计算与地理信息科学研究。

MIT License © 2025 UrbanComp Lab
