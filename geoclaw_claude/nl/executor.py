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

        # LLM 引用（供 ReAct 使用，由外部注入）
        self._llm = None
        self._toolkit = None

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
        if layer is None:
            return   # 不存储 None 图层，避免后续查找误判
        self._layers[name] = layer
        if self._mem:
            self._mem.remember(f"layer_{name}", layer, category="result",
                               tags=["layer", name])

    def get_layer(self, name: str) -> Any:
        # 先查名称完整匹配（跳过 None 值）
        if name in self._layers and self._layers[name] is not None:
            return self._layers[name]
        # 模糊匹配（前缀，跳过 None 值）
        for k, v in self._layers.items():
            if v is not None and (k.startswith(name) or name.startswith(k)):
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
        # 把原始用户文本注入 params，供各 _do_* 方法兜底解析坐标等
        if intent.raw_text and "_raw_text" not in intent.params:
            intent.params["_raw_text"] = intent.raw_text
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
        # 收集失败步骤的错误信息
        failed = [r for r in results if not r.success]
        err_msg = failed[0].error if failed else None
        er  = ExecutionResult(
            success=last_ok,
            action="pipeline",
            result=[r.result for r in results],
            message=msg,
            error=err_msg,
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


        # ── 本地工具调用（直接触发）────────────────────────────────────────────
        if a == "tool_run":
            return self._do_tool_run(p)

        # ── Skill 系统 ─────────────────────────────────────────────────────────
        if a == "skill_run":
            return self._do_skill_run(p, t)

        if a == "skill_list":
            return self._do_skill_list()

        # ── ReAct 智能体（自动工具链）──────────────────────────────────────────
        if a == "react":
            return self._do_react(p)

        if a == "help":
            return self._do_help(p)

        if a == "chat":
            reply = p.get("reply", "好的！")
            return ExecutionResult(success=True, action="chat", result=reply, message=reply)

        if a == "status":
            layers = self.list_layers()
            layer_info = "\n".join(f"  • {l}" for l in layers) if layers else "  (暂无图层)"
            msg = f"当前会话状态：\n已加载图层 ({len(layers)} 个)：\n{layer_info}"
            return ExecutionResult(success=True, action="status", result=layers, message=msg)

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
        out_name = p.get("output_name") or p.get("result_name") or f"{lname or 'layer'}_buf{int(distance)}"
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
        # 兜底1：如果 center 为 None，尝试从 lon/lat 字段组合
        if center is None:
            lon_v = p.get("lon") or p.get("longitude") or p.get("x")
            lat_v = p.get("lat") or p.get("latitude") or p.get("y")
            if lon_v is not None and lat_v is not None:
                center = (float(lon_v), float(lat_v))
        # 兜底2：从原始用户文本正则提取坐标（应对LLM解析失败）
        if center is None:
            pass  # 将在 _raw_text 注入后处理
        if center is None:
            raw = p.get("_raw_text", "")
            if raw:
                import re as _re
                # 匹配 "经度X，纬度Y" 或 "(X, Y)" 或 "X,Y"
                m = _re.search(r"经度\s*([\d.]+)[，,]\s*纬度\s*([\d.]+)", raw)
                if m:
                    center = (float(m.group(1)), float(m.group(2)))
                if center is None:
                    m = _re.search(r"\(([\d.]+)[,，\s]+([\d.]+)\)", raw)
                    if m:
                        a, b = float(m.group(1)), float(m.group(2))
                        center = (a, b) if a > b else (b, a)
        if center is None:
            raise ValueError("请提供等时圈中心坐标，例如：(114.30, 30.60)")
        # 支持字符串坐标 "lon,lat" 或地名
        if isinstance(center, str):
            # 先尝试解析为数字坐标
            try:
                center = self._parse_coord(center)
            except ValueError:
                # 如果不是数字坐标，尝试 geocode 地名
                try:
                    import osmnx as ox
                    gdf = ox.geocode_to_gdf(center)
                    lon_c = float(gdf.geometry.centroid.x.iloc[0])
                    lat_c = float(gdf.geometry.centroid.y.iloc[0])
                    center = (lon_c, lat_c)
                    print(f"  ↳ 地名 '{center}' geocode: ({lon_c:.4f}, {lat_c:.4f})")
                except Exception:
                    raise ValueError(f"无法解析等时圈中心 '{center}'，请使用 'lon,lat' 坐标格式")
        elif isinstance(center, dict):
            center = (float(center.get("lon", center.get("longitude", 0))),
                      float(center.get("lat", center.get("latitude", 0))))
        lon, lat = center if isinstance(center, (list, tuple)) else (center[0], center[1])
        # 动态计算 bbox：步行~5km/h，驾车~50km/h，给 2× 余量
        max_min = max(minutes) if isinstance(minutes, list) else minutes
        speed_km_per_min = {"walk": 5/60, "drive": 50/60, "bike": 15/60}.get(ntype, 5/60)
        radius_deg = (max_min * speed_km_per_min / 111) * 2.5  # 2.5× 余量
        radius_deg = max(0.03, min(radius_deg, 0.15))  # 限制在 0.03~0.15°
        bbox = (lon - radius_deg, lat - radius_deg, lon + radius_deg, lat + radius_deg)
        print(f"  等时圈 bbox: ±{radius_deg:.3f}° (max={max_min}min, {ntype})")
        # 支持传入本地路网文件（graph_file 参数），绕过在线下载
        graph_file = p.get("graph_file")
        try:
            if graph_file:
                import osmnx as ox
                G = ox.load_graphml(graph_file)
                print(f"  ↳ 使用本地路网: {graph_file}")
            else:
                G = build_network(bbox, network_type=ntype)
        except Exception as net_err:
            err_str = str(net_err).lower()
            if any(k in err_str for k in ("timeout", "timed out", "connection", "overpass", "network")):
                raise RuntimeError(
                    f"路网下载超时或网络不可达，无法获取 OSM 步行路网。\n"
                    f"建议：① 检查网络连接；② 稍后重试。\n原始错误: {net_err}"
                ) from net_err
            raise
        result  = isochrone(G, center=(lon, lat), minutes=minutes)
        out_name = p.get("output_name") or p.get("name") or "isochrone"
        self.add_layer(out_name, result)
        return result

    @staticmethod
    def _parse_coord(val) -> tuple:
        """将字符串/列表/元组解析为 (lon, lat) float tuple。"""
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return (float(val[0]), float(val[1]))
        if isinstance(val, str):
            parts = [x.strip() for x in val.replace(";", ",").split(",")]
            if len(parts) >= 2:
                try:
                    a, b = float(parts[0]), float(parts[1])
                    # 自动判断 lat,lon vs lon,lat（中国经度 > 纬度）
                    if a < 90 and b > 90:   # a=lat, b=lon
                        return (b, a)
                    return (a, b)           # 否则原样返回
                except ValueError:
                    pass
        raise ValueError(f"无法解析坐标值: {val!r}，请使用 'lon,lat' 格式")

    def _do_shortest_path(self, p: dict, t: list) -> Any:
        from geoclaw_claude.analysis.network import build_network, shortest_path
        origin      = p.get("origin")
        destination = p.get("destination")
        ntype       = p.get("network_type", "drive")
        # 兜底：origin/destination 可能以 origin_lon/origin_lat 形式传入
        if origin is None:
            olon = p.get("origin_lon") or p.get("from_lon") or p.get("start_lon")
            olat = p.get("origin_lat") or p.get("from_lat") or p.get("start_lat")
            if olon and olat:
                origin = f"{olon},{olat}"
        if destination is None:
            dlon = p.get("destination_lon") or p.get("to_lon") or p.get("end_lon")
            dlat = p.get("destination_lat") or p.get("to_lat") or p.get("end_lat")
            if dlon and dlat:
                destination = f"{dlon},{dlat}"
        if not origin or not destination:
            raise ValueError("请提供起点和终点坐标")

        def _to_coord(val, label):
            """支持 'lon,lat' 字符串或地名→坐标。"""
            try:
                return self._parse_coord(val)
            except ValueError:
                # 尝试 geocode 地名
                if isinstance(val, str):
                    try:
                        import osmnx as ox
                        gdf = ox.geocode_to_gdf(val)
                        lon_c = float(gdf.geometry.centroid.x.iloc[0])
                        lat_c = float(gdf.geometry.centroid.y.iloc[0])
                        print(f"  ↳ {label} '{val}' geocode: ({lon_c:.4f}, {lat_c:.4f})")
                        return (lon_c, lat_c)
                    except Exception:
                        pass
                raise ValueError(f"无法解析{label}坐标: {val!r}")

        origin      = _to_coord(origin, "起点")
        destination = _to_coord(destination, "终点")
        all_coords = list(origin) + list(destination)
        # padding：两点距离的 50% 或最少 0.02°（约 2km），最多 0.08°
        span = max(abs(all_coords[0]-all_coords[2]), abs(all_coords[1]-all_coords[3]))
        pad = max(0.02, min(span * 0.5, 0.08))
        bbox = (min(all_coords[0], all_coords[2]) - pad,
                min(all_coords[1], all_coords[3]) - pad,
                max(all_coords[0], all_coords[2]) + pad,
                max(all_coords[1], all_coords[3]) + pad)
        print(f"  ↓ 下载路网: bbox [{bbox[0]:.3f},{bbox[1]:.3f},{bbox[2]:.3f},{bbox[3]:.3f}] ({ntype})")
        graph_file = p.get("graph_file")
        try:
            if graph_file:
                import osmnx as ox
                G = ox.load_graphml(graph_file)
                print(f"  ↳ 使用本地路网: {graph_file}")
            else:
                G = build_network(bbox, network_type=ntype)
        except Exception as net_err:
            err_str = str(net_err).lower()
            if any(k in err_str for k in ("timeout", "timed out", "connection", "overpass", "network")):
                raise RuntimeError(
                    f"路网下载超时或网络不可达。\n"
                    f"建议：① 检查网络连接；② 稍后重试。\n原始错误: {net_err}"
                ) from net_err
            raise
        result = shortest_path(G, origin=origin, destination=destination)
        out_name = p.get("output_name") or p.get("name") or "shortest_path"
        self.add_layer(out_name, result)
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

    def _render_kde(self, kde_result: dict, p: dict) -> Any:
        """渲染 KDE 栅格结果为静态热力图"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        grid   = kde_result["grid"]
        extent = kde_result["extent"]  # (xmin, ymin, xmax, ymax)
        title  = p.get("title", "核密度分析热力图")
        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.imshow(
            grid,
            origin="lower",
            extent=[extent[0], extent[2], extent[1], extent[3]],
            cmap="hot_r",
            aspect="auto",
        )
        plt.colorbar(im, ax=ax, label="密度")
        ax.set_title(title)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        def _safe(f):
            try: return self._get_safe_output_path(f)
            except: return f
        safe = _safe("kde_heatmap.png")
        import pathlib
        pathlib.Path(safe).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(safe, bbox_inches="tight", dpi=150)
        plt.close(fig)
        return {"type": "static", "path": safe}

    def _do_render(self, p: dict, t: list, interactive: bool = False) -> Any:
        def _is_kde(obj):
            return isinstance(obj, dict) and "grid" in obj and "extent" in obj

        from geoclaw_claude.core.layer import GeoLayer as _GL
        def _is_renderable(obj):
            """只有 GeoLayer 才可以渲染，过滤掉 dict/str/None"""
            return isinstance(obj, _GL)

        layers = []
        for name in (t or []):
            layer = self.get_layer(name)
            if layer is not None and _is_renderable(layer):
                layers.append(layer)
            elif layer is not None and isinstance(layer, dict):
                # skill 返回的 dict 里可能有 GeoLayer，提取出来
                for v in layer.values():
                    if _is_renderable(v):
                        layers.append(v)
                        break
        if not layers and self._last_result is not None:
            last = self._last_result
            if _is_kde(last):
                return self._render_kde(last, p)
            if _is_renderable(last):
                layers = [last]
            elif isinstance(last, dict):
                for v in last.values():
                    if _is_renderable(v):
                        layers.append(v)
                        break
        if not layers:
            for v in list(self._layers.values()):
                if _is_kde(v):
                    return self._render_kde(v, p)
                if _is_renderable(v):
                    layers.append(v)
            if layers:
                layers = layers[:3]  # 最多取3个图层
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
        import re
        place    = p.get("place", "")
        poi_type = p.get("type", "poi")
        if not place:
            raise ValueError("请指定地名，例如：下载武汉市医院数据")
        boundary = download_boundary(place)
        layer    = download_pois(boundary.bounds, poi_type=poi_type)
        # 清洗 place 名，去掉逗号/空格等特殊字符，确保图层名可被 LLM 引用
        safe_place = re.sub(r"[,，\s]+", "_", place).strip("_")
        name = p.get("output_name") or p.get("name") or f"{safe_place}_{poi_type}"
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
                if result is None or (hasattr(result, "__len__") and len(result) == 0):
                    return "OSM 数据下载完成，但未找到匹配的 POI（该区域可能无此类数据）"
                n = len(result) if hasattr(result, "__len__") else "?"
                return f"OSM 数据下载完成，{n} 个 POI"
            if a in ("render", "render_interactive"):
                if isinstance(result, dict):
                    path = result.get("path", "")
                    rtype = result.get("type", "")
                    return f"地图生成完成\n  type: {rtype}\n  path: {path}"
                return "地图生成完成"
            if a == "check_update":
                return result.get("summary", "版本检测完成") if isinstance(result, dict) else str(result)
            if a == "help":
                return result.get("help", "")[:80] + "..." if isinstance(result, dict) else str(result)
            if a in ("tool_run", "react"):
                return result.get("answer", result.get("output", "工具执行完成"))[:100] if isinstance(result, dict) else str(result)
            if a == "skill_list":
                return result[:400] if isinstance(result, str) else str(result)[:400]
            if a == "skill_run":
                if isinstance(result, dict):
                    report = result.get("report", "")
                    if report:
                        return f"✓ Skill 执行完成\n{report[:300]}"
                    keys = [k for k in result if k not in ("report",)]
                    return f"✓ Skill 执行完成，输出: {', '.join(str(k) for k in keys[:5])}"
                return "✓ Skill 执行完成"
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

    # ── 本地工具方法 ──────────────────────────────────────────────────────────

    def _get_toolkit(self):
        """获取（或懒初始化）LocalToolKit。"""
        if not hasattr(self, "_toolkit") or self._toolkit is None:
            from geoclaw_claude.tools import LocalToolKit, ToolPermission
            from geoclaw_claude.config import Config
            cfg = Config.load()
            perm_str = getattr(cfg, "tool_permission", "sandbox")
            perm_map = {
                "full":      ToolPermission.FULL,
                "sandbox":   ToolPermission.SANDBOX,
                "whitelist": ToolPermission.WHITELIST,
            }
            perm = perm_map.get(perm_str.lower(), ToolPermission.SANDBOX)
            self._toolkit = LocalToolKit(permission=perm)
        return self._toolkit

    def _do_tool_run(self, p: dict) -> Any:
        """
        直接执行单个本地工具。
        intent params: tool(工具名), 其余参数透传给工具。
        """
        tool_name = p.pop("tool", "")
        if not tool_name:
            raise ValueError("请指定工具名，例如：tool=shell, cmd='ls ~'")
        kit = self._get_toolkit()
        result = kit.run(tool_name, **p)
        if not result.success:
            raise ValueError(f"工具 [{tool_name}] 执行失败: {result.error}")
        return {"tool": tool_name, "output": result.output,
                "duration": result.duration, "metadata": result.metadata}

    def _do_react(self, p: dict) -> Any:
        """
        启动 ReAct 智能体，自动链式调用工具完成任务。
        intent params: task(任务描述), max_steps(可选)
        """
        task = p.get("task", "")
        if not task:
            raise ValueError("请描述任务，例如：统计 ~/geoclaw_output 下的 geojson 文件数量")
        max_steps = int(p.get("max_steps", 12))

        kit = self._get_toolkit()
        # 获取 LLM provider
        llm = getattr(self, "_llm", None)
        if llm is None:
            # 尝试从 processor 读取
            raise ValueError(
                "ReAct 模式需要配置 LLM。请运行 geoclaw-claude onboard 设置 API Key。"
            )

        from geoclaw_claude.tools.react_agent import ReActAgent
        agent = ReActAgent(toolkit=kit, llm=llm, max_steps=max_steps, verbose=True)
        result = agent.run(task)

        return {
            "task":    result.task,
            "answer":  result.final_answer,
            "steps":   len(result.steps),
            "success": result.success,
            "duration": result.total_duration,
        }

    # ── Skill 系统 ─────────────────────────────────────────────────────────────

    def _do_skill_list(self) -> Any:
        """列出所有已注册的 Skill。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        skills = sm.list_skills()
        if not skills:
            return "暂无可用 Skill。"
        lines = ["可用 Skill 列表：\n"]
        for s in skills:
            name    = s.get("name", "?")
            ver     = s.get("version", "?")
            desc    = s.get("description", "")[:60]
            builtin = "内置" if s.get("builtin") else "用户"
            lines.append(f"  • {name} v{ver} [{builtin}] — {desc}")
        return "\n".join(lines)

    def _do_skill_run(self, p: dict, t: list) -> Any:
        """
        运行指定 Skill。
        params: name(Skill名称) + Skill 所需参数键值对。
        从当前 executor 的图层中注入数据到 SkillContext。
        """
        from geoclaw_claude.skill_manager import SkillManager, SkillContext

        skill_name = p.get("name", "") or (t[0] if t else "")
        if not skill_name:
            raise ValueError("请指定 Skill 名称，例如：运行 hospital_coverage Skill")

        # 构建 SkillContext
        skill_params = {k: v for k, v in p.items() if k != "name"}
        # 预处理: 拆分 center="lon,lat" → center_lon, center_lat
        if "center" in skill_params and "center_lon" not in skill_params:
            center_str = str(skill_params.pop("center"))
            parts = [x.strip() for x in center_str.replace(";", ",").split(",")]
            if len(parts) >= 2:
                skill_params["center_lon"] = parts[0]
                skill_params["center_lat"] = parts[1]
        # 预处理: cutoffs/minutes → cutoffs
        if "minutes" in skill_params and "cutoffs" not in skill_params:
            skill_params["cutoffs"] = str(skill_params.pop("minutes"))
        # 预处理: 如果未提供 city，尝试从当前会话图层名推断
        if "city" not in skill_params or not skill_params["city"]:
            for lname in self._layers:
                # 图层名格式通常是 "城市名_类型"
                if "_" in lname:
                    skill_params.setdefault("city", lname.split("_")[0])
                    break
        llm = getattr(self, "_llm", None)
        use_ai = llm is not None

        ctx = SkillContext(use_ai=use_ai)
        # 将 executor 中所有图层注入 SkillContext
        for lname, layer in self._layers.items():
            ctx._layers[lname] = layer
        # 注入参数
        ctx._params = skill_params
        # Bug修复: 图层别名映射 —— 若参数值是已知图层名，在ctx中建立别名
        # 例如 zones="pop_grid" → ctx._layers["zones"] = ctx._layers["pop_grid"]
        _known_layers = set(self._layers.keys())
        _primary_layer = None  # 主图层，设为 input
        for param_key, param_val in skill_params.items():
            if isinstance(param_val, str) and param_val in _known_layers:
                ctx._layers[param_key] = self._layers[param_val]
                # 第一个图层参数作为主图层
                if _primary_layer is None:
                    _primary_layer = self._layers[param_val]
        # 设定 input：优先用 skill_params 里明确的 layer/input/candidates 参数
        _input_keys = ["layer", "input", "candidates", "hospitals", "points"]
        for k in _input_keys:
            if k in skill_params and skill_params[k] in _known_layers:
                ctx._layers["input"] = self._layers[skill_params[k]]
                break
        else:
            # 否则用第一个别名映射的图层，或最后一个加载的图层
            if _primary_layer is not None:
                ctx._layers["input"] = _primary_layer
            elif self._layers:
                ctx._layers["input"] = list(self._layers.values())[-1]
        # 注入 LLM 并 patch ask_ai
        if llm is not None:
            ctx._llm = llm
            _llm_ref = llm
            def _ask_ai_patched(prompt: str, context_data=None) -> str:
                full = prompt
                if context_data:
                    full = f"{prompt}\n\n数据背景:\n{context_data}"
                try:
                    resp = _llm_ref.chat([{"role": "user", "content": full}])
                    # LLMResponse 对象需要取 .content；若已是字符串直接返回
                    if hasattr(resp, "content"):
                        return resp.content or ""
                    return str(resp)
                except Exception as e:
                    return f"(AI 调用失败: {e})"
            import types
            ctx.ask_ai = types.MethodType(lambda self, p, context_data=None: _ask_ai_patched(p, context_data), ctx)

        sm = SkillManager()
        result = sm.run(skill_name, ctx)

        # 把输出图层注册到当前 executor 会话
        if result and isinstance(result, dict):
            from geoclaw_claude.core.layer import GeoLayer
            _first_layer = None
            for key, val in result.items():
                try:
                    if isinstance(val, GeoLayer):
                        reg_name = f"{skill_name}_{key}"
                        self.add_layer(reg_name, val)
                        if _first_layer is None:
                            _first_layer = (reg_name, val)
                except Exception:
                    pass
            # 额外注册两个通用别名方便 pipeline 中引用
            if _first_layer:
                self.add_layer(f"{skill_name}_result", _first_layer[1])
                self.add_layer(f"{skill_name}_output", _first_layer[1])
        elif result is not None:
            from geoclaw_claude.core.layer import GeoLayer
            if isinstance(result, GeoLayer):
                self.add_layer(f"{skill_name}_result", result)

        return result

