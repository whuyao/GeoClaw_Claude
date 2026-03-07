# data/mobility — 移动性分析测试数据

## 数据概述

本目录包含 GeoClaw-claude 移动性分析模块（trackintel 集成）的测试数据和 Demo 数据。

## 文件清单

| 文件 | 说明 | 大小 |
|------|------|------|
| `wuhan_gps_tracks.csv` | 武汉城市 GPS 轨迹测试数据（主数据） | ~3 MB |
| `users_meta.csv` | 用户元数据（背景信息） | <1 KB |
| `generate_data.py` | 数据生成脚本（可重新生成） | — |

---

## 主数据：wuhan_gps_tracks.csv

### 数据规模

- **轨迹点总数**: 37,549 个
- **用户数量**: 5 位武汉居民
- **时间范围**: 2024-01-15 ~ 2024-01-25（10 天）
- **地理范围**: 武汉三镇（汉口/武昌/汉阳）

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 轨迹点唯一 ID（索引） |
| `user_id` | int | 用户 ID（0-4） |
| `tracked_at` | datetime(UTC) | 记录时间（UTC 时区） |
| `longitude` | float | 经度（WGS84） |
| `latitude` | float | 纬度（WGS84） |
| `elevation` | float | 海拔（米，模拟值） |
| `accuracy` | float | 定位精度（米，模拟值） |

### 用户背景

| user_id | 职业 | 居住地 | 工作地 | 通勤方式 |
|---------|------|--------|--------|---------|
| 0 | 金融从业者 | 汉口后湖 | 武昌中南路 | 地铁 |
| 1 | 互联网工程师 | 武昌洪山广场 | 光谷软件园 | 公交 |
| 2 | 商贸从业者 | 汉阳知音湖 | 汉口江汉路 | 步行 |
| 3 | 高校研究员 | 武昌光谷 | 武汉大学 | 骑行 |
| 4 | 医疗从业者 | 汉口新华路 | 协和医院 | 地铁 |

---

## 使用方法

### 快速开始

```python
from geoclaw_claude.analysis.mobility import (
    read_positionfixes,
    generate_full_hierarchy,
    mobility_summary,
    plot_mobility_layers,
)

# 读入数据
pfs = read_positionfixes(
    "data/mobility/wuhan_gps_tracks.csv",
    user_id_col="user_id",
    tracked_at_col="tracked_at",
    lon_col="longitude",
    lat_col="latitude",
)

# 一键生成完整移动性层级
hierarchy = generate_full_hierarchy(pfs, dist_threshold=80, time_threshold=5)

# 指标摘要
print(mobility_summary(hierarchy))

# 可视化
plot_mobility_layers(hierarchy, save_path="mobility_map.png")
```

### 完整 Demo

运行完整 Demo 脚本（生成 5 张分析图表）：

```bash
python examples/wuhan_mobility_demo.py
```

Demo 输出位于 `output/mobility_demo/`：

| 图表文件 | 内容 |
|---------|------|
| `01_mobility_layers_map.png` | 分层移动性地图（停留点/出行段/重要地点） |
| `02_modal_split.png` | 出行方式构成图 |
| `03_activity_heatmap_all.png` | 全体用户活动时间热力图 |
| `03b_activity_heatmap_u0.png` | 用户0（金融从业者）活动热力图 |
| `04_mobility_metrics_dashboard.png` | 移动性指标综合仪表盘 |
| `05_user1_trajectory.png` | 用户1（互联网工程师）个人轨迹图 |

---

## 数据层级处理结果（参考值）

以默认参数 `dist_threshold=80m, time_threshold=5min` 处理后：

| 层级 | 数量 | 说明 |
|------|------|------|
| positionfixes | 37,549 | 原始 GPS 轨迹点 |
| staypoints | ~1,781 | 停留点（5分钟内80米范围内） |
| triplegs | ~1,240 | 出行段（停留点间的连续移动） |
| trips | ~1,240 | 出行（活动停留点间） |
| locations | ~20 | 重要地点（DBSCAN 聚类，半径120米） |

---

## 算法来源

本模块中的轨迹数据处理算法基于 **trackintel** 开源框架：

- **GitHub**: https://github.com/mie-lab/trackintel
- **开发团队**: ETH Zurich · Mobility Information Engineering Lab (mie-lab.ethz.ch)
- **论文**:
  > Martin, H., Hong, Y., Wiedemann, N., Bucher, D., & Raubal, M. (2023).
  > Trackintel: An open-source Python library for human mobility analysis.
  > *Computers, Environment and Urban Systems*, 101, 101938.
  > https://doi.org/10.1016/j.compenvurbsys.2023.101938

---

## 重新生成数据

```bash
cd data/mobility
python generate_data.py
```

---

*数据由 UrbanComp Lab (https://urbancomp.net) 生成，仅供学术研究和功能演示使用。*
