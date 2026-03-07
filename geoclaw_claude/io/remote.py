"""
geoclaw_claude/io/remote.py
============================
远程地理数据下载模块。

支持:
  - HTTP/HTTPS 直接下载 GeoJSON / Shapefile / GPKG
  - WFS (Web Feature Service) 标准接口
  - 天地图 API（需 key）
  - 带缓存机制（可离线使用已缓存数据）

使用示例:
    from geoclaw_claude.io.remote import download_file, fetch_wfs, fetch_url_layer

    # 直接下载文件
    path = download_file("https://example.com/data.geojson")

    # 加载远程 GeoJSON 为 GeoLayer
    layer = fetch_url_layer("https://example.com/hospitals.geojson")

    # WFS 接口
    layer = fetch_wfs("https://geoserver.example.com/wfs", layer="hospitals", bbox=bbox)

────────────────────────────────────────────────────────
TODO:
  - [ ] 支持 WMS/WMTS 栅格瓦片下载
  - [ ] 支持 ArcGIS REST API (FeatureServer)
  - [ ] 支持国内常见开放数据平台 (DataV/高德/百度)
  - [ ] 断点续传 (大文件)
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlencode, urlparse

import requests

from geoclaw_claude.config import Config
from geoclaw_claude.core.layer import GeoLayer


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _get_session(cfg: Optional[Config] = None) -> requests.Session:
    """创建带代理和超时设置的 requests Session。"""
    cfg = cfg or Config.load()
    session = requests.Session()
    session.headers.update({"User-Agent": "geoclaw-claude/0.2 (https://github.com)"})
    if cfg.proxy:
        session.proxies = {"http": cfg.proxy, "https": cfg.proxy}
    return session


def _cache_path(url: str, cfg: Config) -> Path:
    """根据 URL 生成缓存文件路径。"""
    h = hashlib.md5(url.encode()).hexdigest()[:16]
    ext = Path(urlparse(url).path).suffix or ".bin"
    return Path(cfg.cache_dir) / f"{h}{ext}"


def _cache_valid(path: Path, ttl_hours: int) -> bool:
    """检查缓存文件是否在有效期内。"""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_hours * 3600


# ── 公开 API ──────────────────────────────────────────────────────────────────

def download_file(
    url: str,
    dest: Optional[str] = None,
    force: bool = False,
    cfg: Optional[Config] = None,
) -> str:
    """
    从 URL 下载文件到本地。

    Args:
        url  : 下载地址
        dest : 保存路径（默认保存到配置的 data_dir）
        force: 强制重新下载（忽略缓存）
        cfg  : 配置对象（默认自动加载）

    Returns:
        本地文件路径字符串

    TODO:
        - [ ] 进度条显示 (tqdm)
        - [ ] 断点续传 Range header
    """
    cfg = cfg or Config.load()
    cfg.ensure_dirs()

    # 确定保存路径
    if dest:
        out = Path(dest)
    else:
        filename = Path(urlparse(url).path).name or "download.bin"
        out = Path(cfg.data_dir) / filename

    # 缓存检查
    cache = _cache_path(url, cfg)
    if cfg.enable_cache and not force and _cache_valid(cache, cfg.cache_ttl_hours):
        print(f"  ✓ 使用缓存: {cache}")
        if str(out) != str(cache):
            import shutil
            shutil.copy2(cache, out)
        return str(out)

    print(f"  ↓ 下载: {url}")
    session = _get_session(cfg)
    resp = session.get(url, timeout=cfg.request_timeout, stream=True)
    resp.raise_for_status()

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    # 写入缓存
    if cfg.enable_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(out, cache)

    size_kb = out.stat().st_size / 1024
    print(f"  ✓ 完成: {out} ({size_kb:.1f} KB)")
    return str(out)


def fetch_url_layer(
    url: str,
    name: Optional[str] = None,
    force: bool = False,
    cfg: Optional[Config] = None,
) -> GeoLayer:
    """
    从 URL 加载地理数据为 GeoLayer。

    支持格式: GeoJSON / Shapefile (zip) / GPKG / CSV

    Args:
        url  : 数据 URL
        name : 图层名称（默认从 URL 推断）
        force: 强制重新下载

    Returns:
        GeoLayer

    TODO:
        - [ ] 支持 ZIP 内含多文件 Shapefile 自动解压
        - [ ] 支持 GeoJSON FeatureCollection 分页合并
    """
    cfg = cfg or Config.load()
    path = download_file(url, force=force, cfg=cfg)
    layer_name = name or Path(urlparse(url).path).stem

    from geoclaw_claude.io.vector import load_vector
    return load_vector(path, name=layer_name)


def fetch_wfs(
    endpoint: str,
    layer_name: str,
    bbox: Optional[tuple] = None,
    max_features: int = 1000,
    version: str = "2.0.0",
    output_format: str = "application/json",
    extra_params: Optional[Dict[str, str]] = None,
    cfg: Optional[Config] = None,
) -> Optional[GeoLayer]:
    """
    从 WFS (Web Feature Service) 接口获取要素数据。

    Args:
        endpoint     : WFS 服务 URL (如 https://geoserver.example.com/wfs)
        layer_name   : 图层名称 (TypeName)
        bbox         : 空间过滤 (west, south, east, north)，可选
        max_features : 最大返回要素数
        version      : WFS 版本
        output_format: 输出格式
        extra_params : 附加请求参数

    Returns:
        GeoLayer 或 None

    TODO:
        - [ ] 支持 CQL_FILTER 属性过滤
        - [ ] 支持分页获取超大数据集
        - [ ] 支持 WFS 1.0.0 / 1.1.0 兼容
    """
    cfg = cfg or Config.load()

    params: Dict[str, Any] = {
        "service":      "WFS",
        "version":      version,
        "request":      "GetFeature",
        "typeName":     layer_name,
        "outputFormat": output_format,
        "count" if version.startswith("2") else "maxFeatures": max_features,
    }

    if bbox:
        west, south, east, north = bbox
        params["bbox"] = f"{south},{west},{north},{east}"

    if extra_params:
        params.update(extra_params)

    url = f"{endpoint}?{urlencode(params)}"
    print(f"  WFS 请求: {layer_name}")

    # 缓存检查
    cache = _cache_path(url, cfg)
    if cfg.enable_cache and _cache_valid(cache, cfg.cache_ttl_hours):
        print(f"  ✓ 使用缓存")
        import geopandas as gpd
        gdf = gpd.read_file(str(cache))
        return GeoLayer(gdf, name=layer_name, source=f"WFS/{endpoint}")

    session = _get_session(cfg)
    try:
        resp = session.get(url, timeout=cfg.request_timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ✗ WFS 请求失败: {e}")
        return None

    # 解析响应
    import geopandas as gpd
    import io
    try:
        if "json" in resp.headers.get("Content-Type", ""):
            gdf = gpd.read_file(io.StringIO(resp.text))
        else:
            gdf = gpd.read_file(io.BytesIO(resp.content))
    except Exception as e:
        print(f"  ✗ 解析失败: {e}")
        return None

    if gdf is None or len(gdf) == 0:
        print(f"  ⚠ WFS 返回空数据")
        return None

    # 写入缓存
    if cfg.enable_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(str(cache), driver="GeoJSON")

    layer = GeoLayer(gdf, name=layer_name, source=f"WFS/{endpoint}")
    print(f"  ✓ {layer_name}: {len(layer)} 个要素")
    return layer


def fetch_tianditu_poi(
    keyword: str,
    bbox: tuple,
    api_key: str,
    poi_type: str = "",
    max_results: int = 100,
    cfg: Optional[Config] = None,
) -> Optional[GeoLayer]:
    """
    从天地图 API 搜索 POI 数据。

    Args:
        keyword    : 搜索关键词 (如 "医院")
        bbox       : 搜索范围 (west, south, east, north)
        api_key    : 天地图 API Key
        poi_type   : POI 类型代码（可选，参考天地图文档）
        max_results: 最大返回数量

    Returns:
        点要素 GeoLayer 或 None

    TODO:
        - [ ] 支持分页获取 >100 条结果
        - [ ] 支持行政区代码过滤
    """
    cfg = cfg or Config.load()

    base_url = "https://api.tianditu.gov.cn/v2/search"
    post_data = {
        "postStr": json.dumps({
            "keyWord":    keyword,
            "mapBound":   f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "queryType":  "1",
            "start":      "0",
            "count":      str(max_results),
            "show":       "2",
        }),
        "type": "query",
        "tk":   api_key,
    }

    session = _get_session(cfg)
    try:
        resp = session.post(base_url, data=post_data, timeout=cfg.request_timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ✗ 天地图请求失败: {e}")
        return None

    pois = data.get("pois", [])
    if not pois:
        print(f"  ⚠ 未找到 POI: {keyword}")
        return None

    import geopandas as gpd
    from shapely.geometry import Point

    records = []
    for p in pois:
        try:
            lon = float(p.get("lonlat", "0,0").split(",")[0])
            lat = float(p.get("lonlat", "0,0").split(",")[1])
            records.append({
                "name":     p.get("name", ""),
                "address":  p.get("address", ""),
                "phone":    p.get("phone", ""),
                "category": p.get("poi_type_name", ""),
                "geometry": Point(lon, lat),
            })
        except Exception:
            continue

    if not records:
        return None

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    layer = GeoLayer(gdf, name=keyword, source="tianditu")
    print(f"  ✓ 天地图 {keyword}: {len(layer)} 个 POI")
    return layer
