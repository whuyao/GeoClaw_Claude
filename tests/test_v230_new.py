"""
tests/test_v230_new.py
=======================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

v2.3.0 新功能测试
  G01 - G10 : Gemini LLM Provider（接口 + 配置）
  A01 - A10 : MemoryArchive（存档系统）
  V01 - V10 : VectorSearch（向量检索）
  X01       : 版本号验证
"""

import sys, os, traceback, tempfile, shutil, time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 56)
print("  GeoClaw-claude v2.3.0 新功能测试")
print("=" * 56)

# ══════════════════════════════════════════════════════════════
#  G01 - G10  Gemini LLM Provider
# ══════════════════════════════════════════════════════════════

print("\n─ Gemini LLM Provider ─")

def test_g01_provider_constants():
    from geoclaw_claude.nl.llm_provider import PROVIDER_GEMINI, DEFAULT_MODELS, GEMINI_MODELS
    assert PROVIDER_GEMINI == "gemini"
    assert "gemini" in DEFAULT_MODELS
    assert len(GEMINI_MODELS) >= 3
    assert "gemini-2.0-flash" in GEMINI_MODELS
def test_g02_provider_config():
    from geoclaw_claude.nl.llm_provider import ProviderConfig, PROVIDER_GEMINI, DEFAULT_MODELS
    cfg = ProviderConfig(provider=PROVIDER_GEMINI, api_key="test_key")
    assert cfg.model == DEFAULT_MODELS[PROVIDER_GEMINI]
    assert cfg.is_valid
def test_g03_provider_config_custom_model():
    from geoclaw_claude.nl.llm_provider import ProviderConfig, PROVIDER_GEMINI
    cfg = ProviderConfig(provider=PROVIDER_GEMINI, api_key="key", model="gemini-1.5-pro")
    assert cfg.model == "gemini-1.5-pro"
def test_g04_provider_instantiate():
    from geoclaw_claude.nl.llm_provider import LLMProvider, ProviderConfig, PROVIDER_GEMINI
    cfg = ProviderConfig(provider=PROVIDER_GEMINI, api_key="fake_key_test")
    llm = LLMProvider(cfg)
    assert llm.provider_name == "gemini"
    assert llm.model_name == "gemini-2.0-flash"
def test_g05_config_gemini_fields():
    from geoclaw_claude.config import Config
    cfg = Config()
    assert hasattr(cfg, "gemini_api_key")
    assert hasattr(cfg, "gemini_model")
    assert cfg.gemini_model == "gemini-2.0-flash"
def test_g06_config_save_load_gemini():
    with tempfile.TemporaryDirectory() as tmp:
        from geoclaw_claude.config import Config
        cfg = Config()
        cfg.gemini_api_key = "AIzaFakeKey123"
        cfg.gemini_model   = "gemini-1.5-pro"
        import geoclaw_claude.config as _c
        orig = _c.CONFIG_FILE
        _c.CONFIG_FILE = Path(tmp) / "config.json"
        _c.CONFIG_DIR  = Path(tmp)
        cfg.save()
        cfg2 = Config.load()
        assert cfg2.gemini_api_key == "AIzaFakeKey123"
        assert cfg2.gemini_model   == "gemini-1.5-pro"
        _c.CONFIG_FILE = orig
def test_g07_from_config_gemini_priority():
    """Gemini 优先级在 Anthropic 之后（当 Anthropic 无 key 时选 Gemini）。"""
    from geoclaw_claude.nl.llm_provider import LLMProvider, PROVIDER_GEMINI
    import unittest.mock as mock
    fake_cfg = type("C", (), {
        "anthropic_api_key": "",
        "gemini_api_key":    "AIzaFakeKey",
        "gemini_model":      "gemini-2.0-flash",
        "openai_api_key":    "",
        "openai_model":      "gpt-4o-mini",
        "openai_base_url":   "",
        "qwen_api_key":      "",
        "qwen_model":        "qwen-plus",
        "llm_provider":      "",
    })()
    # Config 是在 from_config 内部动态 import 的，需要 patch geoclaw_claude.config.Config
    with mock.patch("geoclaw_claude.config.Config") as MC:
        MC.load.return_value = fake_cfg
        llm = LLMProvider.from_config()
        assert llm is not None
        assert llm.provider_name == PROVIDER_GEMINI
def test_g08_forced_provider_gemini():
    from geoclaw_claude.nl.llm_provider import LLMProvider, PROVIDER_GEMINI
    import unittest.mock as mock
    fake_cfg = type("C", (), {
        "anthropic_api_key": "sk-ant-xxx",
        "gemini_api_key":    "AIzaKey",
        "gemini_model":      "gemini-2.0-flash",
        "openai_api_key":    "",
        "openai_model":      "gpt-4o-mini",
        "openai_base_url":   "",
        "qwen_api_key":      "",
        "qwen_model":        "qwen-plus",
        "llm_provider":      "gemini",  # 强制 gemini
    })()
    with mock.patch("geoclaw_claude.config.Config") as MC:
        MC.load.return_value = fake_cfg
        llm = LLMProvider.from_config()
        assert llm.provider_name == PROVIDER_GEMINI
def test_g09_gemini_no_key_returns_none():
    """无任何有效 provider 时 from_config 返回 None"""
    from geoclaw_claude.nl.llm_provider import LLMProvider, ProviderConfig
    import unittest.mock as mock
    # Patch all ProviderConfig.is_valid to False to simulate no valid provider
    with mock.patch.object(ProviderConfig, "is_valid", new_callable=lambda: property(lambda self: False)):
        llm = LLMProvider.from_config()
    assert llm is None
def test_g10_gemini_model_list():
    from geoclaw_claude.nl.llm_provider import GEMINI_MODELS
    assert "gemini-2.0-flash" in GEMINI_MODELS
    assert "gemini-1.5-pro" in GEMINI_MODELS
    assert any("gemini-2.5" in m for m in GEMINI_MODELS), f"No gemini-2.5 model found in {GEMINI_MODELS}"
# ══════════════════════════════════════════════════════════════
#  A01 - A10  MemoryArchive
# ══════════════════════════════════════════════════════════════

print("\n─ MemoryArchive 存档系统 ─")

def _make_archive():
    tmp = tempfile.mkdtemp()
    from geoclaw_claude.memory.archive import MemoryArchive
    return MemoryArchive(Path(tmp)), tmp

def test_a01_create_archive():
    arc, tmp = _make_archive()
    try:
        assert len(arc) == 0
        assert repr(arc).startswith("MemoryArchive")
    finally:
        shutil.rmtree(tmp)
def test_a02_save_session():
    arc, tmp = _make_archive()
    try:
        entry = arc.save_session(
            title="武汉医院分析",
            ops_log=[{"action": "buffer", "detail": "hospitals 1km"}],
            summary="完成缓冲区分析",
            tags=["wuhan", "hospital"],
        )
        assert entry.archive_id
        assert entry.title == "武汉医院分析"
        assert entry.ops_count == 1
        assert len(arc) == 1
    finally:
        shutil.rmtree(tmp)
def test_a03_load_archive():
    arc, tmp = _make_archive()
    try:
        entry = arc.save_session("测试存档", ops_log=[], summary="测试摘要")
        loaded = arc.load(entry.archive_id)
        assert loaded is not None
        assert loaded.title == "测试存档"
        assert loaded.summary == "测试摘要"
    finally:
        shutil.rmtree(tmp)
def test_a04_list_archives():
    arc, tmp = _make_archive()
    try:
        for i in range(3):
            arc.save_session(f"存档 {i}", tags=["test"])
        entries = arc.list_archives(limit=10)
        assert len(entries) == 3
    finally:
        shutil.rmtree(tmp)
def test_a05_search_archive():
    arc, tmp = _make_archive()
    try:
        arc.save_session("武汉医院覆盖率", summary="医院缓冲区分析", tags=["wuhan"])
        arc.save_session("上海公园绿地", summary="公园KDE核密度", tags=["shanghai"])
        results = arc.search("武汉 医院")
        assert len(results) >= 1
        assert "武汉" in results[0].title or "武汉" in results[0].summary
    finally:
        shutil.rmtree(tmp)
def test_a06_delete_archive():
    arc, tmp = _make_archive()
    try:
        entry = arc.save_session("待删除")
        assert len(arc) == 1
        ok = arc.delete(entry.archive_id)
        assert ok
        assert len(arc) == 0
        assert arc.load(entry.archive_id) is None
    finally:
        shutil.rmtree(tmp)
def test_a07_export_import():
    arc1, tmp1 = _make_archive()
    arc2, tmp2 = _make_archive()
    try:
        arc1.save_session("导出测试", summary="测试导出功能")
        export_path = str(Path(tmp1) / "export.json")
        arc1.export(export_path)
        n = arc2.import_json(export_path)
        assert n == 1
        assert len(arc2) == 1
    finally:
        shutil.rmtree(tmp1); shutil.rmtree(tmp2)
def test_a08_auto_summary():
    arc, tmp = _make_archive()
    try:
        ops = [{"action": "load"}, {"action": "buffer"}, {"action": "kde"}]
        entry = arc.save_session("自动摘要测试", ops_log=ops)
        # 未提供 summary 时应自动生成
        assert entry.summary
        assert "load" in entry.summary or "buffer" in entry.summary
    finally:
        shutil.rmtree(tmp)
def test_a09_archive_stats():
    arc, tmp = _make_archive()
    try:
        arc.save_session("统计测试")
        st = arc.stats()
        assert st["total"] == 1
        assert "size_human" in st
        assert "sources" in st
    finally:
        shutil.rmtree(tmp)
def test_a10_archive_entry_date_str():
    from geoclaw_claude.memory.archive import ArchiveEntry
    entry = ArchiveEntry(
        archive_id="test123", title="日期测试",
        created_at=time.time(), source="session"
    )
    date_str = entry.date_str
    assert len(date_str) > 5
    assert "-" in date_str
# ══════════════════════════════════════════════════════════════
#  V01 - V10  VectorSearch
# ══════════════════════════════════════════════════════════════

print("\n─ VectorSearch 向量检索 ─")

def _make_vs():
    tmp = tempfile.mkdtemp()
    from geoclaw_claude.memory.vector_search import VectorSearch
    return VectorSearch(Path(tmp), use_neural=False), tmp

def test_v01_init():
    vs, tmp = _make_vs()
    try:
        assert len(vs) == 0
        assert "tfidf" in vs.backend
    finally:
        shutil.rmtree(tmp)
def test_v02_tokenize():
    from geoclaw_claude.memory.vector_search import tokenize
    tokens = tokenize("武汉市医院空间分析 wuhan hospital")
    assert "武" in tokens or "汉" in tokens  # 中文字符级分词
    assert "wuhan" in tokens
    assert "hospital" in tokens
def test_v03_add_search():
    vs, tmp = _make_vs()
    try:
        vs.add("doc1", "武汉市医院空间分布分析",
               title="武汉医院分析", tags=["wuhan", "hospital"])
        vs.add("doc2", "上海公园绿地核密度估计",
               title="上海公园", tags=["shanghai", "park"])
        results = vs.search("武汉医院", top_k=5)
        assert len(results) >= 1
        assert results[0].doc_id == "doc1"
        assert results[0].score > 0
    finally:
        shutil.rmtree(tmp)
def test_v04_relevance_ranking():
    vs, tmp = _make_vs()
    try:
        vs.add("doc1", "武汉市医院空间分析", title="武汉医院")
        vs.add("doc2", "武汉市公园绿地分析", title="武汉公园")
        vs.add("doc3", "上海市医院覆盖率", title="上海医院")
        results = vs.search("武汉医院")
        assert results[0].doc_id in ("doc1",)  # 最相关的应该排第一
        assert results[0].score >= results[-1].score
    finally:
        shutil.rmtree(tmp)
def test_v05_empty_search():
    vs, tmp = _make_vs()
    try:
        results = vs.search("武汉")
        assert results == []
        vs.add("doc1", "武汉医院分析")
        results = vs.search("")
        assert results == []
    finally:
        shutil.rmtree(tmp)
def test_v06_remove_doc():
    vs, tmp = _make_vs()
    try:
        vs.add("doc1", "武汉医院分析")
        vs.add("doc2", "上海公园分析")
        assert len(vs) == 2
        ok = vs.remove("doc1")
        assert ok
        assert len(vs) == 1
        results = vs.search("武汉医院")
        assert all(r.doc_id != "doc1" for r in results)
    finally:
        shutil.rmtree(tmp)
def test_v07_save_load():
    tmp = tempfile.mkdtemp()
    try:
        from geoclaw_claude.memory.vector_search import VectorSearch
        vs1 = VectorSearch(Path(tmp), use_neural=False)
        vs1.add("doc1", "武汉医院空间分析", title="武汉医院")
        vs1.save()

        vs2 = VectorSearch(Path(tmp), use_neural=False)
        ok = vs2.load()
        assert ok
        assert len(vs2) == 1
        results = vs2.search("武汉医院")
        assert len(results) >= 1
    finally:
        shutil.rmtree(tmp)
def test_v08_source_filter():
    vs, tmp = _make_vs()
    try:
        vs.add("doc1", "武汉医院", source="memory")
        vs.add("doc2", "武汉公园", source="archive")
        res_mem = vs.search("武汉", source_filter="memory")
        res_arc = vs.search("武汉", source_filter="archive")
        assert all(r.meta["source"] == "memory" for r in res_mem)
        assert all(r.meta["source"] == "archive" for r in res_arc)
    finally:
        shutil.rmtree(tmp)
def test_v09_cosine_similarity():
    from geoclaw_claude.memory.vector_search import cosine_similarity
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert abs(cosine_similarity(v1, v2) - 1.0) < 1e-6
    assert abs(cosine_similarity(v1, v3) - 0.0) < 1e-6
    assert cosine_similarity([], []) == 0.0
def test_v10_stats():
    vs, tmp = _make_vs()
    try:
        vs.add("doc1", "测试文档")
        st = vs.stats()
        assert st["documents"] == 1
        assert st["vocab_size"] >= 1
        assert "backend" in st
    finally:
        shutil.rmtree(tmp)
# ══════════════════════════════════════════════════════════════
#  X01  版本号
# ══════════════════════════════════════════════════════════════

print("\n─ 版本验证 ─")

def test_x01_version():
    import geoclaw_claude
    assert geoclaw_claude.__version__.startswith("3."), \
        f"期望 3.x，实际 {geoclaw_claude.__version__}"
# ══════════════════════════════════════════════════════════════
#  结果
# ══════════════════════════════════════════════════════════════

print("\n" + "═" * 56)