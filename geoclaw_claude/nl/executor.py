"""
geoclaw_claude/nl/executor.py
================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

自然语言执行器 (NLExecutor)

将 NLProcessor 解析出的 ParsedIntent 转换为实际的 GIS 函数调用并执行。

功能:
  - 将 ParsedIntent 映射到具体的 geoclaw_claude 函数
  - 管理图层上下文（会话内命名图层字典）
  - 自动记录到 Memory 系统（操作日志 + 结果缓存）
  - 支持多步流水线（pipeline）自动顺序执行
  - 返回统一的 ExecutionResult，包含结果、耗时、状态

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from geoclaw_claude.nl.processor import ParsedIntent


# ── 执行结果 ──────────────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """单次操作执行结果。"""
    success:     bool
    action:      str
    result:      Any              = None   # 返回值（GeoLayer / dict / str / ...）
    message:     str              = ""     # 友好描述
    error:       Optional[str]   = None   # 错误信息
    duration:    float           = 0.0    # 耗时（秒）
    result_key:  Optional[str]   = None   # 存入 Memory 的键名

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"ExecutionResult({status} {self.action}: {self.message or self.error or ''})"

    def summary(self) -> str:
        if self.success:
            return f"✓ {self.action}: {self.message}"
        return f"✗ {self.action} 失败: {self.error}"


# ── NLExecutor 主类 ───────────────────────────────────────────────────────────

class NLExecutor:
    """
    自然语言执行器：将解析后的意图转为 GIS 操作并执行。

    Usage::

        from geoclaw_claude.nl import NLExecutor

        exec = NLExecutor()

        # 执行单条意图
        result = exec.execute_intent(intent)

        # 获取当前图层上下文
        layer = exec.get_layer("hospitals")

        # 查看执行历史
        history = exec.history
    """

    def __init__(
        self,
        memory_session: Optional[str] = None,
        verbose: bool = True,
        output_dir: Optional[str] = None,
    ):
        """
        Args:
            memory_session : 绑定的 Memory 会话 ID（None 则自动创建）
            verbose        : 打印执行过程
            output_dir     : 覆盖配置文件中的输出目录；None 则使用 config.output_dir
        """
        self.verbose  = verbose
        self._layers: Dict[str, Any] = {}          # 图层上下文（name → GeoLayer）
        self._history: List[ExecutionResult] = []   # 执行历史
        self._last_result: Any = None               # 上一步结果

        # 输出目录：参数 > 环境变量 > 配置文件 > 默认 ~/geoclaw_output
        import os as _os
        from geoclaw_claude.config import Config as _Cfg
        _cfg = _Cfg.load()
        self._output_dir: Optional[str] = (
            output_dir
            or _os.environ.get("GEOCLAW_OUTPUT_DIR")
            or _cfg.output_dir
            or str(_os.path.expanduser("~/geoclaw_output"))
        )

        # 始终初始化 SecurityGuard，确保所有输出都在 output_dir 下
        self._guard = None
        try:
            from geoclaw_claude.security import SecurityGuard
            import pathlib
            pathlib.Path(self._output_dir).mkdir(parents=True, exist_ok=True)
            self._guard = SecurityGuard(
                output_dir=self._output_dir,
                protected_dirs=[_cfg.data_dir],
            )
        except Exception:
            pass

        # Memory 集成
        self._mem = None
        try:
            from geoclaw_claude.memory import get_memory
            self._mem = get_memory()
            sid = memory_session or f"nl_{time.strftime('%H%M%S')}"
            self._mem.start_session(sid)
        except Exception:
            pass

    def _get_safe_output_path(self, filename: str, subdir: str = "") -> str:
        """获取安全输出路径（优先使用本实例 guard，否则使用全局 guard）。"""
        if self._guard is not None:
            return str(self._guard.safe_output_path(filename, subdir=subdir))
        from geoclaw_claude.security import get_guard
        return str(get_guard().safe_output_path(filename, subdir=subdir))

    # ── 图层管理 ──────────────────────────────────────────────────────────────

    def add_layer(self, name: str, layer: Any) -> None:
        self._layers[name] = layer
        if self._mem:
            self._mem.remember(f"layer_{name}", layer, category="result",
                               tags=["layer", name])

    def get_layer(self, name: str) -> Any:
        # 先查名称完整匹配
        if name in self._layers:
            return self._layers[name]
        # 模糊匹配（前缀）
        for k, v in self._layers.items():
            if k.startswith(name) or name.startswith(k):
                return v
        # 从 Memory 恢复
        if self._mem:
            layer = self._mem.recall_short(f"layer_{name}")
            if layer is not None:
                return layer
        return None

    def list_layers(self) -> List[str]:
        return list(self._layers.keys())

    @property
    def history(self) -> List[ExecutionResult]:
        return self._history

    @property
    def last_result(self) -> Any:
        return self._last_result

    # ── 主执行入口 ────────────────────────────────────────────────────────────

    def execute_intent(self, intent: ParsedIntent) -> ExecutionResult:
        """
        执行一个 ParsedIntent，返回 ExecutionResult。

        自动处理 pipeline 多步执行。
        """
        if intent.action == "pipeline":
            return self._execute_pipeline(intent)

        t0 = time.time()
        try:
            result = self._dispatch(intent)
            dur = time.time() - t0

            # 存入 Memory
            rkey = None
            if result is not None and self._mem:
                rkey = f"result_{intent.action}_{int(t0)}"
                self._mem.remember(rkey, result, category="result")
                self._mem.log_op(intent.action, intent.explanation,
                                 result_key=rkey, duration=dur, success=True)

            self._last_result = result
            er = ExecutionResult(
                success=True,
                action=intent.action,
                result=result,
                message=self._build_message(intent, result),
                duration=dur,
                result_key=rkey,
            )
        except Exception as e:
            dur = time.time() - t0
            err_msg = str(e)
            if self.verbose:
                traceback.print_exc()
            if self._mem:
                self._mem.log_op(intent.action, intent.explanation,
                                 duration=dur, success=False, error=err_msg)
            er = ExecutionResult(
                success=False,
                action=intent.action,
                error=err_msg,
                duration=dur,
            )

        self._history.append(er)
        if self.verbose:
            print(f"  {er.summary()}  [{dur:.2f}s]")
        return er

    def _execute_pipeline(self, pipeline: ParsedIntent) -> ExecutionResult:
        """按顺序执行多步流水线。"""
        results = []
        last_ok = True
        for step in pipeline.steps:
            r = self.execute_intent(step)
            results.append(r)
            if not r.success:
                last_ok = False
                break   # 遇到失败停止

        ok  = sum(1 for r in results if r.success)
        msg = f"流水线完成 {ok}/{len(pipeline.steps)} 步"
        er  = ExecutionResult(
            success=last_ok,
            action="pipeline",
            result=[r.result for r in results],
            message=msg,
            duration=sum(r.duration for r in results),
        )
        self._history.append(er)
        if self.verbose:
            print(f"  ✓ {msg}")
        return er

    # ── 操作分发 ──────────────────────────────────────────────────────────────

    def _dispatch(self, intent: ParsedIntent) -> Any:
        """根据 action 分发到对应函数。"""
        a = intent.action
        p = intent.params
        t = intent.targets

        # ── 数据加载/保存 ───────────────────────────────────────────────────
        if a == "load":
            return self._do_load(p, t)

        if a == "save":
            return self._do_save(p, t)

        # ── 空间分析 ────────────────────────────────────────────────────────
        if a == "buffer":
            return self._do_buffer(p, t)

        if a == "clip":
            return self._do_clip(p, t)

        if a == "intersect":
            return self._do_intersect(p, t)

        if a == "union":
            return self._do_union(p, t)

        if a == "nearest_neighbor":
            return self._do_nearest_neighbor(p, t)

        if a == "spatial_join":
            return self._do_spatial_join(p, t)

        if a == "kde":
            return self._do_kde(p, t)

        if a == "zonal_stats":
            return self._do_zonal_stats(p, t)

        if a == "calculate_area":
            return self._do_calculate_area(p, t)

        # ── 路网分析 ────────────────────────────────────────────────────────
        if a == "isochrone":
            return self._do_isochrone(p, t)

        if a == "shortest_path":
            return self._do_shortest_path(p, t)

        if a == "network_build":
            return self._do_network_build(p, t)

        # ── 坐标转换 ────────────────────────────────────────────────────────
        if a == "coord_transform":
            return self._do_coord_transform(p, t)

        # ── 制图 ────────────────────────────────────────────────────────────
        if a in ("render", "render_interactive"):
            return self._do_render(p, t, interactive=(a == "render_interactive"))

        # ── OSM 下载 ────────────────────────────────────────────────────────
        if a == "download_osm":
            return self._do_download_osm(p, t)

        # ── 系统命令 ────────────────────────────────────────────────────────
        # ── 移动性分析 ────────────────────────────────────────────────────────
        if a == "mobility_load":
            return self._do_mobility_load(p, t)
        if a == "mobility_staypoints":
            return self._do_mobility_staypoints(p, t)
        if a == "mobility_triplegs":
            return self._do_mobility_triplegs(p, t)
        if a == "mobility_hierarchy":
            return self._do_mobility_hierarchy(p, t)
        if a == "mobility_transport":
            return self._do_mobility_transport(p, t)
        if a == "mobility_locations":
            return self._do_mobility_locations(p, t)
        if a == "mobility_summary":
            return self._do_mobility_summary(p, t)
        if a == "mobility_plot":
            return self._do_mobility_plot(p, t)
        if a == "mobility_heatmap":
            return self._do_mobility_heatmap(p, t)
        if a == "mobility_modal":
            return self._do_mobility_modal(p, t)

        if a == "check_update":
            from geoclaw_claude.updater import check
            result = check(verbose=False)
            return {"status": result.status, "summary": result.summary()}

        if a == "memory_status":
            if self._mem:
                return self._mem.status()
            return {"error": "Memory 系统未初始化"}

        if a == "memory_search":
            if self._mem:
                query   = p.get("query", "")
                results = self._mem.recall(query)
                return [{"id": e.id, "title": e.title, "importance": e.importance}
                        for e in results]
            return []

        if a == "help":
            return self._do_help(p)

        if a == "unknown":
            raise ValueError(p.get("reason", "无法识别的操作"))

        raise ValueError(f"未知操作: {a}")

    # ── 具体操作实现 ──────────────────────────────────────────────────────────

    def _resolve_layer(self, name: str, fallback_last: bool = True) -> Any:
        """解析图层名称，找不到时尝试 last_result。"""
        if name:
            layer = self.get_layer(name)
            if layer is not None:
                return layer
        if fallback_last and self._last_result is not None:
            return self._last_result
        raise ValueError(
            f"找不到图层 '{name}'。"
            f"当前可用图层: {self.list_layers() or ['(空)']}"
        )

    def _do_load(self, p: dict, t: list) -> Any:
        from geoclaw_claude.io.vector import load_vector
        path  = p.get("path", "")
        name  = p.get("name", "") or (t[0] if t else "layer")
        if not path:
            raise ValueError("请指定文件路径，例如：加载 hospitals.geojson")
        layer = load_vector(path)
        layer_name = name or path.split("/")[-1].split(".")[0]
        self.add_layer(layer_name, layer)
        return layer

    def _do_save(self, p: dict, t: list) -> Any:
        from geoclaw_claude.io.vector import save_vector
        raw_path = p.get("path", "output.geojson")
        lname = p.get("layer", "") or (t[0] if t else "")
        layer = self._resolve_layer(lname)

        # 安全检查：将输出路径重定向到输出目录
        try:
            safe_path = Path(self._get_safe_output_path(raw_path))
        except Exception:
            from pathlib import Path
            safe_path = Path(raw_path)

        save_vector(layer, str(safe_path))
        return {"saved": str(safe_path), "features": len(layer)}

    def _do_buffer(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import buffer
        lname    = p.get("layer", "") or (t[0] if t else "")
        layer    = self._resolve_layer(lname)
        distance = float(p.get("distance", 1000))
        unit     = p.get("unit", "meters")
        result   = buffer(layer, distance, unit=unit)
        out_name = f"{lname or 'layer'}_buf{int(distance)}"
        self.add_layer(out_name, result)
        return result

    def _do_clip(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import clip
        lname  = p.get("layer",  "") or (t[0] if t else "")
        mname  = p.get("mask",   "") or (t[1] if len(t) > 1 else "")
        layer  = self._resolve_layer(lname)
        mask   = self._resolve_layer(mname, fallback_last=False)
        if mask is None:
            raise ValueError(f"找不到裁剪边界图层 '{mname}'")
        result = clip(layer, mask)
        self.add_layer(f"{lname or 'layer'}_clipped", result)
        return result

    def _do_intersect(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import intersect
        la = self._resolve_layer(p.get("layer_a", "") or (t[0] if t else ""))
        lb = self._resolve_layer(p.get("layer_b", "") or (t[1] if len(t) > 1 else ""),
                                  fallback_last=False)
        result = intersect(la, lb)
        self.add_layer("intersect_result", result)
        return result

    def _do_union(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import union
        la = self._resolve_layer(p.get("layer_a", "") or (t[0] if t else ""))
        lb = self._resolve_layer(p.get("layer_b", "") or (t[1] if len(t) > 1 else ""),
                                  fallback_last=False)
        result = union(la, lb)
        self.add_layer("union_result", result)
        return result

    def _do_nearest_neighbor(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import nearest_neighbor
        sname  = p.get("source", "") or (t[0] if t else "")
        tname  = p.get("target", "") or (t[1] if len(t) > 1 else "")
        source = self._resolve_layer(sname)
        target = self._resolve_layer(tname, fallback_last=False)
        if target is None:
            raise ValueError(f"找不到目标图层 '{tname}'")
        result = nearest_neighbor(source, target)
        self.add_layer(f"{sname or 'layer'}_nn", result)
        return result

    def _do_spatial_join(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import spatial_join
        sname  = p.get("source", "") or (t[0] if t else "")
        tname  = p.get("target", "") or (t[1] if len(t) > 1 else "")
        source = self._resolve_layer(sname)
        target = self._resolve_layer(tname, fallback_last=False)
        how    = p.get("how", "left")
        pred   = p.get("predicate", "intersects")
        result = spatial_join(source, target, how=how, predicate=pred)
        self.add_layer("sjoin_result", result)
        return result

    def _do_kde(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import kde
        lname = p.get("layer", "") or (t[0] if t else "")
        layer = self._resolve_layer(lname)
        bw    = float(p.get("bandwidth", 0.05))
        gs    = int(p.get("grid_size",  100))
        return kde(layer, bandwidth=bw, grid_size=gs)

    def _do_zonal_stats(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import zonal_stats
        zname  = p.get("zones",  "") or (t[0] if t else "")
        pname  = p.get("points", "") or (t[1] if len(t) > 1 else "")
        zones  = self._resolve_layer(zname)
        points = self._resolve_layer(pname, fallback_last=False)
        if points is None:
            raise ValueError(f"找不到点图层 '{pname}'")
        stat   = p.get("stat", "count")
        result = zonal_stats(zones, points, stat=stat)
        self.add_layer("zonal_result", result)
        return result

    def _do_calculate_area(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.spatial_ops import calculate_area
        lname  = p.get("layer", "") or (t[0] if t else "")
        layer  = self._resolve_layer(lname)
        unit   = p.get("unit", "km2")
        result = calculate_area(layer, unit=unit)
        return result

    def _do_isochrone(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.network import build_network, isochrone
        center  = p.get("center")
        minutes = p.get("minutes", [5, 10, 15])
        ntype   = p.get("network_type", "drive")
        if center is None:
            raise ValueError("请提供等时圈中心坐标，例如：(114.30, 30.60)")
        lon, lat = center if isinstance(center, (list, tuple)) else (center[0], center[1])
        bbox    = (lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1)
        G       = build_network(bbox, network_type=ntype)
        result  = isochrone(G, center=(lon, lat), minutes=minutes)
        self.add_layer("isochrone", result)
        return result

    def _do_shortest_path(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.network import build_network, shortest_path
        origin      = p.get("origin")
        destination = p.get("destination")
        ntype       = p.get("network_type", "drive")
        if not origin or not destination:
            raise ValueError("请提供起点和终点坐标")
        all_coords = list(origin) + list(destination)
        bbox = (min(all_coords[0], all_coords[2]) - 0.05,
                min(all_coords[1], all_coords[3]) - 0.05,
                max(all_coords[0], all_coords[2]) + 0.05,
                max(all_coords[1], all_coords[3]) + 0.05)
        G      = build_network(bbox, network_type=ntype)
        result = shortest_path(G, origin=origin, destination=destination)
        self.add_layer("shortest_path", result)
        return result

    def _do_network_build(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.network import build_network
        lname = p.get("layer", "") or (t[0] if t else "")
        ntype = p.get("network_type", "drive")
        if lname:
            layer = self._resolve_layer(lname)
            bbox  = layer.bounds if hasattr(layer, "bounds") else layer.data.total_bounds
        else:
            bbox = p.get("bbox")
            if not bbox:
                raise ValueError("请提供图层或 bbox 坐标范围")
        G = build_network(bbox, network_type=ntype)
        self._layers["__network__"] = G
        return G

    def _do_coord_transform(self, p: dict, t: list) -> Any:
        from geoclaw_claude.utils.coord_transform import transform_layer
        lname    = p.get("layer", "") or (t[0] if t else "")
        layer    = self._resolve_layer(lname)
        from_crs = p.get("from_crs", "wgs84")
        to_crs   = p.get("to_crs",   "gcj02")
        result   = transform_layer(layer, from_crs, to_crs)
        out_name = f"{lname or 'layer'}_{to_crs}"
        self.add_layer(out_name, result)
        return result

    def _do_render(self, p: dict, t: list, interactive: bool = False) -> Any:
        layers = []
        for name in (t or []):
            layer = self.get_layer(name)
            if layer is not None:
                layers.append(layer)
        if not layers and self._last_result is not None:
            layers = [self._last_result]
        if not layers:
            raise ValueError("没有可制图的图层，请先加载或分析数据")
        title = p.get("title", "GeoClaw-claude 地图")

        def _safe_outpath(filename: str) -> str:
            try:
                return self._get_safe_output_path(filename)
            except Exception:
                return filename

        if interactive:
            from geoclaw_claude.cartography.renderer import render_interactive
            raw_path = render_interactive(layers, title=title)
            safe = _safe_outpath(str(raw_path).split("/")[-1])
            import shutil, pathlib
            if str(raw_path) != safe:
                pathlib.Path(safe).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(raw_path), safe)
            return {"type": "interactive", "path": safe}
        else:
            import matplotlib
            matplotlib.use("Agg")
            from geoclaw_claude.cartography.renderer import render_map
            fig = render_map(layers, title=title)
            # 保存到 output_dir，不依赖 GUI display（防止终端崩溃）
            filename = "map.png"
            safe = _safe_outpath(filename)
            import pathlib
            pathlib.Path(safe).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(safe, bbox_inches="tight", dpi=150)
            import matplotlib.pyplot as plt
            plt.close(fig)
            return {"type": "static", "path": safe}

    def _do_download_osm(self, p: dict, t: list) -> Any:
        from geoclaw_claude.io.osm import download_pois, download_boundary
        place    = p.get("place", "")
        poi_type = p.get("type", "poi")
        if not place:
            raise ValueError("请指定地名，例如：下载武汉市医院数据")
        boundary = download_boundary(place)
        layer    = download_pois(boundary.bounds, poi_type=poi_type)
        name     = f"{place}_{poi_type}"
        self.add_layer(name, layer)
        return layer

    # ── 移动性分析操作 ───────────────────────────────────────────────────────

    def _do_mobility_load(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import read_positionfixes
        path = p.get("path", "")
        if not path:
            raise ValueError("请指定 GPS 数据文件路径，例如：读入 gps_tracks.csv")
        pfs = read_positionfixes(path)
        self.add_layer("positionfixes", pfs)
        return pfs

    def _do_mobility_staypoints(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import generate_staypoints
        pfs = self._resolve_layer("positionfixes")
        pfs_updated, sp = generate_staypoints(
            pfs,
            dist_threshold=float(p.get("dist_threshold", 100)),
            time_threshold=float(p.get("time_threshold", 5)),
        )
        self.add_layer("positionfixes", pfs_updated)
        self.add_layer("staypoints", sp)
        return sp

    def _do_mobility_triplegs(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import generate_triplegs
        pfs = self._resolve_layer("positionfixes")
        sp  = self._resolve_layer("staypoints")
        if sp is None:
            raise ValueError("请先生成停留点（运行：生成停留点）")
        pfs_updated, tpls = generate_triplegs(pfs, sp)
        self.add_layer("positionfixes", pfs_updated)
        self.add_layer("triplegs", tpls)
        return tpls

    def _do_mobility_hierarchy(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import generate_full_hierarchy
        pfs = self._resolve_layer("positionfixes")
        h = generate_full_hierarchy(
            pfs,
            dist_threshold=float(p.get("dist_threshold", 100)),
            time_threshold=float(p.get("time_threshold", 5)),
            location_epsilon=float(p.get("location_epsilon", 100)),
        )
        for key, val in h.items():
            self.add_layer(key, val)
        self._layers["__mobility_hierarchy__"] = h
        return h

    def _do_mobility_transport(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import predict_transport_mode
        tpls = self._resolve_layer("triplegs")
        if tpls is None:
            raise ValueError("请先生成出行段")
        result = predict_transport_mode(tpls, method=p.get("method", "simple-coarse"))
        self.add_layer("triplegs", result)
        return result

    def _do_mobility_locations(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import generate_locations, identify_home_work
        sp = self._resolve_layer("staypoints")
        if sp is None:
            raise ValueError("请先生成停留点")
        sp_updated, locs = generate_locations(
            sp, epsilon=float(p.get("epsilon", 100))
        )
        self.add_layer("staypoints", sp_updated)
        self.add_layer("locations", locs)
        method = p.get("method", "")
        if method in ("osna", "freq"):
            try:
                locs = identify_home_work(sp_updated, locs, method=method)
                self.add_layer("locations", locs)
            except Exception:
                pass
        return locs

    def _do_mobility_summary(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import mobility_summary
        h = self._layers.get("__mobility_hierarchy__")
        if h is None:
            h = {
                "positionfixes": self._layers.get("positionfixes"),
                "staypoints":    self._layers.get("staypoints"),
                "triplegs":      self._layers.get("triplegs"),
                "locations":     self._layers.get("locations"),
            }
            h = {k: v for k, v in h.items() if v is not None}
        return mobility_summary(h, user_id=p.get("user_id"))

    def _do_mobility_plot(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import plot_mobility_layers
        h = self._layers.get("__mobility_hierarchy__", {
            k: self._layers.get(k)
            for k in ("positionfixes", "staypoints", "triplegs", "locations")
            if self._layers.get(k) is not None
        })
        fig = plot_mobility_layers(h, user_id=p.get("user_id"))
        return {"type": "mobility_map", "figure": fig}

    def _do_mobility_heatmap(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import plot_activity_heatmap
        sp = self._resolve_layer("staypoints")
        if sp is None:
            raise ValueError("请先生成停留点")
        fig = plot_activity_heatmap(sp, user_id=p.get("user_id"))
        return {"type": "activity_heatmap", "figure": fig}

    def _do_mobility_modal(self, p: dict, t: list) -> any:
        from geoclaw_claude.analysis.mobility import plot_modal_split
        tpls = self._resolve_layer("triplegs")
        if tpls is None:
            raise ValueError("请先生成出行段并预测交通方式")
        fig = plot_modal_split(tpls, metric=p.get("metric", "count"))
        return {"type": "modal_split", "figure": fig}

    def _do_help(self, p: dict) -> dict:
        topic = p.get("topic", "")
        TOPICS = {
            "buffer": "buffer <距离><单位> — 对当前图层做缓冲区\n  例：对医院做1公里缓冲区",
            "load":   "加载 <文件路径> — 加载 GeoJSON/SHP 文件\n  例：加载 hospitals.geojson",
            "render": "制图 / 可视化 — 对当前或指定图层制图\n  例：用折线样式显示武汉路网",
            "kde":    "核密度分析 <图层> — 生成密度热力图\n  例：对医院做核密度分析",
        }
        if topic in TOPICS:
            return {"topic": topic, "help": TOPICS[topic]}
        return {
            "topic": "总览",
            "commands": list(TOPICS.keys()),
            "help": (
                "支持的操作：加载、保存、缓冲区、裁剪、叠加、最近邻、"
                "核密度、分区统计、等时圈、最短路径、坐标转换、制图、下载OSM\n"
                "示例：\n"
                "  '加载 hospitals.geojson'\n"
                "  '对医院做1公里缓冲区'\n"
                "  '然后用交互地图显示'\n"
                "  '下载武汉市公园数据'"
            ),
        }

    # ── 结果消息生成 ─────────────────────────────────────────────────────────

    def _build_message(self, intent: ParsedIntent, result: Any) -> str:
        try:
            a = intent.action
            if a == "load":
                n = len(result) if hasattr(result, "__len__") else "?"
                return f"已加载 {n} 个要素"
            if a == "buffer":
                n = len(result) if hasattr(result, "__len__") else "?"
                dist = intent.params.get("distance", "")
                unit = intent.params.get("unit", "meters")
                return f"缓冲区完成，{n} 个要素，半径 {dist}{unit}"
            if a == "clip":
                n = len(result) if hasattr(result, "__len__") else "?"
                return f"裁剪完成，保留 {n} 个要素"
            if a == "nearest_neighbor":
                n = len(result) if hasattr(result, "__len__") else "?"
                return f"最近邻分析完成，{n} 个要素（含 nn_distance 字段）"
            if a == "kde":
                gs = intent.params.get("grid_size", 100)
                return f"核密度分析完成，{gs}×{gs} 网格"
            if a == "calculate_area":
                if hasattr(result, "data"):
                    mean_area = result.data.get("area", [0]).mean() if hasattr(result.data.get("area", None), "mean") else "?"
                    unit = intent.params.get("unit", "km2")
                    return f"面积计算完成，均值 {mean_area:.4f} {unit}"
            if a == "isochrone":
                n = len(result) if hasattr(result, "__len__") else "?"
                return f"等时圈生成完成，{n} 个等时区"
            if a == "download_osm":
                n = len(result) if hasattr(result, "__len__") else "?"
                return f"OSM 数据下载完成，{n} 个 POI"
            if a in ("render", "render_interactive"):
                return "地图生成完成"
            if a == "check_update":
                return result.get("summary", "版本检测完成") if isinstance(result, dict) else str(result)
            if a == "help":
                return result.get("help", "")[:80] + "..." if isinstance(result, dict) else str(result)
            if a.startswith("mobility_"):
                return f"{a.replace('mobility_', '')} 完成"
            return intent.explanation or f"{a} 完成"
        except Exception:
            return f"{intent.action} 完成"

    # ── 会话结束 ─────────────────────────────────────────────────────────────

    def end_session(self, title: str = "", flush: bool = True) -> None:
        """结束当前会话，将执行摘要写入长期记忆。"""
        if self._mem:
            ok = sum(1 for r in self._history if r.success)
            self._mem.end_session(
                title=title or f"NL会话 ({ok}/{len(self._history)} 成功)",
                tags=["nl", "natural_language"],
                flush=flush,
            )

    def __repr__(self) -> str:
        return (f"NLExecutor(layers={self.list_layers()}, "
                f"history={len(self._history)}步)")
