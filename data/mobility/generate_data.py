"""
generate_wuhan_mobility_data.py
================================
生成武汉城市 GPS 轨迹模拟数据，用于 GeoClaw-claude 移动性分析 Demo。

数据特征:
  - 5 位用户（u0-u4）
  - 每位用户 10 天数据（2024-01-15 ~ 2024-01-24）
  - 典型城市居民作息：家→工作地→午餐→工作地→健身/购物→家
  - 武汉真实地理位置（家/工作地/地铁站/商圈 参照真实坐标）
  - 符合 trackintel positionfixes 格式

输出:
  data/mobility/wuhan_gps_tracks.csv        所有用户原始轨迹点
  data/mobility/users_meta.csv              用户元数据
  data/mobility/README.md                   数据说明

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

np.random.seed(2025)

# ── 武汉真实地标坐标 ──────────────────────────────────────────────────────────
WUHAN_LOCATIONS = {
    # 家（住宅区）
    "home_0":  (114.2814, 30.5862),   # 汉口 → 后湖
    "home_1":  (114.3668, 30.5145),   # 武昌 → 洪山广场
    "home_2":  (114.1755, 30.6012),   # 汉阳 → 知音湖
    "home_3":  (114.3921, 30.5423),   # 武昌 → 光谷
    "home_4":  (114.2623, 30.6234),   # 汉口 → 新华路

    # 工作地
    "work_0":  (114.3562, 30.5413),   # 武昌 → 中南路（金融区）
    "work_1":  (114.4223, 30.5089),   # 光谷 → 软件园
    "work_2":  (114.3012, 30.5756),   # 汉口 → 江汉路（商务区）
    "work_3":  (114.3456, 30.5234),   # 武昌 → 徐东（互联网公司）
    "work_4":  (114.3123, 30.5901),   # 汉口 → 汉正街（贸易区）

    # 公共场所
    "wuhan_station":   (114.3054, 30.5962),   # 武汉站
    "optics_valley":   (114.4109, 30.5057),   # 光谷广场
    "zhongnan_road":   (114.3467, 30.5378),   # 中南路
    "jianghan_road":   (114.2934, 30.5823),   # 江汉路步行街
    "east_lake":       (114.4067, 30.5475),   # 东湖
    "wuhan_univ":      (114.3654, 30.5312),   # 武汉大学
    "hankou_station":  (114.2821, 30.6098),   # 汉口站
    "gym_0":           (114.3412, 30.5521),   # 健身房 A
    "mall_0":          (114.2978, 30.5867),   # 购物中心 A（武广）
    "mall_1":          (114.4089, 30.5112),   # 购物中心 B（光谷步行街）
    "restaurant_0":    (114.3234, 30.5678),   # 午餐 A
    "restaurant_1":    (114.3892, 30.5201),   # 午餐 B
    "hospital_0":      (114.3167, 30.5445),   # 协和医院
}


def interpolate_path(start, end, n_points=20, noise=0.0008):
    """在两点之间生成带噪声的轨迹路径。"""
    lons = np.linspace(start[0], end[0], n_points) + np.random.normal(0, noise, n_points)
    lats = np.linspace(start[1], end[1], n_points) + np.random.normal(0, noise, n_points)
    # 起止点无噪声（精确停留）
    lons[0], lats[0] = start
    lons[-1], lats[-1] = end
    return list(zip(lons, lats))


def add_stay(rows, user_id, location, t_start, duration_min, interval_sec=60):
    """在某地点生成停留轨迹点（小范围随机漂移）。"""
    n = max(1, int(duration_min * 60 / interval_sec))
    for i in range(n):
        lon = location[0] + np.random.normal(0, 0.0003)
        lat = location[1] + np.random.normal(0, 0.0003)
        rows.append({
            "user_id":   user_id,
            "tracked_at": t_start + pd.Timedelta(seconds=i * interval_sec),
            "longitude": round(lon, 6),
            "latitude":  round(lat, 6),
            "elevation": round(np.random.uniform(20, 80), 1),
            "accuracy":  round(np.random.uniform(3, 15), 1),
        })
    return t_start + pd.Timedelta(minutes=duration_min)


def add_trip(rows, user_id, origin, destination, t_start, duration_min, n_points=25):
    """在两点之间生成出行轨迹点。"""
    path = interpolate_path(origin, destination, n_points=n_points)
    interval = (duration_min * 60) / max(1, len(path) - 1)
    for i, (lon, lat) in enumerate(path):
        rows.append({
            "user_id":   user_id,
            "tracked_at": t_start + pd.Timedelta(seconds=i * interval),
            "longitude": round(lon, 6),
            "latitude":  round(lat, 6),
            "elevation": round(np.random.uniform(5, 50), 1),
            "accuracy":  round(np.random.uniform(5, 20), 1),
        })
    return t_start + pd.Timedelta(minutes=duration_min)


# ── 用户日程配置 ──────────────────────────────────────────────────────────────
USER_SCHEDULES = {
    0: {  # 金融从业者 - 中南路上班
        "home": WUHAN_LOCATIONS["home_0"],
        "work": WUHAN_LOCATIONS["work_0"],
        "lunch": WUHAN_LOCATIONS["restaurant_0"],
        "evening": WUHAN_LOCATIONS["mall_0"],
        "commute_mode": "metro",  # 地铁
        "work_start": 9, "work_end": 18,
    },
    1: {  # 互联网工程师 - 光谷软件园
        "home": WUHAN_LOCATIONS["home_1"],
        "work": WUHAN_LOCATIONS["work_1"],
        "lunch": WUHAN_LOCATIONS["mall_1"],
        "evening": WUHAN_LOCATIONS["gym_0"],
        "commute_mode": "bus",
        "work_start": 10, "work_end": 20,  # 弹性上班
    },
    2: {  # 商贸从业者 - 汉口
        "home": WUHAN_LOCATIONS["home_2"],
        "work": WUHAN_LOCATIONS["work_2"],
        "lunch": WUHAN_LOCATIONS["restaurant_1"],
        "evening": WUHAN_LOCATIONS["jianghan_road"],
        "commute_mode": "walk",
        "work_start": 8, "work_end": 17,
    },
    3: {  # 高校研究员 - 武大
        "home": WUHAN_LOCATIONS["home_3"],
        "work": WUHAN_LOCATIONS["wuhan_univ"],
        "lunch": WUHAN_LOCATIONS["restaurant_0"],
        "evening": WUHAN_LOCATIONS["east_lake"],
        "commute_mode": "bike",
        "work_start": 9, "work_end": 17,
    },
    4: {  # 医疗从业者 - 协和医院
        "home": WUHAN_LOCATIONS["home_4"],
        "work": WUHAN_LOCATIONS["hospital_0"],
        "lunch": WUHAN_LOCATIONS["restaurant_1"],
        "evening": WUHAN_LOCATIONS["mall_0"],
        "commute_mode": "metro",
        "work_start": 8, "work_end": 16,
    },
}

# ── 生成主数据 ────────────────────────────────────────────────────────────────
rows = []
START_DATE = pd.Timestamp("2024-01-15", tz="UTC")

for uid, sched in USER_SCHEDULES.items():
    home = sched["home"]
    work = sched["work"]
    lunch_loc = sched["lunch"]
    evening_loc = sched["evening"]
    ws = sched["work_start"]
    we = sched["work_end"]

    for day in range(10):
        date = START_DATE + pd.Timedelta(days=day)
        is_weekend = date.dayofweek >= 5

        if is_weekend:
            # 周末：晚起→外出逛街→回家
            t = date + pd.Timedelta(hours=9, minutes=np.random.randint(0, 60))
            t = add_stay(rows, uid, home, t, 120)  # 在家早晨
            t = add_trip(rows, uid, home, evening_loc, t, 30)
            t = add_stay(rows, uid, evening_loc, t, 180)  # 逛街/休闲
            # 部分用户顺道去东湖公园
            if uid == 3 and day % 2 == 0:
                t = add_trip(rows, uid, evening_loc, WUHAN_LOCATIONS["east_lake"], t, 20)
                t = add_stay(rows, uid, WUHAN_LOCATIONS["east_lake"], t, 90)
                t = add_trip(rows, uid, WUHAN_LOCATIONS["east_lake"], home, t, 25)
            else:
                t = add_trip(rows, uid, evening_loc, home, t, 30)
            t = add_stay(rows, uid, home, t, 120)

        else:
            # 工作日：家→上班→午饭→上班→傍晚→回家
            t = date + pd.Timedelta(hours=ws - 1, minutes=np.random.randint(0, 30))
            t = add_stay(rows, uid, home, t, 30)  # 早晨准备

            # 通勤上班
            commute_dur = {"metro": 35, "bus": 50, "walk": 20, "bike": 25}[sched["commute_mode"]]
            t = add_trip(rows, uid, home, work, t, commute_dur + np.random.randint(-5, 10))
            t = add_stay(rows, uid, work, t, (lunch_start := 12 - ws) * 60 - 30)  # 上午工作

            # 午饭
            t = add_trip(rows, uid, work, lunch_loc, t, 15)
            t = add_stay(rows, uid, lunch_loc, t, 60)
            t = add_trip(rows, uid, lunch_loc, work, t, 15)
            t = add_stay(rows, uid, work, t, (we - 12 - 1) * 60)  # 下午工作

            # 下班通勤
            t = add_trip(rows, uid, work, evening_loc, t, commute_dur // 2 + np.random.randint(0, 15))
            t = add_stay(rows, uid, evening_loc, t, 60 + np.random.randint(0, 30))
            t = add_trip(rows, uid, evening_loc, home, t, commute_dur // 2)
            t = add_stay(rows, uid, home, t, 90)

    print(f"  用户 u{uid} ({sched['commute_mode']}): {sum(1 for r in rows if r['user_id']==uid)} 个轨迹点")

# ── 保存数据 ──────────────────────────────────────────────────────────────────
df = pd.DataFrame(rows)
df = df.sort_values(["user_id", "tracked_at"]).reset_index(drop=True)
df.index.name = "id"

output_dir = Path(__file__).parent
(output_dir).mkdir(parents=True, exist_ok=True)

csv_path = output_dir / "wuhan_gps_tracks.csv"
df.to_csv(csv_path)
print(f"\n✓ 轨迹数据保存: {csv_path}")
print(f"  总轨迹点: {len(df):,}")
print(f"  用户数:   {df['user_id'].nunique()}")
print(f"  时间范围: {df['tracked_at'].min()} ~ {df['tracked_at'].max()}")
print(f"  列:       {list(df.columns)}")

# 用户元数据
meta = pd.DataFrame([
    {"user_id": 0, "name": "金融从业者", "home_area": "汉口后湖", "work_area": "武昌中南路",
     "commute": "地铁", "days": 10},
    {"user_id": 1, "name": "互联网工程师", "home_area": "武昌洪山广场", "work_area": "光谷软件园",
     "commute": "公交", "days": 10},
    {"user_id": 2, "name": "商贸从业者", "home_area": "汉阳知音湖", "work_area": "汉口江汉路",
     "commute": "步行", "days": 10},
    {"user_id": 3, "name": "高校研究员", "home_area": "武昌光谷", "work_area": "武汉大学",
     "commute": "骑行", "days": 10},
    {"user_id": 4, "name": "医疗从业者", "home_area": "汉口新华路", "work_area": "协和医院",
     "commute": "地铁", "days": 10},
])
meta.to_csv(output_dir / "users_meta.csv", index=False)
print(f"✓ 用户元数据保存: users_meta.csv")
