"""
tests/test_memory.py
====================
GeoClaw-claude Memory 系统完整测试
Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

测试覆盖:
  T01 - T06  短期记忆基本操作
  T07 - T10  短期记忆操作日志
  T11 - T14  短期记忆摘要生成
  T15 - T20  长期记忆基本 CRUD
  T21 - T24  长期记忆检索
  T25 - T27  短期→长期 flush
  T28 - T31  MemoryManager 统一接口
  T32 - T34  全局单例 get_memory()
  T35 - T36  与 GIS 操作集成
  T37        版本号验证
"""

import sys
import time
import tempfile
import traceback
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from geoclaw_claude.memory.short_term import ShortTermMemory, MemoryEntry
from geoclaw_claude.memory.long_term  import LongTermMemory
from geoclaw_claude.memory.manager    import MemoryManager, get_memory, reset_memory

# ════════════════════════════════════════════════════════════
#  T01 - T06  短期记忆基本操作
# ════════════════════════════════════════════════════════════

def test_t01_stm_create():
    stm = ShortTermMemory(session_id="test_s01")
    assert stm.session_id == "test_s01"
    assert len(stm) == 0
def test_t02_stm_store_retrieve():
    stm = ShortTermMemory()
    stm.store("key1", {"data": [1, 2, 3]}, category="result")
    stm.store("key2", "hello", category="param")
    assert stm.retrieve("key1") == {"data": [1, 2, 3]}
    assert stm.retrieve("key2") == "hello"
    assert stm.retrieve("nonexist", "default") == "default"
    assert len(stm) == 2
def test_t03_stm_has_delete():
    stm = ShortTermMemory()
    stm.store("k", 42)
    assert stm.has("k") is True
    stm.delete("k")
    assert stm.has("k") is False
    assert stm.retrieve("k") is None
def test_t04_stm_ttl_expire():
    stm = ShortTermMemory(default_ttl=0.1)  # 100ms TTL
    stm.store("fast_expire", "val", ttl=0.05)
    assert stm.retrieve("fast_expire") == "val"
    time.sleep(0.08)
    assert stm.retrieve("fast_expire") is None  # 已过期
def test_t05_stm_context():
    stm = ShortTermMemory()
    stm.set_context("project_name", "wuhan_2025")
    stm.set_context("active_crs", "EPSG:4326")
    assert stm.get_context("project_name") == "wuhan_2025"
    assert stm.get_context("active_crs") == "EPSG:4326"
    assert stm.get_context("nonexist", "fallback") == "fallback"
def test_t06_stm_list_keys():
    stm = ShortTermMemory()
    stm.store("r1", 1, category="result")
    stm.store("r2", 2, category="result")
    stm.store("p1", 3, category="param")
    all_keys    = stm.list_keys()
    result_keys = stm.list_keys(category="result")
    param_keys  = stm.list_keys(category="param")
    assert set(all_keys)    == {"r1", "r2", "p1"}
    assert set(result_keys) == {"r1", "r2"}
    assert set(param_keys)  == {"p1"}
# ════════════════════════════════════════════════════════════
#  T07 - T10  操作日志
# ════════════════════════════════════════════════════════════

def test_t07_op_log_basic():
    stm = ShortTermMemory()
    op_id = stm.log_operation("buffer", "hospitals, 1000m", result_key="buf")
    assert op_id == 1
    ops = stm.get_operation_log()
    assert len(ops) == 1
    assert ops[0].func_name == "buffer"
    assert ops[0].args_repr == "hospitals, 1000m"
    assert ops[0].result_key == "buf"
def test_t08_op_log_multiple():
    stm = ShortTermMemory()
    for i, fn in enumerate(["load", "buffer", "clip", "render"], 1):
        stm.log_operation(fn, f"args_{i}", duration=float(i) * 0.1)
    ops = stm.get_operation_log()
    assert len(ops) == 4
    assert [op.func_name for op in ops] == ["load", "buffer", "clip", "render"]
    assert sum(op.duration for op in ops) == pytest_approx(1.0) if False \
           else abs(sum(op.duration for op in ops) - 1.0) < 0.001
def test_t09_op_log_failure():
    stm = ShortTermMemory()
    stm.log_operation("buffer", "bad args", success=True)
    stm.log_operation("crash", "bad input", success=False, error="ValueError: invalid CRS")
    all_ops  = stm.get_operation_log()
    ok_ops   = stm.get_operation_log(only_success=True)
    assert len(all_ops) == 2
    assert len(ok_ops)  == 1
    assert all_ops[1].error == "ValueError: invalid CRS"
def test_t10_op_log_last():
    stm = ShortTermMemory()
    stm.log_operation("step1", "a")
    stm.log_operation("step2", "b")
    last = stm.get_last_operation()
    assert last.func_name == "step2"
# ════════════════════════════════════════════════════════════
#  T11 - T14  摘要生成
# ════════════════════════════════════════════════════════════

def test_t11_summarize_basic():
    stm = ShortTermMemory(session_id="sum_test")
    stm.store("layer_a", {"type": "GeoLayer"}, category="result")
    stm.store("param_x", 1000, category="param")
    stm.log_operation("buffer", "layer_a, 1000m", result_key="buf_a", duration=0.5)
    stm.log_operation("clip",   "buf_a, boundary",                    duration=0.3)

    summary = stm.summarize()
    assert summary["session_id"] == "sum_test"
    assert summary["operations"]["total"]   == 2
    assert summary["operations"]["success"] == 2
    assert summary["operations"]["failed"]  == 0
    assert abs(summary["operations"]["total_duration"] - 0.8) < 0.01
def test_t12_summarize_frequency():
    stm = ShortTermMemory()
    for _ in range(3):
        stm.log_operation("buffer", "x")
    for _ in range(2):
        stm.log_operation("clip", "y")
    summary = stm.summarize()
    freq = summary["operations"]["frequency"]
    assert freq["buffer"] == 3
    assert freq["clip"]   == 2
def test_t13_summarize_errors():
    stm = ShortTermMemory()
    stm.log_operation("ok_op",  "a", success=True)
    stm.log_operation("bad_op", "b", success=False, error="RuntimeError: OOM")
    summary = stm.summarize()
    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["func"] == "bad_op"
def test_t14_purge_expired():
    stm = ShortTermMemory()
    stm.store("fast", "x", ttl=0.05)
    stm.store("slow", "y", ttl=100)
    time.sleep(0.08)
    removed = stm.purge_expired()
    assert removed == 1
    assert stm.has("slow") is True
    assert stm.has("fast") is False
# ════════════════════════════════════════════════════════════
#  T15 - T20  长期记忆 CRUD
# ════════════════════════════════════════════════════════════

def _make_ltm() -> LongTermMemory:
    tmp = tempfile.mkdtemp()
    return LongTermMemory(memory_dir=Path(tmp))

def test_t15_ltm_store_get():
    ltm = _make_ltm()
    eid = ltm.store(
        title="武汉医院空间分析结果",
        content={"finding": "医院集中在三环内"},
        category="knowledge",
        tags=["wuhan", "hospital"],
        importance=0.8,
    )
    assert eid is not None
    entry = ltm.get(eid)
    assert entry is not None
    assert entry.title == "武汉医院空间分析结果"
    assert entry.content["finding"] == "医院集中在三环内"
    assert entry.importance == 0.8
    assert "wuhan" in entry.tags
def test_t16_ltm_delete():
    ltm = _make_ltm()
    eid = ltm.store("test", "del_me")
    assert ltm.get(eid) is not None
    ltm.delete(eid)
    assert ltm.get(eid) is None
def test_t17_ltm_persist():
    """验证关闭再重新打开后记忆仍存在。"""
    tmp = Path(tempfile.mkdtemp())
    ltm1 = LongTermMemory(memory_dir=tmp)
    eid  = ltm1.store("持久化测试", {"val": 42}, importance=0.9)

    ltm2 = LongTermMemory(memory_dir=tmp)   # 重新加载
    entry = ltm2.get(eid)
    assert entry is not None
    assert entry.title == "持久化测试"
    assert entry.content["val"] == 42
def test_t18_ltm_upsert():
    ltm = _make_ltm()
    eid = ltm.store("title_v1", {"v": 1}, entry_id="fixed_id")
    eid2 = ltm.store("title_v2", {"v": 2}, entry_id="fixed_id")
    assert eid == eid2 == "fixed_id"
    entry = ltm.get("fixed_id")
    assert entry.title == "title_v2"
    assert entry.content["v"] == 2
def test_t19_ltm_stats():
    ltm = _make_ltm()
    ltm.store("k1", "v", category="knowledge", importance=0.8)
    ltm.store("k2", "v", category="knowledge", importance=0.6)
    ltm.store("s1", "v", category="session",   importance=0.4)
    stats = ltm.stats()
    assert stats["total_entries"] == 3
    assert stats["by_category"]["knowledge"] == 2
    assert stats["by_category"]["session"]   == 1
    assert abs(stats["avg_importance"] - (0.8+0.6+0.4)/3) < 0.01
def test_t20_ltm_access_count():
    ltm = _make_ltm()
    eid = ltm.store("ac_test", "val")
    for _ in range(3):
        ltm.get(eid)
    entry = ltm.get(eid)
    assert entry.access_count == 4
# ════════════════════════════════════════════════════════════
#  T21 - T24  长期记忆检索
# ════════════════════════════════════════════════════════════

def test_t21_ltm_search():
    ltm = _make_ltm()
    ltm.store("武汉医院覆盖分析", {"result": "..."}, tags=["wuhan", "hospital"], importance=0.9)
    ltm.store("北京交通拥堵分析", {"result": "..."}, tags=["beijing", "traffic"], importance=0.7)
    ltm.store("武汉路网密度研究", {"result": "..."}, tags=["wuhan", "road"],     importance=0.6)

    results = ltm.search("武汉")
    titles  = [r.title for r in results]
    assert "武汉医院覆盖分析"  in titles
    assert "武汉路网密度研究"  in titles
    assert "北京交通拥堵分析" not in titles
def test_t22_ltm_search_by_tag():
    ltm = _make_ltm()
    ltm.store("A", {}, tags=["wuhan", "hospital"])
    ltm.store("B", {}, tags=["hospital", "beijing"])
    ltm.store("C", {}, tags=["road"])

    by_hospital = ltm.get_by_tag("hospital")
    assert len(by_hospital) == 2
    by_road = ltm.get_by_tag("road")
    assert len(by_road) == 1
def test_t23_ltm_get_recent():
    ltm = _make_ltm()
    for i in range(5):
        ltm.store(f"entry_{i}", i)
        time.sleep(0.01)
    recent = ltm.get_recent(n=3)
    assert len(recent) == 3
    # 最新的应该是 entry_4
    assert recent[0].title == "entry_4"
def test_t24_ltm_get_important():
    ltm = _make_ltm()
    ltm.store("low",  "v", importance=0.3)
    ltm.store("mid",  "v", importance=0.6)
    ltm.store("high", "v", importance=0.9)

    important = ltm.get_important(threshold=0.5)
    titles = [e.title for e in important]
    assert "high" in titles
    assert "mid"  in titles
    assert "low" not in titles
# ════════════════════════════════════════════════════════════
#  T25 - T27  短期→长期 flush
# ════════════════════════════════════════════════════════════

def test_t25_flush_from_session():
    stm = ShortTermMemory(session_id="flush_test")
    stm.store("layer_a", {"n": 200}, category="result")
    stm.log_operation("load",   "hospitals.geojson", duration=0.1)
    stm.log_operation("buffer", "layer_a, 1km",      duration=0.5)
    stm.log_operation("render", "output.png",         duration=0.3)

    ltm = _make_ltm()
    summary = stm.summarize()
    eid = ltm.flush_from_session(summary, title="测试会话复盘", tags=["test"])

    entry = ltm.get(eid)
    assert entry is not None
    assert entry.category == "session"
    assert "test" in entry.tags
    assert entry.content["operations"]["total"] == 3
    assert entry.content["operations"]["success"] == 3
def test_t26_flush_auto_importance():
    """操作越多 + 无错误 → 重要性越高。"""
    stm1 = ShortTermMemory()
    for i in range(10):
        stm1.log_operation(f"op_{i}", "x")

    stm2 = ShortTermMemory()
    stm2.log_operation("op_1", "x")
    stm2.log_operation("op_2", "x", success=False, error="err")

    ltm = _make_ltm()
    eid1 = ltm.flush_from_session(stm1.summarize(), title="many_ops")
    eid2 = ltm.flush_from_session(stm2.summarize(), title="few_with_err")

    e1 = ltm.get(eid1)
    e2 = ltm.get(eid2)
    assert e1.importance > e2.importance, \
        f"期望 {e1.importance} > {e2.importance}"
def test_t27_flush_includes_errors():
    stm = ShortTermMemory()
    stm.log_operation("ok",  "a")
    stm.log_operation("bad", "b", success=False, error="TimeoutError")
    ltm = _make_ltm()
    eid = ltm.flush_from_session(stm.summarize())
    entry = ltm.get(eid)
    assert entry.content["operations"]["failed"] == 1
    assert len(entry.content["errors"]) == 1
    assert entry.content["errors"][0]["error"] == "TimeoutError"
# ════════════════════════════════════════════════════════════
#  T28 - T31  MemoryManager
# ════════════════════════════════════════════════════════════

def _make_mgr() -> MemoryManager:
    tmp = tempfile.mkdtemp()
    return MemoryManager(memory_dir=Path(tmp), auto_flush=True)

def test_t28_mgr_session_lifecycle():
    mgr = _make_mgr()
    sid = mgr.start_session("lifecycle_test")
    assert mgr.current_session == "lifecycle_test"

    mgr.remember("buf", {"type": "layer"})
    mgr.log_op("buffer", "hospitals")
    assert mgr.recall_short("buf") == {"type": "layer"}

    eid = mgr.end_session(title="生命周期测试")
    assert eid is not None
    assert mgr.current_session is None
    assert mgr.recall_short("buf") is None  # 会话结束后短期记忆清空
def test_t29_mgr_learn_recall():
    mgr = _make_mgr()
    eid = mgr.learn(
        title="空间分析最佳实践",
        content={"tip": "使用 UTM 投影进行距离计算"},
        category="knowledge",
        tags=["best_practice", "projection"],
        importance=0.85,
    )
    assert eid is not None

    results = mgr.recall("UTM 投影")
    assert len(results) > 0
    assert any("空间分析" in r.title for r in results)
def test_t30_mgr_context():
    mgr = _make_mgr()
    mgr.start_session()
    mgr.set_context("project", "wuhan_v2")
    mgr.set_context("crs", "EPSG:32649")
    assert mgr.get_context("project") == "wuhan_v2"
    assert mgr.get_context("crs")     == "EPSG:32649"
    assert mgr.get_context("missing", "default") == "default"
def test_t31_mgr_status():
    mgr = _make_mgr()
    mgr.start_session("status_test")
    mgr.remember("k1", "v1")
    mgr.log_op("fn", "args")
    mgr.learn("知识A", "content")

    status = mgr.status()
    assert isinstance(status["short_term"], dict)
    assert status["short_term"]["entries"] == 1
    assert status["short_term"]["ops"]     == 1
    assert status["long_term"]["total_entries"] == 1
# ════════════════════════════════════════════════════════════
#  T32 - T34  全局单例
# ════════════════════════════════════════════════════════════

def test_t32_global_singleton():
    reset_memory()
    m1 = get_memory()
    m2 = get_memory()
    assert m1 is m2
def test_t33_global_reset():
    reset_memory()
    m1 = get_memory()
    reset_memory()
    m2 = get_memory()
    assert m1 is not m2
def test_t34_global_session():
    reset_memory()
    mem = get_memory()
    mem.start_session("global_test")
    mem.remember("global_key", 9999)
    assert get_memory().recall_short("global_key") == 9999
    get_memory().end_session(flush=False)
# ════════════════════════════════════════════════════════════
#  T35 - T36  与 GIS 操作集成
# ════════════════════════════════════════════════════════════

def test_t35_memory_with_geolayer():
    """将 GeoLayer 存入短期记忆，再取出使用。"""
    import geopandas as gpd
    from shapely.geometry import Point
    from geoclaw_claude.core.layer import GeoLayer
    from geoclaw_claude.analysis.spatial_ops import buffer

    stm = ShortTermMemory(session_id="gis_test")

    # 创建图层并存入短期记忆
    gdf = gpd.GeoDataFrame(
        {"name": ["A", "B", "C"]},
        geometry=[Point(114.3, 30.6), Point(114.4, 30.7), Point(114.5, 30.5)],
        crs="EPSG:4326",
    )
    layer = GeoLayer(gdf, name="test_pts")
    stm.store("input_layer", layer, category="result",
              metadata={"source": "test", "feature_count": len(layer)})
    stm.log_operation("load_layer", "test_pts", result_key="input_layer", duration=0.01)

    # 取出并执行 buffer 分析
    retrieved = stm.retrieve("input_layer")
    assert retrieved is not None
    assert len(retrieved) == 3

    t0     = time.time()
    result = buffer(retrieved, 500, unit="meters")
    dur    = time.time() - t0
    stm.store("buf_layer", result, category="result")
    stm.log_operation("buffer", "input_layer, 500m", result_key="buf_layer",
                      duration=dur, success=True)

    # 验证摘要
    summary = stm.summarize()
    assert summary["operations"]["total"]   == 2
    assert summary["operations"]["success"] == 2
    assert "input_layer" in summary["memory_store"]["keys"]
    assert "buf_layer"   in summary["memory_store"]["keys"]
def test_t36_full_workflow():
    """完整工作流：开始会话→分析→复盘→存入长期记忆→检索。"""
    import geopandas as gpd
    from shapely.geometry import Point
    from geoclaw_claude.core.layer import GeoLayer
    from geoclaw_claude.analysis.spatial_ops import buffer, nearest_neighbor

    mgr = _make_mgr()
    sid = mgr.start_session("full_workflow_test")

    # 设置上下文
    mgr.set_context("city", "wuhan")
    mgr.set_context("analysis_type", "hospital_coverage")

    # 模拟分析步骤
    gdf = gpd.GeoDataFrame(
        {"name": ["H1", "H2"]},
        geometry=[Point(114.3, 30.6), Point(114.5, 30.8)],
        crs="EPSG:4326",
    )
    hospitals = GeoLayer(gdf, name="hospitals")

    t0 = time.time()
    mgr.log_op("load_data", "hospitals.geojson")
    mgr.remember("hospitals", hospitals, category="result",
                 tags=["hospital", "wuhan"])

    buf = buffer(hospitals, 1000, unit="meters")
    mgr.log_op("buffer", "hospitals, 1000m", result_key="buf_hospitals",
               duration=time.time()-t0)
    mgr.remember("buf_hospitals", buf, category="result")

    # 存入领域知识
    mgr.learn(
        title="武汉医院1km覆盖分析",
        content={
            "hospital_count":  len(hospitals),
            "buffer_radius_m": 1000,
            "city":            "wuhan",
            "finding":         "2个医院在主城区",
        },
        tags=["wuhan", "hospital", "coverage"],
        importance=0.75,
    )

    # 结束会话，自动转入长期记忆
    eid = mgr.end_session(
        title="武汉医院覆盖分析复盘",
        tags=["wuhan", "hospital", "workflow"],
        importance=0.8,
    )
    assert eid is not None

    # 从长期记忆检索
    results = mgr.recall("武汉 医院")
    assert len(results) >= 1

    recent = mgr.recall_recent(n=5)
    assert len(recent) >= 1

    # 验证 session 条目内容
    session_entry = mgr.ltm.get_by_category("session")
    assert len(session_entry) >= 1
    assert session_entry[0].content["operations"]["total"] >= 2
# ════════════════════════════════════════════════════════════
#  T37  版本号
# ════════════════════════════════════════════════════════════

def test_t37_version():
    import geoclaw_claude
    assert geoclaw_claude.__version__ == "3.1.0", \
        f"期望 3.1.0，实际 {geoclaw_claude.__version__}"
    assert geoclaw_claude.__author__ == "UrbanComp Lab"
# ════════════════════════════════════════════════════════════
#  汇总
# ════════════════════════════════════════════════════════════
