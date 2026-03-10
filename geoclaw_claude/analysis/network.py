"""
geoclaw_claude/analysis/network.py
====================================
路网分析模块 — 基于 osmnx + networkx 实现。

主要功能:
  - build_network()     从地名/bbox/GeoLayer 下载并构建路网图
  - shortest_path()     Dijkstra 最短路径（支持距离/时间权重）
  - isochrone()         N 分钟等时圈多边形
  - network_stats()     路网密度、连通性等统计指标
  - service_areas()     批量设施服务区分析
  - nearest_node()      最近路网节点查找

使用示例:
    from geoclaw_claude.analysis.network import build_network, shortest_path, isochrone

    G    = build_network("武汉市汉口", network_type="drive")
    path = shortest_path(G, origin=(114.30, 30.60), dest=(114.35, 30.58))
    iso  = isochrone(G, center=(114.30, 30.60), minutes=[5, 10, 15])

────────────────────────────────────────────────────────
TODO:
  - [ ] 多目标最短路径 (一对多、多对多矩阵)
  - [ ] 基于实时路况的动态路网权重
  - [ ] 公交/地铁多模式换乘路径规划
  - [ ] 路网脆弱性分析（关键边删除实验）
  - [ ] alpha shape 替代凸包生成更精确等时圈
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point

from geoclaw_claude.core.layer import GeoLayer


# ── 路网构建 ──────────────────────────────────────────────────────────────────

def build_network(
    source: Union[str, "GeoLayer", tuple],
    network_type: str = "drive",
    retain_all: bool = False,
    custom_filter: Optional[str] = None,
) -> Any:
    """
    构建路网图 (networkx.MultiDiGraph)。

    Args:
        source       : 地名字符串 / bbox元组 (west,south,east,north) / GeoLayer
        network_type : "drive" | "walk" | "bike" | "all"
        retain_all   : 是否保留所有不连通子图
        custom_filter: 自定义 OSM highway 过滤器

    Returns:
        osmnx Graph，节点含 x/y 坐标，边含 length/travel_time/speed_kph

    TODO:
        - [ ] 支持从本地 OSM PBF 文件构建
        - [ ] 支持从本地道路 Shapefile 构建（不依赖网络）
    """
    try:
        import osmnx as ox
    except ImportError:
        raise ImportError("需要安装 osmnx: pip install osmnx")

    ox.settings.use_cache = True
    ox.settings.log_console = False
    ox.settings.timeout = 15  # 最多等待15秒（测试环境），生产建议60秒
    ox.settings.max_query_area_size = 50_000_000_000  # 放宽面积限制

    # === Hard timeout wrapper ===
    import concurrent.futures as _cf, functools as _ft

    def _do_download():
        nonlocal G
        if isinstance(source, str):
            print(f"  ↓ 下载路网: {source} ({network_type})")
            return ox.graph_from_place(source, network_type=network_type,
                                       retain_all=retain_all, custom_filter=custom_filter)
        elif isinstance(source, tuple) and len(source) == 4:
            west, south, east, north = source
            print(f"  ↓ 下载路网: bbox [{west:.3f},{south:.3f},{east:.3f},{north:.3f}] ({network_type})")
            return ox.graph_from_bbox(bbox=(north, south, east, west),
                                      network_type=network_type, retain_all=retain_all,
                                      custom_filter=custom_filter)
        elif isinstance(source, GeoLayer):
            bounds = source.data.total_bounds
            west2, south2, east2, north2 = bounds
            pad = 0.01
            print(f"  ↓ 下载路网: 图层范围 ({network_type})")
            return ox.graph_from_bbox(bbox=(north2+pad, south2-pad, east2+pad, west2-pad),
                                      network_type=network_type, retain_all=retain_all)
        else:
            raise ValueError("source 须为: 地名字符串 / (west,south,east,north)元组 / GeoLayer")

    _timeout_sec = 25
    import signal as _sig

    def _timeout_handler(signum, frame):
        raise RuntimeError(
            f"路网下载超时（>{_timeout_sec}秒），Overpass API 响应过慢或网络不通。\n"
            "建议：① 检查网络连接；② 稍后重试；③ 如需离线分析，"
            "可先下载路网文件（graph_from_bbox 后 save_graphml）再使用 graph_file 参数。"
        )

    # signal 只在主线程中有效
    _is_main_thread = (_sig.getsignal(_sig.SIGALRM) is not None
                       if hasattr(_sig, 'SIGALRM') else False)
    try:
        if hasattr(_sig, 'SIGALRM'):
            _old_handler = _sig.signal(_sig.SIGALRM, _timeout_handler)
            _sig.alarm(_timeout_sec)
        G = _do_download()
        if hasattr(_sig, 'SIGALRM'):
            _sig.alarm(0)
            _sig.signal(_sig.SIGALRM, _old_handler)
    except RuntimeError:
        if hasattr(_sig, 'SIGALRM'):
            _sig.alarm(0)
        raise

    if False:  # 以下原始分支已被上面的 _do_download 替代，保留注释供参考
        pass
    if isinstance(source, str):
        G = ox.graph_from_place(
            source,
            network_type=network_type,
            retain_all=retain_all,
            custom_filter=custom_filter,
        )

    elif isinstance(source, tuple) and len(source) == 4:
        west, south, east, north = source
        print(f"  ↓ 下载路网: bbox [{west:.3f},{south:.3f},{east:.3f},{north:.3f}] ({network_type})")
        G = ox.graph_from_bbox(
            bbox=(north, south, east, west),
            network_type=network_type,
            retain_all=retain_all,
            custom_filter=custom_filter,
        )

    elif isinstance(source, GeoLayer):
        bounds = source.data.total_bounds
        west, south, east, north = bounds
        pad = 0.01
        print(f"  ↓ 下载路网: 图层范围 ({network_type})")
        G = ox.graph_from_bbox(
            bbox=(north + pad, south - pad, east + pad, west - pad),
            network_type=network_type,
            retain_all=retain_all,
        )
    else:
        raise ValueError("source 须为: 地名字符串 / (west,south,east,north)元组 / GeoLayer")

    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    total_km = sum(d.get("length", 0) for _, _, d in G.edges(data=True)) / 1000
    print(f"  ✓ 路网: {n_nodes} 节点, {n_edges} 边, {total_km:.1f} km")
    return G


def build_network_from_layer(roads: "GeoLayer", weight_col: str = "length") -> Any:
    """
    从本地道路 GeoLayer 构建 networkx 图（离线使用）。

    Args:
        roads      : 道路线图层 (LineString/MultiLineString)
        weight_col : 权重字段名，默认用几何长度

    Returns:
        networkx.Graph

    TODO:
        - [ ] 处理道路方向属性（oneway 字段）
        - [ ] 自动捕捉近似相交节点（容差合并）
    """
    import networkx as nx

    G = nx.Graph()
    for _, row in roads.data.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        parts = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
        for part in parts:
            coords = list(part.coords)
            start, end = coords[0], coords[-1]
            G.add_node(start, x=start[0], y=start[1])
            G.add_node(end,   x=end[0],   y=end[1])
            w = float(row.get(weight_col, part.length)) if weight_col in roads.data.columns else part.length
            G.add_edge(start, end, weight=w, geometry=part)

    print(f"  ✓ 本地路网: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")
    return G


# ── 最近节点 ──────────────────────────────────────────────────────────────────

def nearest_node(G: Any, lon: float, lat: float) -> Tuple[Any, float]:
    """
    查找路网中距给定坐标最近的节点。

    Returns:
        (node_id, snap_distance_meters)
    """
    try:
        import osmnx as ox
        node_id = ox.nearest_nodes(G, X=lon, Y=lat)
        nd = G.nodes[node_id]
        dist = Point(lon, lat).distance(Point(nd["x"], nd["y"])) * 111320
        return node_id, dist
    except Exception:
        best_id, best_dist = None, float("inf")
        for nid, data in G.nodes(data=True):
            d = (data.get("x", 0) - lon) ** 2 + (data.get("y", 0) - lat) ** 2
            if d < best_dist:
                best_dist, best_id = d, nid
        return best_id, best_dist ** 0.5 * 111320


# ── 最短路径 ──────────────────────────────────────────────────────────────────

def shortest_path(
    G: Any,
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    weight: str = "travel_time",
) -> Optional["GeoLayer"]:
    """
    计算两点间最短路径。

    Args:
        G      : osmnx Graph
        origin : 起点 (lon, lat)
        dest   : 终点 (lon, lat)
        weight : "travel_time"（秒）或 "length"（米）

    Returns:
        路径 GeoLayer（单条 LineString），含距离/时间/速度属性
        若无路径则返回 None

    TODO:
        - [ ] 途经点支持 (waypoints 列表)
        - [ ] k 条最短路径候选
        - [ ] 路径详情（逐段转弯说明）
    """
    import networkx as nx

    orig_node, _ = nearest_node(G, *origin)
    dest_node, _ = nearest_node(G, *dest)

    if orig_node == dest_node:
        print("  ⚠ 起终点映射到同一节点")
        return None

    try:
        node_path = nx.shortest_path(G, orig_node, dest_node, weight=weight)
    except nx.NetworkXNoPath:
        print(f"  ✗ 无可用路径: {origin} → {dest}")
        return None
    except nx.NodeNotFound as e:
        print(f"  ✗ 节点不存在: {e}")
        return None

    geoms, total_len, total_time = [], 0.0, 0.0
    for u, v in zip(node_path[:-1], node_path[1:]):
        edge_data = G.get_edge_data(u, v)
        # MultiDiGraph 可能有多条平行边，取权重最小的
        if isinstance(edge_data, dict) and 0 in edge_data:
            best = min(edge_data.values(), key=lambda d: d.get(weight, float("inf")))
        else:
            best = edge_data or {}

        geom = best.get("geometry")
        if geom is None:
            un, vn = G.nodes[u], G.nodes[v]
            geom = LineString([(un["x"], un["y"]), (vn["x"], vn["y"])])

        geoms.append(geom)
        total_len  += best.get("length", 0)
        total_time += best.get("travel_time", 0)

    all_coords = [c for g in geoms for c in g.coords]
    path_line  = LineString(all_coords)

    gdf = gpd.GeoDataFrame({
        "origin_lon":      [origin[0]], "origin_lat":     [origin[1]],
        "dest_lon":        [dest[0]],   "dest_lat":       [dest[1]],
        "length_m":        [round(total_len, 1)],
        "travel_time_s":   [round(total_time, 1)],
        "travel_time_min": [round(total_time / 60, 2)],
        "speed_kph":       [round(total_len / total_time * 3.6, 1) if total_time > 0 else 0],
        "node_count":      [len(node_path)],
        "geometry":        [path_line],
    }, crs="EPSG:4326")

    print(f"  ✓ 路径: {total_len/1000:.2f} km, {total_time/60:.1f} min, {len(node_path)} 节点")
    return GeoLayer(gdf, name="shortest_path", source="network_analysis")


# ── 等时圈 ────────────────────────────────────────────────────────────────────

def isochrone(
    G: Any,
    center: Tuple[float, float],
    minutes: List[float] = [5, 10, 15],
    weight: str = "travel_time",
) -> "GeoLayer":
    """
    计算从中心点出发 N 分钟可达的等时圈多边形。

    Args:
        G       : osmnx Graph
        center  : 中心点 (lon, lat)
        minutes : 时间档位（分钟），如 [5, 10, 15]
        weight  : "travel_time" 或 "length"

    Returns:
        多边形 GeoLayer，每行一个时间档位，含 area_km2 属性

    TODO:
        - [ ] alpha shape 生成更贴合路网形态的等时圈
        - [ ] 多中心点批量并行计算
        - [ ] 支持步行/骑行速度参数
    """
    import networkx as nx

    center_node, snap_dist = nearest_node(G, *center)
    if snap_dist > 500:
        print(f"  ⚠ 中心点距最近节点 {snap_dist:.0f}m，结果可能偏移")

    records = []
    for t_min in sorted(minutes):
        cutoff = t_min * 60 if weight == "travel_time" else t_min * 60 * (50 / 3.6)

        reachable = nx.single_source_dijkstra_path_length(
            G, center_node, cutoff=cutoff, weight=weight
        )
        node_ids = list(reachable.keys())

        if len(node_ids) < 3:
            print(f"  ⚠ {t_min}min 可达节点不足 ({len(node_ids)}个)，跳过")
            continue

        pts = [
            Point(G.nodes[n]["x"], G.nodes[n]["y"])
            for n in node_ids
            if "x" in G.nodes[n]
        ]
        if len(pts) < 3:
            continue

        gs   = gpd.GeoSeries(pts, crs=4326)
        poly = gs.unary_union.convex_hull

        # 投影到 UTM 做平滑缓冲
        try:
            gs_utm   = gs.to_crs(epsg=32650)
            poly_utm = gs_utm.unary_union.convex_hull.buffer(300).buffer(-150)
            poly     = gpd.GeoSeries([poly_utm], crs=32650).to_crs(4326).iloc[0]
        except Exception:
            pass

        area_km2 = round(
            gpd.GeoSeries([poly], crs=4326).to_crs(32650).area.iloc[0] / 1e6, 3
        )
        records.append({
            "minutes":    t_min,
            "cutoff_sec": cutoff if weight == "travel_time" else None,
            "node_count": len(node_ids),
            "area_km2":   area_km2,
            "geometry":   poly,
        })
        print(f"  ✓ {t_min}min 等时圈: {len(node_ids)} 节点, {area_km2} km²")

    if not records:
        raise ValueError("所有时间档位均无有效可达区域")

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.sort_values("minutes", ascending=False).reset_index(drop=True)
    return GeoLayer(gdf, name="isochrone", source="network_analysis")


# ── 路网统计 ──────────────────────────────────────────────────────────────────

def network_stats(G: Any, area_km2: Optional[float] = None) -> Dict[str, Any]:
    """
    计算路网统计指标（密度、连通性、迂回度等）。

    Args:
        G        : osmnx Graph
        area_km2 : 研究区面积（km²），用于计算密度指标

    Returns:
        字典，含: node_count / edge_count / avg_degree /
                  total_length_km / avg_speed_kph /
                  road_density_km_per_km2 (需area_km2) /
                  intersection_density_per_km2 (需area_km2) /
                  circuity_avg

    TODO:
        - [ ] 连通性指数: beta/gamma/alpha index
        - [ ] 道路等级分布（highway 类型占比）
    """
    total_len = sum(d.get("length", 0) for _, _, d in G.edges(data=True))
    speeds = [d.get("speed_kph", 0) for _, _, d in G.edges(data=True) if d.get("speed_kph", 0) > 0]
    degrees = [d for _, d in G.degree()]

    result: Dict[str, Any] = {
        "node_count":      G.number_of_nodes(),
        "edge_count":      G.number_of_edges(),
        "avg_degree":      round(np.mean(degrees), 2) if degrees else 0,
        "total_length_km": round(total_len / 1000, 2),
        "avg_speed_kph":   round(np.mean(speeds), 1) if speeds else 0,
    }

    if area_km2 and area_km2 > 0:
        result["road_density_km_per_km2"]       = round(result["total_length_km"] / area_km2, 2)
        result["intersection_density_per_km2"]  = round(result["node_count"] / area_km2, 2)

    try:
        import osmnx as ox
        stats = ox.basic_stats(G)
        if "circuity_avg" in stats:
            result["circuity_avg"] = round(stats["circuity_avg"], 3)
    except Exception:
        pass

    print(f"  路网: {result['node_count']} 节点 | "
          f"{result['total_length_km']} km | 平均度 {result['avg_degree']}")
    return result


# ── 服务区批量分析 ────────────────────────────────────────────────────────────

def service_areas(
    G: Any,
    facilities: "GeoLayer",
    minutes: float = 10.0,
    weight: str = "travel_time",
) -> "GeoLayer":
    """
    批量计算多个设施点的服务区（等时圈）。

    Args:
        G          : osmnx Graph
        facilities : 设施点 GeoLayer（Point 类型）
        minutes    : 服务时间（分钟）
        weight     : "travel_time" 或 "length"

    Returns:
        服务区多边形 GeoLayer，含 facility / area_km2 / node_count 字段

    TODO:
        - [ ] 支持多时间档位同时计算
        - [ ] 计算服务覆盖率（与人口格网叠加）
    """
    import networkx as nx

    if not all(facilities.data.geometry.geom_type == "Point"):
        raise ValueError("facilities 图层须为 Point 类型")

    name_col = next((c for c in ["name", "名称", "NAME", "facility"] if c in facilities.data.columns), None)
    cutoff   = minutes * 60 if weight == "travel_time" else minutes * 60 * (50 / 3.6)
    records  = []

    for i, row in facilities.data.iterrows():
        pt    = row.geometry
        fname = (row[name_col] if name_col else f"facility_{i}")
        try:
            cnode, _ = nearest_node(G, pt.x, pt.y)
            reachable = nx.single_source_dijkstra_path_length(G, cnode, cutoff=cutoff, weight=weight)
            nids = list(reachable.keys())
            if len(nids) < 3:
                continue
            pts = [Point(G.nodes[n]["x"], G.nodes[n]["y"]) for n in nids if "x" in G.nodes[n]]
            poly = gpd.GeoSeries(pts, crs=4326).unary_union.convex_hull
            area = gpd.GeoSeries([poly], crs=4326).to_crs(32650).area.iloc[0] / 1e6
            records.append({"facility": fname, "minutes": minutes,
                             "node_count": len(nids), "area_km2": round(area, 3), "geometry": poly})
        except Exception as e:
            print(f"  ⚠ {fname}: {e}")

    if not records:
        raise ValueError("未能生成任何服务区")

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    print(f"  ✓ 服务区: {len(gdf)}/{len(facilities)} 个设施, {minutes}min")
    return GeoLayer(gdf, name=f"service_area_{minutes}min", source="network_analysis")
