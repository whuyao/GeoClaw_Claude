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

_passed = 0
_failed = 0
_errors = []

def test(name, fn):
    global _passed, _failed
    try:
        fn()
        _passed += 1
        print(f"  ✓ {name}")
    except Exception as e:
        _failed += 1
        _errors.append((name, e, traceback.format_exc()))
        print(f"  ✗ {name}: {e}")

print("=" * 56)
print("  GeoClaw-claude v2.3.0 新功能测试")
print("=" * 56)

# ══════════════════════════════════════════════════════════════
#  G01 - G10  Gemini LLM Provider
# ══════════════════════════════════════════════════════════════

print("\n─ Gemini LLM Provider ─")

def g01_provider_constants():
    from geoclaw_claude.nl.llm_provider import PROVIDER_GEMINI, DEFAULT_MODELS, GEMINI_MODELS
    assert PROVIDER_GEMINI == "gemini"
    assert "gemini" in DEFAULT_MODELS
    assert len(GEMINI_MODELS) >= 3
    assert "gemini-2.0-flash" in GEMINI_MODELS
test("G01 Gemini provider 常量", g01_provider_constants)

def g02_provider_config():
    from geoclaw_claude.nl.llm_provider import ProviderConfig, PROVIDER_GEMINI, DEFAULT_MODELS
    cfg = ProviderConfig(provider=PROVIDER_GEMINI, api_key="test_key")
    assert cfg.model == DEFAULT_MODELS[PROVIDER_GEMINI]
    assert cfg.is_valid
test("G02 Gemini ProviderConfig 默认模型", g02_provider_config)

def g03_provider_config_custom_model():
    from geoclaw_claude.nl.llm_provider import ProviderConfig, PROVIDER_GEMINI
    cfg = ProviderConfig(provider=PROVIDER_GEMINI, api_key="key", model="gemini-1.5-pro")
    assert cfg.model == "gemini-1.5-pro"
test("G03 Gemini ProviderConfig 自定义模型", g03_provider_config_custom_model)

def g04_provider_instantiate():
    from geoclaw_claude.nl.llm_provider import LLMProvider, ProviderConfig, PROVIDER_GEMINI
    cfg = ProviderConfig(provider=PROVIDER_GEMINI, api_key="fake_key_test")
    llm = LLMProvider(cfg)
    assert llm.provider_name == "gemini"
    assert llm.model_name == "gemini-2.0-flash"
test("G04 Gemini LLMProvider 实例化", g04_provider_instantiate)

def g05_config_gemini_fields():
    from geoclaw_claude.config import Config
    cfg = Config()
    assert hasattr(cfg, "gemini_api_key")
    assert hasattr(cfg, "gemini_model")
    assert cfg.gemini_model == "gemini-2.0-flash"
test("G05 Config 包含 Gemini 字段", g05_config_gemini_fields)

def g06_config_save_load_gemini():
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
test("G06 Gemini Key 持久化到配置文件", g06_config_save_load_gemini)

def g07_from_config_gemini_priority():
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
test("G07 Gemini 自动选择优先级（Anthropic 无 Key 时）", g07_from_config_gemini_priority)

def g08_forced_provider_gemini():
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
test("G08 强制指定 llm_provider=gemini", g08_forced_provider_gemini)

def g09_gemini_no_key_returns_none():
    from geoclaw_claude.nl.llm_provider import LLMProvider, PROVIDER_GEMINI
    import unittest.mock as mock
    fake_cfg = type("C", (), {
        "anthropic_api_key": "",
        "gemini_api_key":    "",
        "gemini_model":      "gemini-2.0-flash",
        "openai_api_key":    "",
        "openai_model":      "gpt-4o-mini",
        "openai_base_url":   "",
        "qwen_api_key":      "",
        "qwen_model":        "qwen-plus",
        "llm_provider":      "",
    })()
    with mock.patch("geoclaw_claude.config.Config") as MC:
        MC.load.return_value = fake_cfg
        llm = LLMProvider.from_config()
        assert llm is None
test("G09 无任何 Key 返回 None", g09_gemini_no_key_returns_none)

def g10_gemini_model_list():
    from geoclaw_claude.nl.llm_provider import GEMINI_MODELS
    assert "gemini-2.0-flash" in GEMINI_MODELS
    assert "gemini-1.5-pro" in GEMINI_MODELS
    assert "gemini-2.5-pro-preview-03-25" in GEMINI_MODELS
test("G10 Gemini 模型列表完整性", g10_gemini_model_list)

# ══════════════════════════════════════════════════════════════
#  A01 - A10  MemoryArchive
# ══════════════════════════════════════════════════════════════

print("\n─ MemoryArchive 存档系统 ─")

def _make_archive():
    tmp = tempfile.mkdtemp()
    from geoclaw_claude.memory.archive import MemoryArchive
    return MemoryArchive(Path(tmp)), tmp

def a01_create_archive():
    arc, tmp = _make_archive()
    try:
        assert len(arc) == 0
        assert repr(arc).startswith("MemoryArchive")
    finally:
        shutil.rmtree(tmp)
test("A01 MemoryArchive 初始化", a01_create_archive)

def a02_save_session():
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
test("A02 save_session 存档", a02_save_session)

def a03_load_archive():
    arc, tmp = _make_archive()
    try:
        entry = arc.save_session("测试存档", ops_log=[], summary="测试摘要")
        loaded = arc.load(entry.archive_id)
        assert loaded is not None
        assert loaded.title == "测试存档"
        assert loaded.summary == "测试摘要"
    finally:
        shutil.rmtree(tmp)
test("A03 load 加载完整存档", a03_load_archive)

def a04_list_archives():
    arc, tmp = _make_archive()
    try:
        for i in range(3):
            arc.save_session(f"存档 {i}", tags=["test"])
        entries = arc.list_archives(limit=10)
        assert len(entries) == 3
    finally:
        shutil.rmtree(tmp)
test("A04 list_archives 列出存档", a04_list_archives)

def a05_search_archive():
    arc, tmp = _make_archive()
    try:
        arc.save_session("武汉医院覆盖率", summary="医院缓冲区分析", tags=["wuhan"])
        arc.save_session("上海公园绿地", summary="公园KDE核密度", tags=["shanghai"])
        results = arc.search("武汉 医院")
        assert len(results) >= 1
        assert "武汉" in results[0].title or "武汉" in results[0].summary
    finally:
        shutil.rmtree(tmp)
test("A05 search 关键词搜索", a05_search_archive)

def a06_delete_archive():
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
test("A06 delete 删除存档", a06_delete_archive)

def a07_export_import():
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
test("A07 export/import 全量导出导入", a07_export_import)

def a08_auto_summary():
    arc, tmp = _make_archive()
    try:
        ops = [{"action": "load"}, {"action": "buffer"}, {"action": "kde"}]
        entry = arc.save_session("自动摘要测试", ops_log=ops)
        # 未提供 summary 时应自动生成
        assert entry.summary
        assert "load" in entry.summary or "buffer" in entry.summary
    finally:
        shutil.rmtree(tmp)
test("A08 自动生成摘要", a08_auto_summary)

def a09_archive_stats():
    arc, tmp = _make_archive()
    try:
        arc.save_session("统计测试")
        st = arc.stats()
        assert st["total"] == 1
        assert "size_human" in st
        assert "sources" in st
    finally:
        shutil.rmtree(tmp)
test("A09 stats 统计信息", a09_archive_stats)

def a10_archive_entry_date_str():
    from geoclaw_claude.memory.archive import ArchiveEntry
    entry = ArchiveEntry(
        archive_id="test123", title="日期测试",
        created_at=time.time(), source="session"
    )
    date_str = entry.date_str
    assert len(date_str) > 5
    assert "-" in date_str
test("A10 ArchiveEntry.date_str 格式", a10_archive_entry_date_str)

# ══════════════════════════════════════════════════════════════
#  V01 - V10  VectorSearch
# ══════════════════════════════════════════════════════════════

print("\n─ VectorSearch 向量检索 ─")

def _make_vs():
    tmp = tempfile.mkdtemp()
    from geoclaw_claude.memory.vector_search import VectorSearch
    return VectorSearch(Path(tmp), use_neural=False), tmp

def v01_init():
    vs, tmp = _make_vs()
    try:
        assert len(vs) == 0
        assert "tfidf" in vs.backend
    finally:
        shutil.rmtree(tmp)
test("V01 VectorSearch 初始化（TF-IDF 模式）", v01_init)

def v02_tokenize():
    from geoclaw_claude.memory.vector_search import tokenize
    tokens = tokenize("武汉市医院空间分析 wuhan hospital")
    assert "武" in tokens or "汉" in tokens  # 中文字符级分词
    assert "wuhan" in tokens
    assert "hospital" in tokens
test("V02 tokenize 中英文分词", v02_tokenize)

def v03_add_search():
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
test("V03 add + search 基础检索", v03_add_search)

def v04_relevance_ranking():
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
test("V04 相关度排序", v04_relevance_ranking)

def v05_empty_search():
    vs, tmp = _make_vs()
    try:
        results = vs.search("武汉")
        assert results == []
        vs.add("doc1", "武汉医院分析")
        results = vs.search("")
        assert results == []
    finally:
        shutil.rmtree(tmp)
test("V05 空索引/空查询返回空列表", v05_empty_search)

def v06_remove_doc():
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
test("V06 remove 删除文档", v06_remove_doc)

def v07_save_load():
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
test("V07 save/load 持久化", v07_save_load)

def v08_source_filter():
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
test("V08 source_filter 按来源过滤", v08_source_filter)

def v09_cosine_similarity():
    from geoclaw_claude.memory.vector_search import cosine_similarity
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert abs(cosine_similarity(v1, v2) - 1.0) < 1e-6
    assert abs(cosine_similarity(v1, v3) - 0.0) < 1e-6
    assert cosine_similarity([], []) == 0.0
test("V09 cosine_similarity 计算正确", v09_cosine_similarity)

def v10_stats():
    vs, tmp = _make_vs()
    try:
        vs.add("doc1", "测试文档")
        st = vs.stats()
        assert st["documents"] == 1
        assert st["vocab_size"] >= 1
        assert "backend" in st
    finally:
        shutil.rmtree(tmp)
test("V10 stats 统计信息", v10_stats)

# ══════════════════════════════════════════════════════════════
#  X01  版本号
# ══════════════════════════════════════════════════════════════

print("\n─ 版本验证 ─")

def x01_version():
    import geoclaw_claude
    assert geoclaw_claude.__version__ == "2.3.0", \
        f"期望 2.3.0，实际 {geoclaw_claude.__version__}"
test("X01 版本号 v2.3.0", x01_version)

# ══════════════════════════════════════════════════════════════
#  结果
# ══════════════════════════════════════════════════════════════

print("\n" + "═" * 56)
total = _passed + _failed
print(f"  v2.3.0 功能测试: {_passed}/{total} 通过")
print("═" * 56)
if _failed:
    print("\n❌ 失败详情:")
    for name, err, tb in _errors:
        print(f"  ✗ {name}")
        print(f"    {type(err).__name__}: {err}")
    sys.exit(1)
else:
    print("✅ 全部通过！Gemini + Archive + VectorSearch 功能正常。")
