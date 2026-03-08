"""
tests/test_v230_features.py
============================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

v2.3.0 新功能测试
  F1 - F10 : 上下文压缩 (ContextCompressor)
  F11- F20 : 多 LLM Provider (LLMProvider)
  F21- F30 : 安全机制 (SecurityGuard)
  F31      : 版本号验证

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

import sys, os, traceback, tempfile, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 测试框架 ──────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
#  F1 - F10  上下文压缩 (ContextCompressor)
# ══════════════════════════════════════════════════════════════════════════════

def test_f01_token_estimate():
    from geoclaw_claude.nl.context_compress import estimate_tokens
    # 英文
    assert estimate_tokens("hello world") > 0
    # 中文（每字约2 token）
    zh = estimate_tokens("武汉市医院空间分析")
    en = estimate_tokens("wuhan hospital spatial analysis")
    assert zh > 0 and en > 0
    # 空字符串
    assert estimate_tokens("") == 0
def test_f02_messages_token_estimate():
    from geoclaw_claude.nl.context_compress import estimate_messages_tokens
    msgs = [
        {"role": "user",      "content": "对医院做1公里缓冲区"},
        {"role": "assistant", "content": "✓ 缓冲完成，200 个要素"},
    ]
    total = estimate_messages_tokens(msgs)
    assert total > 10, f"估算 token 应>10，实际 {total}"
def test_f03_compress_not_needed():
    from geoclaw_claude.nl.context_compress import ContextCompressor, CompressConfig
    compressor = ContextCompressor(CompressConfig(max_tokens=10000))
    msgs = [{"role": "user", "content": "你好"}]
    compressed, report = compressor.compress(msgs)
    assert report.level_applied == 0
    assert len(compressed) == len(msgs)
def test_f04_compress_level1_summary():
    from geoclaw_claude.nl.context_compress import ContextCompressor, CompressConfig
    # 生成足够多消息触发 Level 1
    msgs = []
    for i in range(20):
        msgs.append({"role": "user",      "content": f"操作 {i}: 对图层{i}做缓冲区分析，半径500米"})
        msgs.append({"role": "assistant", "content": f"✓ 完成缓冲，{i*10}个要素"})

    cfg = CompressConfig(max_tokens=100, target_tokens=50,
                         keep_recent=4, enable_level2=False, enable_level3=False)
    compressor = ContextCompressor(cfg)
    compressed, report = compressor.compress(msgs)

    assert report.level_applied >= 1, f"应触发 Level 1，实际 {report.level_applied}"
    assert len(compressed) < len(msgs), "压缩后消息数应减少"
    assert report.summary_injected, "应注入摘要消息"
def test_f05_compress_level2_dedup():
    from geoclaw_claude.nl.context_compress import ContextCompressor, CompressConfig
    msgs = [
        {"role": "user",      "content": "对医院做缓冲区"},
        {"role": "user",      "content": "对医院做缓冲区"},   # 重复
        {"role": "assistant", "content": "✓ 完成"},
        {"role": "user",      "content": "对医院做缓冲区"},   # 又重复
        {"role": "assistant", "content": "✓ 再次完成"},
    ]
    cfg = CompressConfig(max_tokens=10, target_tokens=5,
                         enable_level1=False, enable_level3=False)
    compressor = ContextCompressor(cfg)
    compressed, report = compressor.compress(msgs)
    assert report.level_applied >= 2
def test_f06_compress_level3_truncate():
    from geoclaw_claude.nl.context_compress import ContextCompressor, CompressConfig
    msgs = [{"role": "user", "content": f"消息{i} " * 10} for i in range(30)]
    cfg = CompressConfig(max_tokens=10, target_tokens=5,
                         keep_recent=4, keep_hard_limit=3,
                         enable_level1=False, enable_level2=False)
    compressor = ContextCompressor(cfg)
    compressed, report = compressor.compress(msgs)
    assert report.level_applied == 3
    # 保留 3 条 + 1 条截断提示
    assert len(compressed) == 4, f"期望4条（3+notice），实际{len(compressed)}"
def test_f07_compress_ratio():
    from geoclaw_claude.nl.context_compress import CompressResult
    r = CompressResult(
        original_tokens=8000, compressed_tokens=3200,
        level_applied=1, messages_before=20, messages_after=8
    )
    assert abs(r.ratio - 0.4) < 0.01
    assert "Level 1" in str(r)
def test_f08_compress_convenience_fn():
    from geoclaw_claude.nl.context_compress import compress_if_needed
    msgs = [{"role": "user", "content": "hello"}]
    compressed, report = compress_if_needed(msgs)
    assert isinstance(report.level_applied, int)
    assert compressed is not None
def test_f09_compress_local_summary_content():
    from geoclaw_claude.nl.context_compress import ContextCompressor
    compressor = ContextCompressor()
    msgs = [
        {"role": "user",      "content": "加载医院数据"},
        {"role": "assistant", "content": "✓ 加载完成 200 个要素"},
        {"role": "user",      "content": "做1公里缓冲区"},
        {"role": "assistant", "content": "✗ 失败：CRS 未设置"},
    ]
    summary = compressor._make_local_summary(msgs)
    assert len(summary) > 0
    assert len(summary) <= compressor.config.summary_max_len + 20  # 留余量
def test_f10_compress_similarity():
    from geoclaw_claude.nl.context_compress import ContextCompressor
    c = ContextCompressor()
    assert c._similarity("hello world", "hello world") > 0.9
    assert c._similarity("apple", "banana") < 0.5
    assert c._similarity("", "") == 0.0
# ══════════════════════════════════════════════════════════════════════════════
#  F11 - F20  多 LLM Provider
# ══════════════════════════════════════════════════════════════════════════════

def test_f11_provider_config_anthropic():
    from geoclaw_claude.nl.llm_provider import ProviderConfig, PROVIDER_ANTHROPIC
    cfg = ProviderConfig(provider=PROVIDER_ANTHROPIC, api_key="sk-test-123", model="claude-test")
    assert cfg.provider == PROVIDER_ANTHROPIC
    assert cfg.model == "claude-test"
    assert cfg.is_valid
def test_f12_provider_config_qwen_default_url():
    from geoclaw_claude.nl.llm_provider import ProviderConfig, PROVIDER_QWEN, QWEN_BASE_URL
    cfg = ProviderConfig(provider=PROVIDER_QWEN, api_key="sk-qwen")
    assert cfg.base_url == QWEN_BASE_URL
    assert cfg.model == "qwen3-235b-a22b"  # 默认模型（v3.1.0 更新为 Qwen3 旗舰）
def test_f13_provider_config_invalid():
    from geoclaw_claude.nl.llm_provider import ProviderConfig, PROVIDER_OPENAI
    cfg = ProviderConfig(provider=PROVIDER_OPENAI, api_key="")  # 无 key
    assert not cfg.is_valid
def test_f14_provider_default_models():
    from geoclaw_claude.nl.llm_provider import DEFAULT_MODELS, PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_QWEN
    assert PROVIDER_ANTHROPIC in DEFAULT_MODELS
    assert PROVIDER_OPENAI    in DEFAULT_MODELS
    assert PROVIDER_QWEN      in DEFAULT_MODELS
    assert DEFAULT_MODELS[PROVIDER_QWEN].startswith("qwen")
def test_f15_llm_provider_from_config_no_key():
    from geoclaw_claude.nl.llm_provider import LLMProvider
    # 无 API Key 时应返回 None（配置文件默认无 key）
    result = LLMProvider.from_config()
    # 两种情况都可以：有 key 返回实例，无 key 返回 None
    assert result is None or hasattr(result, "chat")
def test_f16_llm_provider_chat_invalid_provider():
    from geoclaw_claude.nl.llm_provider import LLMProvider, ProviderConfig
    cfg = ProviderConfig(provider="unknown_provider", api_key="test")
    provider = LLMProvider(cfg)
    resp = provider.chat([{"role": "user", "content": "test"}])
    assert resp is None  # 未知 provider 应返回 None
def test_f17_clean_json_response():
    from geoclaw_claude.nl.llm_provider import clean_json_response
    raw = '```json\n{"action": "buffer"}\n```'
    cleaned = clean_json_response(raw)
    assert cleaned == '{"action": "buffer"}'
def test_f18_parse_json_response_valid():
    from geoclaw_claude.nl.llm_provider import parse_json_response
    result = parse_json_response('{"action": "buffer", "confidence": 0.9}')
    assert result is not None
    assert result["action"] == "buffer"
def test_f19_parse_json_response_invalid():
    from geoclaw_claude.nl.llm_provider import parse_json_response
    result = parse_json_response("这不是 JSON")
    assert result is None
def test_f20_llm_response_bool():
    from geoclaw_claude.nl.llm_provider import LLMResponse
    r1 = LLMResponse(content="hello", provider="test", model="test")
    r2 = LLMResponse(content="", provider="test", model="test")
    assert bool(r1)
    assert not bool(r2)
# ══════════════════════════════════════════════════════════════════════════════
#  F21 - F30  安全机制 (SecurityGuard)
# ══════════════════════════════════════════════════════════════════════════════

def _make_guard():
    """创建测试用 SecurityGuard（临时目录）。"""
    from geoclaw_claude.security import SecurityGuard
    tmp = tempfile.mkdtemp()
    output_dir   = os.path.join(tmp, "output")
    protected_in = os.path.join(tmp, "input_data")
    os.makedirs(output_dir,   exist_ok=True)
    os.makedirs(protected_in, exist_ok=True)
    guard = SecurityGuard(output_dir=output_dir, protected_dirs=[protected_in])
    return guard, tmp, output_dir, protected_in

def test_f21_safe_output_path_basic():
    guard, tmp, out, inp = _make_guard()
    try:
        p = guard.safe_output_path("result.geojson")
        assert str(p).startswith(out)
        assert p.name == "result.geojson"
    finally:
        shutil.rmtree(tmp)
def test_f22_safe_output_path_auto_rename():
    guard, tmp, out, inp = _make_guard()
    try:
        # 创建同名文件
        Path(out, "result.geojson").write_text("x")
        p1 = guard.safe_output_path("result.geojson")
        assert p1.name == "result_1.geojson"  # 自动加序号
        # 再创建
        p1.write_text("x")
        p2 = guard.safe_output_path("result.geojson")
        assert p2.name == "result_2.geojson"
    finally:
        shutil.rmtree(tmp)
def test_f23_check_write_blocks_input():
    from geoclaw_claude.security import SecurityError
    guard, tmp, out, inp = _make_guard()
    try:
        # 尝试写入 input 目录下的文件
        target = os.path.join(inp, "hospitals.geojson")
        try:
            guard.check_write(target)
            assert False, "应抛出 SecurityError"
        except SecurityError as e:
            assert e.rule == "input_file_protection"
    finally:
        shutil.rmtree(tmp)
def test_f24_check_write_allows_output():
    guard, tmp, out, inp = _make_guard()
    try:
        target = os.path.join(out, "result.geojson")
        safe = guard.check_write(target)
        assert str(safe).startswith(out)
    finally:
        shutil.rmtree(tmp)
def test_f25_check_write_blocks_system():
    from geoclaw_claude.security import SecurityError
    guard, tmp, out, inp = _make_guard()
    try:
        try:
            guard.check_write("/etc/passwd")
            assert False, "应抛出 SecurityError"
        except SecurityError as e:
            assert e.rule == "system_dir_protection"
    finally:
        shutil.rmtree(tmp)
def test_f26_check_write_blocks_path_traversal():
    from geoclaw_claude.security import SecurityError
    guard, tmp, out, inp = _make_guard()
    try:
        try:
            guard.check_write("../../../etc/passwd")
            assert False, "应抛出 SecurityError"
        except SecurityError as e:
            assert e.rule == "path_traversal"
    finally:
        shutil.rmtree(tmp)
def test_f27_check_delete_blocks_input():
    from geoclaw_claude.security import SecurityError
    guard, tmp, out, inp = _make_guard()
    try:
        target = os.path.join(inp, "data.geojson")
        try:
            guard.check_delete(target)
            assert False, "应抛出 SecurityError"
        except SecurityError as e:
            assert e.rule == "input_file_protection"
    finally:
        shutil.rmtree(tmp)
def test_f28_check_delete_blocks_output_root():
    from geoclaw_claude.security import SecurityError
    guard, tmp, out, inp = _make_guard()
    try:
        try:
            guard.check_delete(out)  # 尝试删除 output_dir 本身
            assert False, "应抛出 SecurityError"
        except SecurityError as e:
            assert e.rule == "output_dir_protection"
    finally:
        shutil.rmtree(tmp)
def test_f29_is_input_file():
    guard, tmp, out, inp = _make_guard()
    try:
        assert guard.is_input_file(os.path.join(inp, "test.geojson"))
        assert not guard.is_input_file(os.path.join(out, "result.geojson"))
    finally:
        shutil.rmtree(tmp)
def test_f30_redirect_to_output():
    guard, tmp, out, inp = _make_guard()
    try:
        # 将绝对路径重定向到 output_dir
        redirected = guard.redirect_to_output("/some/deep/path/result.geojson")
        assert str(redirected).startswith(out)
        assert redirected.name == "result.geojson"
    finally:
        shutil.rmtree(tmp)
# ══════════════════════════════════════════════════════════════════════════════
#  F31  版本号验证
# ══════════════════════════════════════════════════════════════════════════════

def test_f31_version():
    import geoclaw_claude
    assert geoclaw_claude.__version__.startswith("3."), \
        f"期望 3.x，实际 {geoclaw_claude.__version__}"
# ══════════════════════════════════════════════════════════════════════════════
#  F32  NLProcessor 集成新 provider 参数
# ══════════════════════════════════════════════════════════════════════════════

def test_f32_nlprocessor_provider_param():
    from geoclaw_claude.nl import NLProcessor
    # 规则模式：provider 参数不影响规则解析
    proc = NLProcessor(use_ai=False, provider="qwen")
    assert not proc._use_ai
    intent = proc.parse("对医院做500米缓冲区")
    assert intent.action != "unknown"
# ══════════════════════════════════════════════════════════════════════════════
#  F33  SecurityGuard from_config
# ══════════════════════════════════════════════════════════════════════════════

def test_f33_guard_from_config():
    from geoclaw_claude.security import get_guard, SecurityGuard
    guard = get_guard(force_reload=True)
    assert isinstance(guard, SecurityGuard)
    assert guard.output_dir.exists()
# ── 结果统计 ──────────────────────────────────────────────────────────────────
