# GeoClaw-claude

> **UrbanComp Lab** (https://urbancomp.net) 出品的轻量级 Python 地理信息分析工具集。

[![Version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.9+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![Lab](https://img.shields.io/badge/lab-UrbanComp-purple)](https://urbancomp.net)

参考 QGIS Processing Framework 设计，专注于城市地理空间数据分析。支持空间分析、路网分析、栅格处理、AI 驱动的 Skill 脚本系统。

---

## 快速开始

```bash
# 安装
bash install.sh

# 初始化（配置 API Key、数据目录等）
geoclaw-claude onboard

# 验证环境
geoclaw-claude test
```

---

## 功能模块

| 模块 | 功能 |
|------|------|
| `core/` | `GeoLayer` 核心图层类，`GeoClawProject` 项目管理 |
| `io/` | GeoJSON/SHP 读写，OSM 下载，HTTP/WFS 远程数据 |
| `analysis/spatial_ops` | 缓冲区、叠加、最近邻、KDE 核密度 |
| `analysis/network` | 最短路径、等时圈、服务区、路网统计 |
| `analysis/raster_ops` | DEM 坡度/坡向、重分类、栅格计算器、分区统计 |
| `cartography/` | 静态制图（4主题）、Folium 交互地图 |
| `utils/coord_transform` | WGS84 ↔ GCJ-02 ↔ BD-09 坐标互转 |
| `skills/` | 用户自定义分析 Skill 脚本系统 + AI 接口 |

---

## CLI 命令

```bash
geoclaw-claude onboard                          # 交互式初始化向导
geoclaw-claude config set anthropic_api_key KEY # 设置 AI Key
geoclaw-claude config show                      # 查看配置

geoclaw-claude download osm "武汉市" --type hospital    # 下载 OSM 数据
geoclaw-claude download url https://example.com/a.geojson

geoclaw-claude skill list                       # 列出 skill
geoclaw-claude skill run hospital_coverage \    # 运行 skill
    --data hospitals.geojson --ai
geoclaw-claude skill new my_analysis            # 创建 skill 模板
geoclaw-claude skill install ./my_analysis.py  # 安装 skill
```

---

## Skill 系统

用户可编写符合规范的 Python 脚本，通过 CLI 或 API 运行，支持调用 Claude AI 进行数据分析：

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

```python
from geoclaw_claude import GeoLayer, GeoClawProject
from geoclaw_claude.io.osm import download_pois, download_boundary
from geoclaw_claude.analysis.spatial_ops import buffer, kde
from geoclaw_claude.analysis.network import build_network, isochrone
from geoclaw_claude.analysis.raster_ops import load_raster, slope, zonal_stats
from geoclaw_claude.cartography.renderer import render_map
from geoclaw_claude.utils.coord_transform import wgs84_to_gcj02

# 下载武汉医院数据
boundary = download_boundary("武汉市")
hospitals = download_pois(boundary.bounds, poi_type="hospital")

# 路网等时圈
G   = build_network(boundary.bounds, network_type="drive")
iso = isochrone(G, center=(114.30, 30.60), minutes=[5, 10, 15])

# 渲染地图
render_map([hospitals, iso], title="武汉医院15分钟可达圈")
```

---

## 版本历史

详见 [CHANGELOG.md](CHANGELOG.md)

- **v1.0.0** — 正式版本，完整 CLI、Skill 系统、路网/栅格分析
- v0.2.0 — CLI 骨架、Skill 原型
- v0.1.0 — 初始内部版本

---

## 关于

**GeoClaw-claude** 由 [UrbanComp Lab](https://urbancomp.net) 开发，服务于城市计算与地理信息科学研究。

MIT License © 2025 UrbanComp Lab
