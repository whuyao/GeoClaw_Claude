"""
examples/wuhan_mobility_demo.py
================================
武汉城市人类移动性分析完整 Demo
——基于 trackintel 的移动性数据层级生成与可视化

数据集：data/mobility/wuhan_gps_tracks.csv
  - 5 位武汉居民，10 天 GPS 轨迹
  - 涵盖汉口/武昌/汉阳三镇，多种出行方式
  - 共约 37,500 个 GPS 轨迹点

演示内容:
  Step 1  读入 GPS 数据，规范化为 trackintel 格式
  Step 2  生成停留点（staypoints）
  Step 3  生成出行段（triplegs）并预测出行方式
  Step 4  生成出行（trips）与重要地点（locations）
  Step 5  计算移动性指标（回转半径、跳跃距离、出行方式）
  Step 6  识别家/工作地
  Step 7  可视化：分层地图 + 热力图 + 指标仪表盘

算法来源：trackintel (https://github.com/mie-lab/trackintel)
  Martin, H. et al. (2023). Trackintel: An open-source Python library for
  human mobility analysis. Computers, Environment and Urban Systems, 101.

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

import warnings
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # 无界面模式
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from geoclaw_claude.analysis.mobility import (
    read_positionfixes,
    generate_full_hierarchy,
    predict_transport_mode,
    identify_home_work,
    radius_of_gyration,
    jump_lengths,
    modal_split,
    tracking_quality,
    mobility_summary,
    plot_mobility_layers,
    plot_modal_split,
    plot_activity_heatmap,
    plot_mobility_metrics,
)

# ── 输出目录 ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "mobility_demo"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_PATH = Path(__file__).parent.parent / "data" / "mobility" / "wuhan_gps_tracks.csv"

print("=" * 60)
print("  武汉城市移动性分析 Demo")
print("  基于 trackintel  ·  GeoClaw-claude v2.2.0")
print("  UrbanComp Lab (https://urbancomp.net)")
print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1  读入 GPS 数据
# ─────────────────────────────────────────────────────────────────────────────
print("\n[Step 1] 读入 GPS 轨迹数据...")
pfs = read_positionfixes(
    DATA_PATH,
    user_id_col="user_id",
    tracked_at_col="tracked_at",
    lon_col="longitude",
    lat_col="latitude",
)
print(f"  ✓ 读入 {len(pfs):,} 个 GPS 轨迹点，{pfs['user_id'].nunique()} 位用户")
print(f"    时间范围: {pfs['tracked_at'].min().date()} ~ {pfs['tracked_at'].max().date()}")
print(f"    坐标范围: 经度 [{pfs.geometry.x.min():.4f}, {pfs.geometry.x.max():.4f}]")
print(f"              纬度 [{pfs.geometry.y.min():.4f}, {pfs.geometry.y.max():.4f}]")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2~4  一键生成完整数据层级
# ─────────────────────────────────────────────────────────────────────────────
print("\n[Step 2-4] 生成完整移动性数据层级（trackintel）...")
print("  positionfixes → staypoints → triplegs → trips → locations")

hierarchy = generate_full_hierarchy(
    pfs,
    dist_threshold=80,       # 停留判定：80 米内
    time_threshold=5,        # 停留判定：至少 5 分钟
    gap_threshold=30,        # 数据缺口容忍：30 分钟
    location_epsilon=120,    # 地点聚类半径：120 米
    predict_mode=True,       # 自动预测出行方式
)

sp   = hierarchy["staypoints"]
tpls = hierarchy["triplegs"]
trips = hierarchy["trips"]
locs = hierarchy["locations"]

print(f"\n  ✓ 层级生成完成:")
print(f"    停留点  (staypoints):  {len(sp):>5} 个")
print(f"    出行段  (triplegs):    {len(tpls):>5} 个")
print(f"    出行    (trips):       {len(trips):>5} 个")
print(f"    重要地点(locations):   {len(locs):>5} 个")

if "mode" in tpls.columns:
    mode_dist = tpls["mode"].value_counts()
    print(f"\n  出行方式分布:")
    for mode, cnt in mode_dist.items():
        pct = cnt / len(tpls) * 100
        bar = "█" * int(pct / 3)
        print(f"    {mode:<8} {bar:<20} {cnt:>4} ({pct:.1f}%)")


# ─────────────────────────────────────────────────────────────────────────────
# Step 5  移动性指标计算
# ─────────────────────────────────────────────────────────────────────────────
print("\n[Step 5] 计算移动性指标...")

summary = mobility_summary(hierarchy)

print(f"  回转半径 (Radius of Gyration):")
if "radius_of_gyration_m" in summary:
    rog = summary["radius_of_gyration_m"]
    print(f"    均值: {rog['mean']/1000:.2f} km")
    print(f"    中位数: {rog['median']/1000:.2f} km")
    print(f"    最大: {rog['max']/1000:.2f} km")

print(f"\n  跳跃距离 (Jump Length):")
if "jump_length_m" in summary:
    jl = summary["jump_length_m"]
    print(f"    均值: {jl['mean']/1000:.2f} km")
    print(f"    中位数: {jl['median']/1000:.2f} km")
    print(f"    P90: {jl['p90']/1000:.2f} km")

if "tracking_quality_mean" in summary:
    print(f"\n  轨迹覆盖率: {summary['tracking_quality_mean']:.1%}")

# 逐用户回转半径
try:
    rog_per_user = radius_of_gyration(sp)
    print(f"\n  逐用户回转半径:")
    for _, row in rog_per_user.iterrows():
        uid = int(row["user_id"])
        names = ["金融从业者", "互联网工程师", "商贸从业者", "高校研究员", "医疗从业者"]
        name = names[uid] if uid < len(names) else f"u{uid}"
        rog_col = 'radius_gyration' if 'radius_gyration' in rog_per_user.columns else 'radius_of_gyration'
        print(f"    u{uid} {name}: {row[rog_col]/1000:.2f} km")
except Exception as e:
    print(f"  (逐用户 RoG 跳过: {e})")


# ─────────────────────────────────────────────────────────────────────────────
# Step 6  识别家/工作地
# ─────────────────────────────────────────────────────────────────────────────
print("\n[Step 6] 识别家和工作地（OSNA 方法）...")
try:
    locs_labeled = identify_home_work(sp, locs, method="osna")
    hierarchy["locations"] = locs_labeled
    if "purpose" in locs_labeled.columns:
        purpose_cnt = locs_labeled["purpose"].value_counts(dropna=False)
        print(f"  ✓ 地点语义标注完成:")
        for p, cnt in purpose_cnt.items():
            p_str = str(p) if p is not None else "unknown"
            print(f"    {p_str}: {cnt} 个地点")
except Exception as e:
    print(f"  (家/工作地识别跳过: {e})")


# ─────────────────────────────────────────────────────────────────────────────
# Step 7  可视化
# ─────────────────────────────────────────────────────────────────────────────
print("\n[Step 7] 生成可视化图表...")

# 7.1 分层移动性地图
print("  生成分层移动性地图...")
fig1 = plot_mobility_layers(
    hierarchy,
    show_positionfixes=False,
    show_staypoints=True,
    show_triplegs=True,
    show_locations=True,
    title="武汉城市移动性数据层级地图（trackintel）",
    figsize=(14, 12),
    save_path=OUTPUT_DIR / "01_mobility_layers_map.png",
)
plt.close(fig1)
print(f"  ✓ 01_mobility_layers_map.png")

# 7.2 出行方式构成图
if "mode" in tpls.columns:
    print("  生成出行方式构成图...")
    fig2 = plot_modal_split(
        tpls,
        metric="count",
        title="武汉居民出行方式构成",
        save_path=OUTPUT_DIR / "02_modal_split.png",
    )
    plt.close(fig2)
    print(f"  ✓ 02_modal_split.png")

# 7.3 活动时间热力图
print("  生成活动时间热力图...")
fig3 = plot_activity_heatmap(
    sp,
    title="武汉居民活动时间热力图（全部用户）",
    save_path=OUTPUT_DIR / "03_activity_heatmap_all.png",
)
plt.close(fig3)
print(f"  ✓ 03_activity_heatmap_all.png")

# 单用户热力图（用户 0：金融从业者）
fig3b = plot_activity_heatmap(
    sp, user_id=0,
    title="用户0（金融从业者）活动时间热力图",
    save_path=OUTPUT_DIR / "03b_activity_heatmap_u0.png",
)
plt.close(fig3b)
print(f"  ✓ 03b_activity_heatmap_u0.png")

# 7.4 移动性指标仪表盘
print("  生成移动性指标仪表盘...")
fig4 = plot_mobility_metrics(
    summary,
    title="武汉城市居民移动性指标综合报告",
    save_path=OUTPUT_DIR / "04_mobility_metrics_dashboard.png",
)
plt.close(fig4)
print(f"  ✓ 04_mobility_metrics_dashboard.png")

# 7.5 单用户轨迹地图（用户 1：光谷工程师）
print("  生成单用户轨迹地图（光谷工程师）...")
fig5 = plot_mobility_layers(
    hierarchy,
    user_id=1,
    show_positionfixes=False,
    show_staypoints=True,
    show_triplegs=True,
    show_locations=True,
    title="用户1（互联网工程师·光谷）个人轨迹地图",
    figsize=(12, 10),
    save_path=OUTPUT_DIR / "05_user1_trajectory.png",
)
plt.close(fig5)
print(f"  ✓ 05_user1_trajectory.png")


# ─────────────────────────────────────────────────────────────────────────────
# 完成
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  ✅ Demo 完成！共生成 5 张图表")
print(f"  输出目录: {OUTPUT_DIR}")
print("=" * 60)
print()
print("  算法来源: trackintel (mie-lab/trackintel)")
print("  论文: Martin et al. (2023). Computers, Environment and Urban Systems.")
print("  框架: GeoClaw-claude v2.2.0 · UrbanComp Lab")
print()
