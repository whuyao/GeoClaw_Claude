"""
tests/test_nl.py
==================
GeoClaw-claude 自然语言操作系统完整测试
Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

测试覆盖:
  N01 - N04  NLProcessor 模块初始化与模式选择
  N05 - N14  规则引擎解析测试（10种核心操作）
  N15 - N17  ParsedIntent 数据类测试
  N18 - N19  GeoAgent 初始化与对话流程
  N20        版本号 v1.3.0 验证
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geoclaw_claude.nl import NLProcessor, ParsedIntent, NLExecutor, GeoAgent

results = []

def test(name, fn):
    try:
        fn()
        results.append(("OK", name))
        print(f"  ✓ {name}")
    except Exception as e:
        results.append(("FAIL", name, str(e), traceback.format_exc()))
        print(f"  ✗ {name}: {e}")

def proc():
    """创建规则模式解析器（不需要 API Key）"""
    return NLProcessor(use_ai=False, verbose=False)


# ════════════════════════════════════════════════════════════
#  N01 - N04  NLProcessor 初始化
# ════════════════════════════════════════════════════════════

def n01_proc_rule_mode():
    """强制规则模式初始化"""
    p = NLProcessor(use_ai=False)
    assert not p._use_ai
test("N01 NLProcessor 规则模式", n01_proc_rule_mode)


def n02_proc_auto_no_key():
    """无 API Key 时自动降级为规则模式"""
    p = NLProcessor(api_key="", use_ai=None)
    assert not p._use_ai
test("N02 NLProcessor 无Key自动降级", n02_proc_auto_no_key)


def n03_proc_ai_flag():
    """强制 AI 模式时 _use_ai=True（即使 key 可能无效）"""
    p = NLProcessor(api_key="fake_key", use_ai=True)
    assert p._use_ai
test("N03 NLProcessor 强制AI模式", n03_proc_ai_flag)


def n04_proc_empty_input():
    """空输入返回 unknown intent"""
    p  = proc()
    r  = p.parse("")
    assert r.action == "unknown"
    assert r.confidence == 0.0
test("N04 NLProcessor 空输入处理", n04_proc_empty_input)


# ════════════════════════════════════════════════════════════
#  N05 - N14  规则引擎解析（10 种操作）
# ════════════════════════════════════════════════════════════

def n05_parse_buffer():
    """缓冲区分析解析"""
    p = proc()
    r = p.parse("对医院做1公里缓冲区")
    assert r.action == "buffer", f"期望 buffer，实际 {r.action}"
    assert r.params["distance"] == 1000.0
    assert r.params["unit"] == "meters"
    assert "hospitals" in r.targets
    assert r.confidence >= 0.8
test("N05 buffer 解析", n05_parse_buffer)


def n06_parse_load():
    """加载文件解析"""
    p = proc()
    r = p.parse("加载 hospitals.geojson")
    assert r.action == "load", f"期望 load，实际 {r.action}"
    assert "hospitals.geojson" in r.params.get("path", "")
test("N06 load 解析", n06_parse_load)


def n07_parse_kde():
    """核密度分析解析"""
    p = proc()
    r = p.parse("对医院做核密度分析")
    assert r.action == "kde", f"期望 kde，实际 {r.action}"
    assert "bandwidth" in r.params
    assert "grid_size" in r.params
test("N07 kde 解析", n07_parse_kde)


def n08_parse_download():
    """下载 OSM 数据解析"""
    p = proc()
    r = p.parse("下载武汉市医院数据")
    assert r.action == "download_osm", f"期望 download_osm，实际 {r.action}"
    assert "hospital" in r.params.get("type", "")
test("N08 download_osm 解析", n08_parse_download)


def n09_parse_render():
    """制图/可视化解析"""
    p = proc()
    r = p.parse("可视化当前结果")
    assert r.action in ("render", "render_interactive"), f"期望 render，实际 {r.action}"
test("N09 render 解析", n09_parse_render)


def n10_parse_render_interactive():
    """交互地图解析"""
    p = proc()
    r = p.parse("用交互地图显示医院数据")
    assert r.action == "render_interactive", f"期望 render_interactive，实际 {r.action}"
test("N10 render_interactive 解析", n10_parse_render_interactive)


def n11_parse_coord_transform():
    """坐标转换解析"""
    p = proc()
    r = p.parse("把医院数据从 wgs84 转成 gcj02")
    assert r.action == "coord_transform", f"期望 coord_transform，实际 {r.action}"
    assert "from_crs" in r.params
    assert "to_crs" in r.params
test("N11 coord_transform 解析", n11_parse_coord_transform)


def n12_parse_isochrone():
    """等时圈解析"""
    p = proc()
    r = p.parse("以医院为中心做10分钟等时圈")
    assert r.action == "isochrone", f"期望 isochrone，实际 {r.action}"
    assert 10 in r.params.get("minutes", [])
test("N12 isochrone 解析", n12_parse_isochrone)


def n13_parse_pipeline():
    """多步流水线解析"""
    p = proc()
    r = p.parse("对医院做1公里缓冲区然后可视化")
    assert r.action == "pipeline", f"期望 pipeline，实际 {r.action}"
    assert len(r.steps) >= 2
    actions = [s.action for s in r.steps]
    assert "buffer" in actions, f"流水线缺少 buffer，实际: {actions}"
    assert "render" in actions or "render_interactive" in actions, \
        f"流水线缺少 render，实际: {actions}"
test("N13 pipeline 多步流水线", n13_parse_pipeline)


def n14_parse_help():
    """帮助命令解析"""
    p = proc()
    r = p.parse("帮助")
    assert r.action == "help"
    assert r.confidence >= 0.8
test("N14 help 解析", n14_parse_help)


# ════════════════════════════════════════════════════════════
#  N15 - N17  ParsedIntent 数据类
# ════════════════════════════════════════════════════════════

def n15_parsed_intent_fields():
    """ParsedIntent 字段完整性"""
    intent = ParsedIntent(
        action="buffer",
        params={"distance": 500, "unit": "meters"},
        targets=["hospitals"],
        confidence=0.9,
        raw_text="对医院做500米缓冲区",
        explanation="缓冲区分析",
    )
    assert intent.action == "buffer"
    assert intent.params["distance"] == 500
    assert not intent.is_multi_step()
test("N15 ParsedIntent 字段", n15_parsed_intent_fields)


def n16_parsed_intent_multistep():
    """ParsedIntent 多步检测"""
    step1 = ParsedIntent(action="buffer", params={}, targets=[])
    step2 = ParsedIntent(action="render", params={}, targets=[])
    pipeline = ParsedIntent(
        action="pipeline", params={}, targets=[],
        steps=[step1, step2]
    )
    assert pipeline.is_multi_step()
    assert len(pipeline.steps) == 2
test("N16 ParsedIntent 多步检测", n16_parsed_intent_multistep)


def n17_parsed_intent_to_dict():
    """ParsedIntent.to_dict() 序列化"""
    import json
    intent = ParsedIntent(
        action="kde",
        params={"bandwidth": 0.05, "grid_size": 100},
        targets=["hospitals"],
        confidence=0.88,
        explanation="核密度分析",
    )
    d = intent.to_dict()
    assert isinstance(d, dict)
    assert d["action"] == "kde"
    assert d["confidence"] == 0.88
    # 确保可以 JSON 序列化
    json_str = json.dumps(d, ensure_ascii=False)
    assert "kde" in json_str
test("N17 ParsedIntent.to_dict()", n17_parsed_intent_to_dict)


# ════════════════════════════════════════════════════════════
#  N18 - N19  GeoAgent 对话流程
# ════════════════════════════════════════════════════════════

def n18_agent_init():
    """GeoAgent 初始化（规则模式，不需要 API Key）"""
    agent = GeoAgent(use_ai=False, verbose=False)
    s = agent.status()
    assert s["mode"] == "规则"
    assert s["turns"] == 0
    assert isinstance(s["layers"], list)
    # 初始化时已加入欢迎消息
    assert len(agent._history) == 1
    assert agent._history[0].role == "agent"
test("N18 GeoAgent 初始化", n18_agent_init)


def n19_agent_chat_help():
    """GeoAgent 帮助问答不报错"""
    agent = GeoAgent(use_ai=False, verbose=False)
    reply = agent.chat("帮助")
    assert isinstance(reply, str) and len(reply) > 0
    # 帮助应该成功（不是错误消息）
    assert "✗" not in reply or "帮助" in reply
    assert agent.status()["turns"] == 1
test("N19 GeoAgent chat 帮助", n19_agent_chat_help)


# ════════════════════════════════════════════════════════════
#  N20  版本号验证
# ════════════════════════════════════════════════════════════

def n20_version():
    import geoclaw_claude
    assert geoclaw_claude.__version__ == "1.3.0", \
        f"期望 1.3.0，实际 {geoclaw_claude.__version__}"
test("N20 版本号 v1.3.0", n20_version)


# ════════════════════════════════════════════════════════════
#  汇总
# ════════════════════════════════════════════════════════════

ok   = [r for r in results if r[0] == "OK"]
fail = [r for r in results if r[0] == "FAIL"]

print(f"\n{'═'*52}")
print(f"  NL 模块测试: {len(ok)}/{len(results)} 通过")
print(f"  UrbanComp Lab — GeoClaw-claude v1.3.0")
print(f"{'═'*52}")

if fail:
    print("\n❌ 失败详情:")
    for r in fail:
        print(f"\n  ✗ {r[1]}")
        print(f"    {r[2]}")
        for line in r[3].strip().split("\n")[-4:]:
            print(f"    {line}")
else:
    print("\n✅ 全部通过！自然语言操作系统运行正常。\n")

if fail:
    sys.exit(1)
