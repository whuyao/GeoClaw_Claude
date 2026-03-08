# GeoClaw — 开发文档

> Python GIS 分析工具集 | v0.1.0 | 2026-03

---

## 目录

1. [项目概述](#1-项目概述)
2. [文件结构](#2-文件结构)
3. [环境配置](#3-环境配置)
4. [安装与运行](#4-安装与运行)
5. [模块说明](#5-模块说明)
6. [武汉案例数据](#6-武汉案例数据)
7. [运行测试](#7-运行测试)
8. [开发路线图](#8-开发路线图)
9. [代码规范](#9-代码规范)
10. [常见问题](#10-常见问题)

---

## 1. 项目概述

**GeoClaw** 是一个参考 QGIS Processing Framework 设计的轻量级 Python 地理信息分析工具集，目标是提供：

- 与 QGIS 概念相近的 Python API（GeoLayer ≈ QgsVectorLayer，GeoClawProject ≈ .qgz 项目）
- 从数据获取 → 空间分析 → 制图输出的完整工作流
- 以武汉市 OpenStreetMap 数据作为标准测试用例

**当前版本 (v0.1)** 实现了：
- 城市数据下载（Overpass API：医院、高校、公园、地铁、道路、水体）
- 空间分析：缓冲区、叠加分析、最近邻、KDE 核密度、分区统计
- 专业静态制图：4 种主题、比例尺、指北针、图例
- 交互式 Web 地图：Folium（POI 弹窗、点聚合、图层控制）

---

## 2. 文件结构

```
GeoClaw-Claude/                     ← 项目根目录（放到任意本地路径）
│
├── geoclaw_claude/                        ← 主包（Python Package）
│   ├── __init__.py                 ← 包入口；快速导入 GeoLayer / GeoClawProject
│   │
│   ├── core/                       ← 核心数据结构
│   │   ├── layer.py                ← GeoLayer — 空间数据层（封装 GeoDataFrame）
│   │   └── project.py              ← GeoClawProject — 项目管理器
│   │
│   ├── analysis/                   ← 空间分析算法
│   │   ├── spatial_ops.py          ← 矢量分析（缓冲区、叠加、连接、统计）
│   │   └── network.py              ← 网络分析（服务圈、KDE 密度、可达性）
│   │
│   ├── cartography/                ← 制图渲染
│   │   ├── map_composer.py         ← 静态地图制图引擎（4 种主题）
│   │   └── renderer.py             ← 交互式地图渲染器（Folium Web Map）
│   │
│   ├── io/                         ← 数据输入输出
│   │   ├── vector.py               ← 矢量数据读写（GeoJSON/SHP/GPKG/CSV）
│   │   └── osm.py                  ← OSM 数据下载（Overpass API）
│   │
│   └── utils/                      ← 工具函数（预留，当前为空）
│       └── __init__.py
│
├── data/                           ← 测试数据
│   └── wuhan/                      ← 武汉市 OpenStreetMap 数据（已下载，离线使用）
│       ├── boundary.geojson        ← 武汉市行政边界（MultiPolygon）
│       ├── hospitals.geojson       ← 医院 200 个（Point，含名称/运营商等属性）
│       ├── universities.geojson    ← 高校 62 所（Point）
│       ├── parks.geojson           ← 公园 200 个（Point）
│       ├── metro_stations.geojson  ← 地铁站 624 个（Point）
│       ├── roads_main.geojson      ← 主干路 600 段（LineString：高速/快速/主干）
│       └── water.geojson           ← 水体 300 个（Point 质心：湖泊/河流）
│
├── examples/                       ← 示例脚本
│   └── wuhan_analysis.py           ← 完整武汉案例（9 步分析 + 5 张地图输出）
│
├── tests/                          ← 测试套件
│   └── test_environment.py         ← 环境检查 + 功能单元测试（25 项）
│
├── docs/                           ← 文档目录（预留）
│
├── requirements.txt                ← Python 依赖清单
└── DEVELOPMENT.md                  ← 本文档（开发指南）
```

---

## 3. 环境配置

### 3.1 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS 12+ / Ubuntu 20.04+ / Windows 10+ (WSL2 推荐) |
| Python | **3.10 或以上**（推荐 3.11/3.12） |
| 内存 | ≥ 4 GB（处理大型 OSM 数据时建议 8 GB） |
| 磁盘空间 | ≥ 500 MB（含 Python 环境） |
| 网络 | 首次下载 OSM 数据需访问 overpass-api.de（境内可能较慢） |

### 3.2 推荐使用虚拟环境

**方式一：conda（推荐，最稳定）**

```bash
# 创建环境
conda create -n geoclaw_claude python=3.11 -y
conda activate geoclaw_claude

# 安装核心 GIS 包（conda-forge 频道）
conda install -c conda-forge geopandas shapely pyproj rasterio pyogrio -y

# 安装其余依赖
pip install folium osmnx matplotlib-scalebar mapclassify contextily scipy networkx requests
```

**方式二：venv（纯 Python）**

```bash
# 进入项目目录
cd GeoClaw_Claude

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate.bat     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3.3 中文字体配置（可选，显示地图中文标注）

GeoClaw 自动检测系统中的 CJK 字体，推荐安装：

```bash
# macOS
brew install font-noto-sans-cjk

# Ubuntu/Debian
sudo apt install fonts-noto-cjk

# 安装后刷新 matplotlib 字体缓存
python3 -c "import matplotlib.font_manager as fm; fm._load_fontmanager(try_read_cache=False); print('字体缓存已更新')"
```

---

## 4. 安装与运行

### 4.1 配置 Python 路径

GeoClaw 当前不是安装包，需要手动将项目根目录加入 Python 路径。

**方式一：在脚本头部添加（推荐）**

```python
import sys
sys.path.insert(0, "/path/to/GeoClaw_Claude")  # 仅未安装时需要，安装后无需此行

from geoclaw_claude.core.layer import GeoLayer
from geoclaw_claude.io.osm import load_wuhan_data
```

**方式二：设置环境变量（全局）**

```bash
export PYTHONPATH="/path/to/GeoClaw_Claude:$PYTHONPATH"  # 仅未安装时需要
```

**方式三：开发模式安装**

```bash
# 克隆后在项目根目录运行
git clone https://github.com/whuyao/GeoClaw_Claude.git
cd GeoClaw_Claude && bash install.sh --dev  # 可编辑模式，代码修改即时生效
```

### 4.2 运行武汉案例

```bash
# 激活环境
conda activate geoclaw_claude  # 或 source .venv/bin/activate

# 进入项目根目录
cd GeoClaw_Claude

# 运行完整分析（约 1-2 分钟）
python3 examples/wuhan_analysis.py
```

**输出文件**（默认保存至 `output/wuhan/`）：

| 文件名 | 内容 |
|--------|------|
| `01_wuhan_overview_urban.png` | 城区概览图（暗色主题） |
| `02_hospital_coverage.png` | 医院 1/3/5km 服务覆盖分析 |
| `03_metro_university.png` | 地铁站与高校分布（蓝图主题） |
| `04_hospital_kde.png` | 医疗资源核密度热力图 |
| `05_interactive_map.html` | 交互式 Web 地图（浏览器打开） |

### 4.3 快速上手（Python 交互式）

```python
import sys
sys.path.insert(0, "/path/to/GeoClaw_Claude")  # 仅未安装时需要，安装后无需此行

from geoclaw_claude.io.osm import load_wuhan_data
from geoclaw_claude.analysis.network import service_area_buffers
from geoclaw_claude.cartography.map_composer import MapComposer

# 1. 加载数据
layers    = load_wuhan_data("data/wuhan")
hospitals = layers["hospitals"]
print(hospitals.summary())

# 2. 服务圈分析
rings = service_area_buffers(hospitals, distances_km=[1, 3, 5])

# 3. 出图
MapComposer(title="医院服务覆盖", palette="light") \
    .add_layer(rings, color="#ef5350", alpha=0.2, label="服务圈") \
    .add_layer(hospitals, role="hospital", label="医院") \
    .render("output/my_map.png")
```

---

## 5. 模块说明

### geoclaw_claude.core.layer — GeoLayer

空间数据层的核心抽象，所有空间操作的基本单元。

```python
from geoclaw_claude.core.layer import GeoLayer

layer = GeoLayer(gdf, name="武汉医院", source="OSM/hospitals.geojson")

# 属性
layer.feature_count   # 要素数
layer.geometry_type   # Point / LineString / Polygon
layer.epsg            # EPSG 代码（int）
layer.bounds          # (minx, miny, maxx, maxy)
layer.columns         # 属性字段列表

# 方法（均返回新 GeoLayer，不修改原数据）
layer.reproject(32650)                       # 投影转换
layer.filter_by_attribute("name", "", "!=") # 属性过滤
layer.filter_by_extent((113.7, 30.0, 115.0, 31.0))  # 空间过滤
print(layer.summary())                       # 摘要
print(layer.history())                       # 操作历史
```

### geoclaw_claude.analysis.spatial_ops — 空间分析

```python
from geoclaw_claude.analysis.spatial_ops import (
    buffer, intersect, clip, nearest_neighbor,
    spatial_join, calculate_area, zonal_stats
)

buf    = buffer(layer, 1000, unit="meters")     # 缓冲区
clipped = clip(target, mask)                     # 裁剪
nn     = nearest_neighbor(metro, hospitals)      # 最近邻（新增 nn_distance 字段）
joined = spatial_join(source, target)            # 空间连接
areas  = calculate_area(layer, unit="km2")       # 面积计算
stats  = zonal_stats(zones, points, stat="count") # 分区统计
```

### geoclaw_claude.analysis.network — 网络与密度分析

```python
from geoclaw_claude.analysis.network import service_area_buffers, point_density

# 服务圈分析
rings = service_area_buffers(hospitals, distances_km=[1, 3, 5])

# KDE 核密度（返回网格数组，用于热力图渲染）
kde = point_density(hospitals, resolution=0.005, bandwidth=0.04)
# kde["X"], kde["Y"], kde["Z"], kde["extent"]
```

### geoclaw_claude.cartography.map_composer — 静态制图

```python
from geoclaw_claude.cartography.map_composer import MapComposer

composer = MapComposer(
    figsize=(16, 12), dpi=150,
    palette="urban",           # urban | light | satellite | blueprint
    title="地图标题",
    subtitle="数据来源注释",
)

# add_layer 支持链式调用
composer \
    .add_layer(boundary, role="boundary", label="边界") \
    .add_layer(roads,    role="road",     alpha=0.4) \
    .add_layer(hospitals,role="hospital", markersize=6) \
    .add_kde_heatmap(kde_data, cmap="hot") \
    .render("output/map.png")
```

**role 参数自动配色对照表：**

| role | 颜色策略 |
|------|----------|
| `boundary` | 透明填充 + 灰色边框 |
| `water` | 主题水体色 |
| `road` | 主题道路色 |
| `park` | 主题公园色 |
| `hospital` | 红色 #e53935 |
| `university` | 紫色 #7b1fa2 |
| `metro` | 橙色 #f57f17 |
| `poi` | 主题 POI 色 |

### geoclaw_claude.io.osm — OSM 数据下载

```python
from geoclaw_claude.io.osm import download_pois, download_roads, download_boundary, load_wuhan_data

# 武汉市 bbox
WUHAN_BBOX = (113.7, 29.97, 115.08, 31.36)  # (west, south, east, north)

# 下载 POI（需要网络）
hospitals  = download_pois(WUHAN_BBOX, poi_type="hospital")
parks      = download_pois(WUHAN_BBOX, poi_type="park", max_results=200)

# 下载路网
roads = download_roads(WUHAN_BBOX, level="major")  # all|major|highway|primary

# 下载行政边界
boundary = download_boundary("Wuhan, Hubei, China")

# 加载已下载的武汉数据（离线，不需要网络）
layers = load_wuhan_data("data/wuhan")  # dict: {name: GeoLayer}
```

---

## 6. 武汉案例数据

`data/wuhan/` 目录包含 2026年3月 从 OpenStreetMap 下载的武汉市地理数据：

| 文件 | 要素数 | 几何类型 | 主要字段 |
|------|--------|----------|----------|
| boundary.geojson | 1 | MultiPolygon | name, admin_level |
| hospitals.geojson | 200 | Point | name, operator, healthcare, phone |
| universities.geojson | 62 | Point | name, operator, website |
| parks.geojson | 200 | Point | name, leisure |
| metro_stations.geojson | 624 | Point | name, public_transport |
| roads_main.geojson | 600 | LineString | name, highway, maxspeed, lanes |
| water.geojson | 300 | Point（质心） | name, water |

数据遵循 [ODbL 1.0 开放数据许可](https://opendatacommons.org/licenses/odbl/1-0/)。

**坐标系**：所有数据均为 **EPSG:4326**（WGS84 地理坐标）。

**武汉 UTM 投影**（需要米单位计算时）：**EPSG:32650**（UTM Zone 50N）

---

## 7. 运行测试

```bash
# 方式一：直接运行测试脚本
python3 tests/test_environment.py

# 方式二：pytest（需安装 pytest）
pip install pytest
pytest tests/ -v

# 预期输出：25/25 PASSED
```

**测试覆盖范围**：

- 环境依赖检查（geopandas/shapely/folium 等）
- GeoLayer 创建、属性访问、过滤操作
- 空间分析：buffer / clip / nearest_neighbor
- 制图：MapComposer 渲染输出
- I/O：矢量读写

---

## 8. 开发路线图

### v0.2（下一版本）

**高优先级：**
- [ ] `analysis/raster_ops.py` — 栅格分析（DEM 加载、坡度计算、重分类、栅格叠加）
- [ ] `analysis/network.py` → `shortest_path()` — Dijkstra 最短路径，返回路径几何 + 时间
- [ ] `analysis/network.py` → `isochrone()` — 等时圈分析（N 分钟可达范围）
- [ ] `cartography/map_composer.py` → `add_labels()` — 地图要素标注（需处理碰撞）

**中优先级：**
- [ ] `cartography/map_composer.py` → `add_inset_map()` — 区位示意小地图
- [ ] `cartography/map_composer.py` → contextily 底图集成（OSM 底图、卫星图）
- [ ] `io/vector.py` — 支持 KML / GML 格式读取
- [ ] 添加 `setup.py` / `pyproject.toml`，支持 `pip install -e .`

### v0.3

- [ ] `io/postgis.py` — PostGIS 数据库连接器（读写空间查询）
- [ ] `reporting/report.py` — HTML/PDF 分析报告自动生成
- [ ] `io/wfs_wms.py` — Web 地图服务接入（OGC WFS/WMS/WMTS）
- [ ] `processing/pipeline.py` — 批处理 Pipeline API（链式分析流）

---

## 9. 代码规范

- **语言**：Python 3.10+，使用 `from __future__ import annotations`
- **文档字符串**：所有 public 函数必须有 Google 风格 docstring（含 Args/Returns/TODO）
- **类型标注**：函数签名使用类型标注，复杂类型使用 `from typing import ...`
- **不可变原则**：所有空间操作函数返回**新的 GeoLayer**，不修改输入数据
- **编码**：源码 UTF-8，字符串尽量用 f-string
- **格式化**：推荐使用 `black` 自动格式化：`black geoclaw_claude/`
- **命名规范**：
  - 模块：`snake_case.py`
  - 类：`PascalCase`
  - 函数/变量：`snake_case`
  - 常量：`UPPER_SNAKE_CASE`

---

## 10. 常见问题

**Q: 运行时报 `ModuleNotFoundError: No module named 'geoclaw_claude'`**

```python
# 在脚本最开头添加：
import sys
sys.path.insert(0, "/path/to/GeoClaw_Claude")  # 仅未安装时需要，安装后无需此行
```

**Q: 地图中文标题显示为方块**

系统缺少 CJK 字体，执行：

```bash
# macOS
brew install font-noto-sans-cjk
python3 -c "import matplotlib.font_manager as fm; fm._load_fontmanager(try_read_cache=False)"
```

**Q: Overpass API 下载超时**

Overpass 公共服务器有速率限制，可以：
1. 使用 `load_wuhan_data()` 直接加载本地已下载数据（推荐）
2. 减小 `max_results` 参数
3. 等待 60 秒后重试

**Q: `geopandas.sjoin_nearest` 警告 "Geometry is in a geographic CRS"**

正常警告，`nearest_neighbor()` 函数内部会投影到 UTM 后计算距离，结果是正确的。  
`nn_distance = 0` 是已知 BUG，正在修复（见 `network.py` TODO）。

**Q: macOS 上安装 geopandas 失败**

优先使用 conda-forge：

```bash
conda install -c conda-forge geopandas
```

**Q: Windows 下 Shapefile 中文属性乱码**

```python
layer = load_vector("data.shp", encoding="gbk")  # 国内数据通常为 GBK 编码
```

---

*GeoClaw v0.1.0 | 最后更新: 2026-03*
