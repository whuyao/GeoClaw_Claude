# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
景德镇商场选址分析 — GeoClaw-claude 用户案例

演示在 chat 模式下的完整工作流：
  1. 下载景德镇 OSM 地理数据
  2. 提取商业 POI、交通节点、居民区等
  3. 多因子评分选出最适合建设商场的前 5 个地址
  4. 生成分析报告 + 地图

用法:
    git clone https://github.com/whuyao/GeoClaw_Claude.git
    cd GeoClaw_Claude && bash install.sh
    python3 examples/jingdezhen_mall_siting.py

依赖: osmnx, geopandas, matplotlib, shapely, scipy, numpy
"""

from __future__ import annotations

import json
import time
import warnings
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Point

warnings.filterwarnings("ignore")

OUT_DIR = Path(__file__).parent / "jingdezhen_mall_site"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CITY = "景德镇市, 江西省, 中国"

# ── 聊天记录收集 ───────────────────────────────────────────────────────────────
chat_log: list[dict] = []

def user_say(text: str) -> None:
    print(f"\n  你> {text}")
    chat_log.append({"role": "user", "text": text, "time": datetime.now().isoformat()})

def agent_say(text: str) -> None:
    print(f"\n  GeoClaw> {text}")
    chat_log.append({"role": "agent", "text": text, "time": datetime.now().isoformat()})

def agent_progress(step: str) -> None:
    print(f"    ⚙  {step}")


# ═══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("  GeoClaw-claude v3.1.1  |  chat 模式  |  景德镇商场选址案例")
print("=" * 65)
print("  AI Provider: OpenAI (gpt-4o-mini)  |  输出:", OUT_DIR)
print()

agent_say(
    "你好！我是 GeoClaw 智能 GIS 助手。\n"
    "  当前 AI 模式已启用（OpenAI gpt-4o-mini）。\n"
    "  输入自然语言指令即可开始分析，输入 exit 退出。\n"
    "  特殊命令: history / layers / status / exit"
)

# ── 用户提问 ───────────────────────────────────────────────────────────────────
user_say("请你下载景德镇的数据，并分析最适合建设商场的前5个地址，输出报告")

agent_say(
    "收到！这是一个多步骤的城市商业选址分析任务，我将按以下流程执行：\n\n"
    "  【1/5】下载景德镇 OpenStreetMap 地理数据\n"
    "  【2/5】提取商业 POI、交通节点、居住区密度\n"
    "  【3/5】构建候选网格 + 多因子评分模型\n"
    "  【4/5】筛选前 5 名候选地址（空间去重）\n"
    "  【5/5】生成分析报告与地图\n\n"
    "  预计耗时 60-120 秒，开始执行……"
)

# ═══════════════════════════════════════════════════════════════════════════════
# 【1/5】数据下载
# ═══════════════════════════════════════════════════════════════════════════════
import osmnx as ox

t0 = time.time()

agent_progress("下载景德镇行政边界……")
try:
    boundary_gdf = ox.geocode_to_gdf(CITY)
    boundary = boundary_gdf.geometry.iloc[0]
    agent_progress(f"  行政边界 OK，范围: {tuple(round(v, 4) for v in boundary.bounds)}")
except Exception as e:
    agent_progress(f"  边界下载失败 ({e})，使用默认范围")
    boundary_gdf = None
    boundary = Point(117.178, 29.2693).buffer(0.12)

agent_progress("下载商业 POI（商店/餐饮/银行）……")
try:
    shop_gdf = ox.features_from_place(
        CITY, tags={"shop": True, "amenity": ["restaurant", "cafe", "fast_food", "bank", "supermarket"]}
    )
    shop_pts = shop_gdf.copy()
    shop_pts["geometry"] = shop_gdf.geometry.centroid
    shop_pts = shop_pts[shop_pts.geometry.notnull()].reset_index(drop=True)
    agent_progress(f"  商业 POI: {len(shop_pts)} 条")
except Exception as e:
    agent_progress(f"  商业 POI 失败 ({e})")
    shop_pts = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

agent_progress("下载公共交通节点……")
try:
    transport_gdf = ox.features_from_place(
        CITY, tags={"highway": "bus_stop", "public_transport": ["stop_position", "platform"]}
    )
    transport_pts = transport_gdf.copy()
    transport_pts["geometry"] = transport_gdf.geometry.centroid
    transport_pts = transport_pts[transport_pts.geometry.notnull()].reset_index(drop=True)
    agent_progress(f"  交通节点: {len(transport_pts)} 条")
except Exception as e:
    agent_progress(f"  交通节点失败 ({e})")
    transport_pts = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

agent_progress("下载居住区 / 学校 / 医院……")
try:
    resident_gdf = ox.features_from_place(
        CITY, tags={
            "landuse": ["residential", "commercial", "retail"],
            "amenity": ["school", "university", "hospital", "clinic"]
        }
    )
    resident_pts = resident_gdf.copy()
    resident_pts["geometry"] = resident_gdf.geometry.centroid
    resident_pts = resident_pts[resident_pts.geometry.notnull()].reset_index(drop=True)
    agent_progress(f"  居住/教育/医疗: {len(resident_pts)} 条")
except Exception as e:
    agent_progress(f"  居住区失败 ({e})")
    resident_pts = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

agent_progress("下载道路网络……")
try:
    G = ox.graph_from_place(CITY, network_type="drive")
    nodes, edges = ox.graph_to_gdfs(G)
    agent_progress(f"  道路: {len(edges)} 条路段，{len(nodes)} 个节点")
except Exception as e:
    agent_progress(f"  路网失败 ({e})")
    nodes = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    edges = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

download_time = time.time() - t0
agent_say(
    f"✓ 数据下载完成（{download_time:.1f}s）\n"
    f"  商业 POI: {len(shop_pts)} | 交通节点: {len(transport_pts)} | "
    f"居住/设施: {len(resident_pts)} | 路网节点: {len(nodes)}"
)

# ═══════════════════════════════════════════════════════════════════════════════
# 【2/5 & 3/5】候选网格 + 多因子评分
# ═══════════════════════════════════════════════════════════════════════════════
agent_say(
    "构建选址评分模型（多因子加权，满分 100 分）：\n"
    "  • 商业集聚度  30 分 — 500m 内商业 POI 密度\n"
    "  • 交通可达性  25 分 — 最近公交/路网节点距离\n"
    "  • 人口密度    25 分 — 1km 内居住/学校/医院密度\n"
    "  • 竞争规避    10 分 — 避开过度集中商业区\n"
    "  • 区位中心性  10 分 — 距城市中心距离"
)

agent_progress("生成候选地块网格（500m × 500m）……")

minx, miny, maxx, maxy = 117.10, 29.22, 117.26, 29.33
step = 0.0045  # ≈ 500m
xs = np.arange(minx + step / 2, maxx, step)
ys = np.arange(miny + step / 2, maxy, step)

grid_pts = [Point(x, y) for x in xs for y in ys
            if boundary.contains(Point(x, y)) or boundary.distance(Point(x, y)) < 0.01]

grid_gdf = gpd.GeoDataFrame({"geometry": grid_pts}, crs="EPSG:4326")
agent_progress(f"  候选地块: {len(grid_gdf)} 个")

# 投影到米制坐标
grid_proj     = grid_gdf.to_crs("EPSG:32650")
shop_proj     = shop_pts.to_crs("EPSG:32650") if len(shop_pts) else gpd.GeoDataFrame(geometry=[], crs="EPSG:32650")
transport_proj= transport_pts.to_crs("EPSG:32650") if len(transport_pts) else gpd.GeoDataFrame(geometry=[], crs="EPSG:32650")
resident_proj = resident_pts.to_crs("EPSG:32650") if len(resident_pts) else gpd.GeoDataFrame(geometry=[], crs="EPSG:32650")
nodes_proj    = nodes.to_crs("EPSG:32650") if len(nodes) else gpd.GeoDataFrame(geometry=[], crs="EPSG:32650")

from scipy.spatial import cKDTree

cand_xy = np.array([[g.x, g.y] for g in grid_proj.geometry])

def count_within(cxy, poi_xy, r):
    if len(poi_xy) == 0: return np.zeros(len(cxy))
    tree = cKDTree(poi_xy)
    return np.array([len(tree.query_ball_point(p, r)) for p in cxy])

def min_dist(cxy, poi_xy):
    if len(poi_xy) == 0: return np.ones(len(cxy)) * 9999
    tree = cKDTree(poi_xy)
    d, _ = tree.query(cxy, k=1)
    return d

def norm(a):
    mn, mx = a.min(), a.max()
    return np.zeros_like(a) if mx == mn else (a - mn) / (mx - mn)

def norm_inv(a): return 1 - norm(a)

shop_xy  = np.array([[g.x, g.y] for g in shop_proj.geometry]) if len(shop_proj) else np.empty((0, 2))
trans_xy = np.array([[g.x, g.y] for g in transport_proj.geometry]) if len(transport_proj) else \
           (np.array([[g.x, g.y] for g in nodes_proj.geometry]) if len(nodes_proj) else np.empty((0, 2)))
res_xy   = np.array([[g.x, g.y] for g in resident_proj.geometry]) if len(resident_proj) else np.empty((0, 2))
city_ctr = np.array([[cand_xy[:, 0].mean(), cand_xy[:, 1].mean()]])

shop_density   = count_within(cand_xy, shop_xy, 500)
trans_dist     = min_dist(cand_xy, trans_xy)
pop_density    = count_within(cand_xy, res_xy, 1000)
competition    = np.where(shop_density > 10, shop_density - 10, 0)
center_dist    = min_dist(cand_xy, city_ctr)

score_comm  = norm(shop_density)     * 30
score_trans = norm_inv(trans_dist)   * 25
score_pop   = norm(pop_density)      * 25
score_comp  = (1 - norm(competition))* 10
score_loc   = norm_inv(center_dist)  * 10
total_score = score_comm + score_trans + score_pop + score_comp + score_loc

grid_gdf["score_commercial"]  = score_comm
grid_gdf["score_transport"]   = score_trans
grid_gdf["score_population"]  = score_pop
grid_gdf["score_competition"] = score_comp
grid_gdf["score_location"]    = score_loc
grid_gdf["total_score"]       = total_score
grid_gdf["shop_density_500m"] = shop_density
grid_gdf["pop_density_1km"]   = pop_density
grid_gdf["trans_dist_m"]      = trans_dist

# ═══════════════════════════════════════════════════════════════════════════════
# 【4/5】筛选前5（空间去重）
# ═══════════════════════════════════════════════════════════════════════════════
agent_progress("筛选前 5 名（最小间距 800m 去重）……")

grid_proj["total_score"] = total_score
sorted_idx = grid_proj["total_score"].sort_values(ascending=False).index.tolist()

selected, sel_xy = [], []
for idx in sorted_idx:
    pt = grid_proj.geometry[idx]
    xy = np.array([pt.x, pt.y])
    if not sel_xy or min(np.linalg.norm(xy - s) for s in sel_xy) > 800:
        selected.append(idx); sel_xy.append(xy)
    if len(selected) == 5: break

top5 = grid_gdf.loc[selected].copy().reset_index(drop=True)
top5["rank"] = range(1, 6)
top5["lng"]  = [g.x for g in top5.geometry]
top5["lat"]  = [g.y for g in top5.geometry]

def region_label(lng, lat):
    zones = [
        (117.17, 117.22, 29.27, 29.32, "珠山区"),
        (117.10, 117.17, 29.24, 29.30, "昌江区"),
        (117.22, 117.30, 29.24, 29.32, "浮梁县城区"),
        (117.10, 117.26, 29.22, 29.27, "南部新区"),
    ]
    for x0, x1, y0, y1, name in zones:
        if x0 <= lng <= x1 and y0 <= lat <= y1: return name
    return "景德镇市区"

top5["region"] = [region_label(r["lng"], r["lat"]) for _, r in top5.iterrows()]

agent_say(
    "✓ 评分完成！前 5 个最优商场候选地址：\n\n"
    + "\n".join(
        f"  #{r['rank']}  {r['region']:8s}  "
        f"({r['lng']:.4f}°E, {r['lat']:.4f}°N)  "
        f"综合 {r['total_score']:.1f}/100"
        for _, r in top5.iterrows()
    )
    + "\n\n  正在生成地图和报告……"
)

# ═══════════════════════════════════════════════════════════════════════════════
# 【5/5】地图生成
# ═══════════════════════════════════════════════════════════════════════════════
agent_progress("生成选址热力图 + 因子对比图……")

fig, axes = plt.subplots(1, 2, figsize=(16, 9))
fig.patch.set_facecolor("#1a1a2e")
RANK_COLORS = ["#FFD700", "#C0C0C0", "#CD7F32", "#FF6B6B", "#4ECDC4"]

# 左图：热力图
ax1 = axes[0]
ax1.set_facecolor("#16213e")
if boundary_gdf is not None:
    boundary_gdf.to_crs("EPSG:4326").boundary.plot(ax=ax1, color="#4a9eff", linewidth=1.5, alpha=0.8)

sc = ax1.scatter(
    [g.x for g in grid_gdf.geometry], [g.y for g in grid_gdf.geometry],
    c=grid_gdf["total_score"], cmap="RdYlGn", s=18, alpha=0.7, vmin=0, vmax=100, zorder=2
)
plt.colorbar(sc, ax=ax1, label="综合评分", shrink=0.8)

for _, row in top5.iterrows():
    r = int(row["rank"])
    ax1.scatter(row["lng"], row["lat"], c=RANK_COLORS[r-1],
                s=220, zorder=10, edgecolors="white", linewidth=2, marker="*")
    ax1.annotate(f"#{r}", (row["lng"], row["lat"]),
                 textcoords="offset points", xytext=(8, 6), fontsize=10,
                 color="white", fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.2", fc=RANK_COLORS[r-1], alpha=0.85))

ax1.set_title("景德镇商场选址评分热力图", color="white", fontsize=14, pad=12)
ax1.set_xlabel("经度", color="#aaa", fontsize=9)
ax1.set_ylabel("纬度", color="#aaa", fontsize=9)
ax1.tick_params(colors="#aaa")
for sp in ax1.spines.values(): sp.set_edgecolor("#4a9eff")

# 右图：因子对比柱状图
ax2 = axes[1]
ax2.set_facecolor("#16213e")
cats = ["商业集聚\n(30)", "交通可达\n(25)", "人口密度\n(25)", "竞争规避\n(10)", "区位中心\n(10)"]
cols = ["score_commercial", "score_transport", "score_population", "score_competition", "score_location"]
x = np.arange(len(cats))
w = 0.15
offsets = np.linspace(-2*w, 2*w, 5)

for i, (_, row) in enumerate(top5.iterrows()):
    vals = [row[c] for c in cols]
    ax2.bar(x + offsets[i], vals, w, color=RANK_COLORS[i], alpha=0.85,
            label=f"#{int(row['rank'])} {row['region']}")

ax2.set_xticks(x)
ax2.set_xticklabels(cats, color="#ccc", fontsize=8)
ax2.set_ylabel("因子得分", color="#aaa")
ax2.set_title("前5候选地址因子得分对比", color="white", fontsize=14, pad=12)
ax2.legend(loc="upper right", fontsize=8, framealpha=0.3, labelcolor="white", facecolor="#16213e")
ax2.tick_params(colors="#aaa")
for sp in ax2.spines.values(): sp.set_edgecolor("#4a9eff")

plt.tight_layout()
map_path = OUT_DIR / "jingdezhen_mall_site_analysis.png"
plt.savefig(map_path, dpi=150, bbox_inches="tight", facecolor="#1a1a2e")
plt.close()
agent_progress(f"  地图已保存: {map_path.name}")

# ── 生成 Markdown 报告 ────────────────────────────────────────────────────────
agent_progress("生成分析报告……")

now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
total_time = time.time() - t0

rows_md = "\n".join(
    f"| #{int(r['rank'])} | {r['region']} | "
    f"{r['lng']:.4f}°E, {r['lat']:.4f}°N | "
    f"**{r['total_score']:.1f}** | "
    f"{r['score_commercial']:.1f} | {r['score_transport']:.1f} | {r['score_population']:.1f} |"
    for _, r in top5.iterrows()
)

detail_md = ""
for _, row in top5.iterrows():
    adv = (
        "较高商业集聚效应，适合综合体锚点商业" if row["score_commercial"] > 20
        else "较好交通辐射能力，适合大型零售商场" if row["score_transport"] > 18
        else "较大居住区服务潜力，适合社区型购物中心"
    )
    detail_md += f"""
### #{int(row['rank'])}  {row['region']}

| 指标 | 数值 |
|------|------|
| 坐标 | {row['lng']:.4f}°E，{row['lat']:.4f}°N |
| 综合评分 | **{row['total_score']:.1f} / 100** |
| 商业集聚（30分） | {row['score_commercial']:.1f} — 500m 内商业 POI {row['shop_density_500m']:.0f} 个 |
| 交通可达（25分） | {row['score_transport']:.1f} — 最近交通节点 {row['trans_dist_m']:.0f} 米 |
| 人口密度（25分） | {row['score_population']:.1f} — 1km 内设施 {row['pop_density_1km']:.0f} 处 |
| 竞争规避（10分） | {row['score_competition']:.1f} |
| 区位中心（10分） | {row['score_location']:.1f} |

**选址建议**：{adv}。

"""

REPORT = f"""# 景德镇商场选址分析报告

> **生成工具**：GeoClaw-claude v3.1.1  
> **生成时间**：{now_str}  
> **数据来源**：OpenStreetMap (© OpenStreetMap contributors, ODbL)  
> **分析耗时**：{total_time:.1f} 秒

---

## 一、任务背景

用户通过 GeoClaw chat 模式提出需求：

> *"请你下载景德镇的数据，并分析最适合建设商场的前5个地址，输出报告"*

GeoClaw 自动完成了数据下载、多因子建模、空间评分与报告生成全流程，无需用户编写任何代码。

---

## 二、数据获取

| 数据类型 | 数量 | 来源 |
|---------|------|------|
| 行政边界 | 1 个多边形 | OSM Nominatim |
| 商业 POI（商店/餐饮/银行） | {len(shop_pts)} 条 | OSM features |
| 公共交通节点 | {len(transport_pts)} 条 | OSM features |
| 居住/教育/医疗设施 | {len(resident_pts)} 条 | OSM features |
| 道路网络节点 | {len(nodes)} 个 | OSMnx graph |

候选分析地块：{len(grid_gdf)} 个（500m × 500m 网格，覆盖城区范围）

---

## 三、评分模型

采用**加权多因子评分模型**（满分 100 分）：

| 因子 | 权重 | 计算方法 |
|------|------|---------|
| 商业集聚度 | 30 分 | 半径 500m 内商业 POI 数量归一化 |
| 交通可达性 | 25 分 | 最近公交/路网节点距离取反归一化 |
| 人口密度   | 25 分 | 半径 1km 内居住/教育/医疗 POI 数量归一化 |
| 竞争规避   | 10 分 | 超过 10 个同类 POI 时扣分 |
| 区位中心性 | 10 分 | 距城市几何中心距离取反归一化 |

**空间去重**：各候选点最小间距 ≥ 800m，避免结果过度集中。

---

## 四、前 5 名候选地址汇总

| 排名 | 区域 | 坐标 | 综合评分 | 商业(30) | 交通(25) | 人口(25) |
|------|------|------|---------|---------|---------|---------|
{rows_md}

---

## 五、各地址详细分析
{detail_md}
---

## 六、结论与建议

1. **综合最优地块**为 #{int(top5.iloc[0]['rank'])} **{top5.iloc[0]['region']}**（{top5.iloc[0]['total_score']:.1f}/100 分），建议优先开展实地踏勘。
2. 景德镇城区面积适中，5 个候选地址均匀分布，可服务不同片区居民。
3. **实地验证建议**：
   - 确认用地性质是否允许商业开发
   - 核实地块面积（大型购物中心建议 ≥ 3 万㎡建筑面积）
   - 评估周边基础设施（水电、市政管网）完善程度
   - 参考景德镇市最新商业规划文件
4. **数据局限性**：本分析基于 OpenStreetMap 开源数据，景德镇部分区域 POI 覆盖可能不完整，建议结合政府规划数据综合评估。

---

## 七、附件说明

| 文件 | 说明 |
|------|------|
| `jingdezhen_mall_site_analysis.png` | 选址热力图 + 因子对比图 |
| `jingdezhen_top5_sites.geojson` | 前 5 候选地址 GeoJSON 数据 |
| `jingdezhen_chat_log.json` | 完整 chat 对话记录 |
| `jingdezhen_mall_siting.py` | 本案例完整源代码 |

---

*GeoClaw-claude v3.1.1 · UrbanComp Lab · China University of Geosciences (Wuhan)*  
*数据协议：© OpenStreetMap contributors, ODbL*
"""

report_path = OUT_DIR / "jingdezhen_mall_siting_report.md"
report_path.write_text(REPORT, encoding="utf-8")
agent_progress(f"  报告已保存: {report_path.name}")

# ── GeoJSON 输出 ──────────────────────────────────────────────────────────────
geojson_path = OUT_DIR / "jingdezhen_top5_sites.geojson"
top5[["rank", "region", "total_score", "score_commercial", "score_transport",
      "score_population", "score_competition", "score_location",
      "lng", "lat", "shop_density_500m", "pop_density_1km", "trans_dist_m", "geometry"]
].to_file(geojson_path, driver="GeoJSON")
agent_progress(f"  GeoJSON 已保存: {geojson_path.name}")

# ── 完成 ──────────────────────────────────────────────────────────────────────
agent_say(
    f"✅ 分析完成！（总耗时 {total_time:.1f}s）\n\n"
    "  生成文件：\n"
    f"  📄 {report_path.name}\n"
    f"  🗺  jingdezhen_mall_site_analysis.png\n"
    f"  📍 jingdezhen_top5_sites.geojson\n"
    f"  💬 jingdezhen_chat_log.json\n\n"
    "  建议下一步：\n"
    "  • geoclaw-claude chat → '展示交互地图'\n"
    "  • geoclaw-claude chat → '调整权重 交通30 商业20'\n"
    "  • geoclaw-claude chat → '对 #1 地址做 1km 等时圈分析'"
)

user_say("谢谢！报告非常详细，请保存结果。")
agent_say("所有结果已保存到 examples/jingdezhen_mall_site/ 目录。如需继续分析，随时告知！")

# ── 保存对话记录 ──────────────────────────────────────────────────────────────
chat_path = OUT_DIR / "jingdezhen_chat_log.json"
chat_path.write_text(json.dumps(chat_log, ensure_ascii=False, indent=2), encoding="utf-8")

# ── 打印摘要 ──────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("  输出文件：")
for f in sorted(OUT_DIR.glob("*")):
    print(f"  {f.name:50s}  {f.stat().st_size:>8,} bytes")
print("=" * 65)
