"""
geoclaw_claude/io/osm.py
=================
OpenStreetMap 数据下载模块（基于 Overpass API）

提供从 OSM 下载各类城市地理数据的功能:
  - download_pois()     — 下载兴趣点 (POI: 医院/学校/公园等)
  - download_roads()    — 下载路网（按道路等级过滤）
  - download_boundary() — 下载行政边界（通过 Nominatim 地名解析）
  - load_wuhan_data()   — 加载预下载的武汉数据集（离线使用）

Overpass API 端点: https://overpass-api.de/api/interpreter
Nominatim 端点:    https://nominatim.openstreetmap.org

────────────────────────────────────────────────────────
TODO (高优先级):
  - [ ] 支持 osmnx 下载完整路网 (带拓扑结构) 用于网络分析
  - [ ] 添加离线缓存机制: 相同 query 直接读取本地 cache/
  - [ ] download_roads: 返回 LineString 图层 (当前已实现，需增加拓扑修复)

TODO (中优先级):
  - [ ] 添加 download_buildings() — 建筑物轮廓下载
  - [ ] 添加 download_landuse()   — 土地利用分类下载
  - [ ] 添加 download_waterways() — 水系（线状河流）下载
  - [ ] 添加 retry_on_rate_limit: Overpass 限流时自动等待重试

TODO (低优先级):
  - [ ] 支持 Overpass Turbo QL 查询字符串直接传入
  - [ ] 支持 GeoFabrik PBF 文件批量下载解析 (适合大区域)
  - [ ] 适配 OpenStreetMap China 镜像减少境内访问延迟
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import time
from typing import Dict, List, Optional

import geopandas as gpd
import requests
from shapely.geometry import LineString, Point

from geoclaw_claude.core.layer import GeoLayer


# ── 常量 ─────────────────────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# POI 类型 → Overpass 标签映射
# 使用方式: download_pois(bbox, poi_type="hospital")
# 扩展时在此字典添加新条目即可
POI_PRESETS: Dict[str, str] = {
    "hospital":    '["amenity"="hospital"]',
    "school":      '["amenity"~"school|university|college"]',
    "university":  '["amenity"="university"]',
    "park":        '["leisure"="park"]',
    "metro":       '["public_transport"="stop_position"]["subway"="yes"]',
    "bus_stop":    '["highway"="bus_stop"]',
    "restaurant":  '["amenity"="restaurant"]',
    "hotel":       '["tourism"="hotel"]',
    "supermarket": '["shop"="supermarket"]',
    "pharmacy":    '["amenity"="pharmacy"]',
    "bank":        '["amenity"="bank"]',
    "police":      '["amenity"="police"]',
    "fire_station":'["amenity"="fire_station"]',
    # TODO: 添加更多 POI 类型
}

# 道路等级 → highway 标签正则
ROAD_LEVELS: Dict[str, str] = {
    "all":     "motorway|trunk|primary|secondary|tertiary",
    "major":   "motorway|trunk|primary",
    "highway": "motorway|trunk",
    "primary": "primary",
    "secondary": "secondary",
    "local":   "tertiary|residential|unclassified",
}

# TODO: 提取为配置文件 config/overpass.yaml
_DEFAULT_TIMEOUT    = 60   # Overpass query timeout (seconds)
_DEFAULT_MAX_RESULTS = 500  # 单次查询最大返回要素数
_RETRY_WAIT         = 5    # 重试等待秒数


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _safe_query(query: str, retries: int = 2) -> List[dict]:
    """
    执行 Overpass API 查询，带重试机制。

    Args:
        query  : Overpass QL 查询字符串
        retries: 失败时重试次数

    Returns:
        elements 列表，失败时返回空列表

    TODO:
        - [ ] 区分 HTTP 429 (限流) 和 504 (超时) 分别处理
        - [ ] 记录请求耗时到 log
    """
    for attempt in range(retries):
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=_DEFAULT_TIMEOUT + 20,
            )
            if resp.status_code == 200 and resp.text.strip():
                return resp.json().get("elements", [])
            elif resp.status_code == 429:
                print(f"  [Overpass] 请求频率限制，等待 {_RETRY_WAIT * 2}s 后重试...")
                time.sleep(_RETRY_WAIT * 2)
        except requests.Timeout:
            print(f"  [Overpass] 查询超时 (尝试 {attempt + 1}/{retries})")
            time.sleep(_RETRY_WAIT)
        except Exception as e:
            print(f"  [Overpass] 错误: {e} (尝试 {attempt + 1}/{retries})")
            time.sleep(_RETRY_WAIT)
    return []


def _elements_to_points(
    elements: List[dict],
    tag_fields: Optional[List[str]] = None,
) -> Optional[gpd.GeoDataFrame]:
    """
    将 Overpass node/way（out center）要素列表转换为点 GeoDataFrame。

    Args:
        elements  : Overpass API 返回的 elements 列表
        tag_fields: 需要提取的 OSM 标签字段列表（默认提取常用字段）

    Returns:
        点 GeoDataFrame，若无有效要素返回 None

    TODO:
        - [ ] 支持提取 relation 类型要素（当前仅支持 node/way）
    """
    default_fields = [
        "name", "name:en", "name:zh", "amenity", "leisure", "railway",
        "public_transport", "highway", "tourism", "shop", "operator",
        "operator:type", "beds", "capacity", "website", "phone",
        "opening_hours", "wheelchair", "healthcare", "healthcare:speciality",
    ]
    fields = tag_fields or default_fields

    records = []
    for e in elements:
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat and lon:
            r = {
                "osm_id":   e["id"],
                "osm_type": e["type"],
                "geometry": Point(lon, lat),
            }
            tags = e.get("tags", {})
            for f in fields:
                r[f] = tags.get(f, "")
            records.append(r)

    if not records:
        return None
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")


def _elements_to_lines(elements: List[dict]) -> Optional[gpd.GeoDataFrame]:
    """
    将 Overpass way（out geom）要素列表转换为 LineString GeoDataFrame。

    TODO:
        - [ ] 处理自相交的折线（调用 shapely simplify）
        - [ ] 支持 multilinestring 合并
    """
    roads = []
    for e in elements:
        coords = [(n["lon"], n["lat"]) for n in e.get("geometry", []) if "lon" in n]
        if len(coords) >= 2:
            tags = e.get("tags", {})
            roads.append({
                "osm_id":   e["id"],
                "name":     tags.get("name", ""),
                "highway":  tags.get("highway", ""),
                "maxspeed": tags.get("maxspeed", ""),
                "lanes":    tags.get("lanes", ""),
                "oneway":   tags.get("oneway", "no"),
                "geometry": LineString(coords),
            })
    if not roads:
        return None
    return gpd.GeoDataFrame(roads, geometry="geometry", crs="EPSG:4326")


# ── 公共 API ──────────────────────────────────────────────────────────────────

def download_pois(
    bbox: tuple,
    poi_type: str,
    name: Optional[str] = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
    tag_fields: Optional[List[str]] = None,
) -> Optional[GeoLayer]:
    """
    从 OpenStreetMap 下载兴趣点（POI）。

    Args:
        bbox       : (west, south, east, north) WGS84 坐标
        poi_type   : POI 类型，支持 POI_PRESETS 中的预设键，
                     或直接传入 Overpass 标签字符串（如 '["amenity"="cinema"]'）
        name       : 图层名称（默认使用 poi_type）
        max_results: 最大返回要素数（受 Overpass 限制）
        tag_fields : 需要提取的 OSM tag 字段（默认提取 20 个常用字段）

    Returns:
        点要素 GeoLayer，无数据时返回 None

    使用示例:
        bbox = (113.7, 29.97, 115.08, 31.36)  # 武汉市
        hospitals = download_pois(bbox, poi_type="hospital")
        parks     = download_pois(bbox, poi_type="park", max_results=200)

    TODO:
        - [ ] 添加 within_place 参数（按行政区名称查询，而非 bbox）
        - [ ] 添加 progress_bar 显示下载进度
    """
    west, south, east, north = bbox
    bbox_str   = f"({south},{west},{north},{east})"
    tag        = POI_PRESETS.get(poi_type, poi_type)
    layer_name = name or poi_type.replace("_", " ").title()

    query = (
        f'[out:json][timeout:{_DEFAULT_TIMEOUT}];'
        f'(node{tag}{bbox_str};way{tag}{bbox_str};);'
        f'out center {max_results};'
    )

    print(f"  下载 {layer_name}（{poi_type}）...")
    elements = _safe_query(query)

    if not elements:
        print(f"  ⚠ 未找到 {layer_name} 数据")
        return None

    gdf = _elements_to_points(elements, tag_fields=tag_fields)
    if gdf is None:
        return None

    layer = GeoLayer(gdf, name=layer_name, source=f"OSM/Overpass/{poi_type}")
    print(f"  ✓ {layer_name}: {len(layer)} 个要素")
    return layer


def download_roads(
    bbox: tuple,
    level: str = "major",
    name: Optional[str] = None,
    max_results: int = 600,
) -> Optional[GeoLayer]:
    """
    从 OpenStreetMap 下载路网数据。

    Args:
        bbox       : (west, south, east, north) WGS84 坐标
        level      : 道路等级，支持 ROAD_LEVELS 中的键:
                     'all' | 'major' | 'highway' | 'primary' | 'secondary' | 'local'
        name       : 图层名称
        max_results: 最大返回路段数

    Returns:
        LineString 要素 GeoLayer，无数据时返回 None

    TODO:
        - [ ] 下载完整拓扑路网（支持 osmnx.graph_from_bbox）
        - [ ] 支持下载人行道/自行车道 (bicycle|footway)
        - [ ] 过滤隧道/高架（tunnel=yes/bridge=yes 可选是否包含）
    """
    west, south, east, north = bbox
    bbox_str      = f"({south},{west},{north},{east})"
    highway_re    = ROAD_LEVELS.get(level, level)
    layer_name    = name or f"路网 ({level})"

    query = (
        f'[out:json][timeout:{_DEFAULT_TIMEOUT}];'
        f'way["highway"~"^({highway_re})$"]{bbox_str};'
        f'out geom {max_results};'
    )

    print(f"  下载 {layer_name}...")
    resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=_DEFAULT_TIMEOUT + 20)

    if resp.status_code != 200 or not resp.text.strip():
        print(f"  ⚠ 路网请求失败 (HTTP {resp.status_code})")
        return None

    elements = resp.json().get("elements", [])
    gdf = _elements_to_lines(elements)
    if gdf is None:
        return None

    layer = GeoLayer(gdf, name=layer_name, source="OSM/Overpass/roads")
    print(f"  ✓ {layer_name}: {len(layer)} 路段")
    return layer


def download_boundary(
    place_name: str,
    name: Optional[str] = None,
) -> Optional[GeoLayer]:
    """
    通过 Nominatim 地名解析下载行政边界多边形。

    Args:
        place_name: 地名字符串（如 "Wuhan, Hubei, China"）
        name      : 图层名称（默认取地名第一段）

    Returns:
        Polygon/MultiPolygon GeoLayer，失败时返回 None

    TODO:
        - [ ] 支持 admin_level 过滤（市级/区级/街道级）
        - [ ] 支持语言偏好设置（name:zh vs name:en）
    """
    try:
        import osmnx as ox
    except ImportError:
        raise ImportError("download_boundary 需要安装 osmnx: pip install osmnx")

    layer_name = name or place_name.split(",")[0].strip()
    print(f"  下载行政边界: '{place_name}'...")
    try:
        gdf = ox.geocode_to_gdf(place_name)
        layer = GeoLayer(gdf, name=layer_name, source=f"Nominatim/{place_name}")
        print(f"  ✓ 边界: {layer.geometry_type}, 范围={tuple(round(v,3) for v in layer.bounds)}")
        return layer
    except Exception as e:
        print(f"  ✗ 下载失败: {e}")
        return None


def load_wuhan_data(
    data_dir: str = "data/wuhan",
) -> Dict[str, GeoLayer]:
    """
    加载预下载的武汉 OSM 数据集（离线模式）。

    适用于无网络环境或测试场景，数据已保存在 data/wuhan/ 目录。

    Args:
        data_dir: 武汉数据目录路径

    Returns:
        dict: {图层名: GeoLayer}，缺失文件会打印警告并跳过

    预置数据集:
        boundary       — 武汉市行政边界 (MultiPolygon)
        hospitals      — 医院 200 个 (Point)
        universities   — 高校 62 所 (Point)
        parks          — 公园 200 个 (Point)
        metro_stations — 地铁站 624 个 (Point)
        roads_main     — 主干道 600 段 (LineString)
        water          — 水体 300 个 (Point 质心)

    TODO:
        - [ ] 支持指定下载日期版本（数据时效管理）
        - [ ] 自动检查文件完整性（MD5 校验）
        - [ ] 若数据缺失，提供 download=True 参数自动下载
    """
    import os

    file_map = {
        "boundary":       "boundary.geojson",
        "hospitals":      "hospitals.geojson",
        "universities":   "universities.geojson",
        "parks":          "parks.geojson",
        "metro_stations": "metro_stations.geojson",
        "roads_main":     "roads_main.geojson",
        "water":          "water.geojson",
    }

    layers: Dict[str, GeoLayer] = {}
    for layer_name, filename in file_map.items():
        path = os.path.join(data_dir, filename)
        if os.path.exists(path):
            gdf = gpd.read_file(path)
            display_name = layer_name.replace("_", " ").title()
            layers[layer_name] = GeoLayer(gdf, name=display_name, source=f"OSM/{filename}")
        else:
            print(f"  ⚠ 文件缺失: {path}")

    print(f"  加载完成: {len(layers)}/{len(file_map)} 个图层")
    return layers
