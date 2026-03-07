"""
tests/test_updater.py
======================
GeoClaw-claude Updater（自我检测 & 更新）完整测试
Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

测试覆盖:
  U01 - U04  VersionInfo 版本解析与比较
  U05 - U07  _fetch_url 基本网络请求
  U08 - U10  check() 版本检测
  U11 - U13  self_check() 全面检测
  U14 - U15  changelog_diff() 变更日志
  U16 - U18  update() 逻辑（mock git + pip）
  U19        CLI 命令导入验证
  U20        版本号 v2.3.0 验证
"""

import sys
import time
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch, MagicMock

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from geoclaw_claude.updater import (
    VersionInfo, CheckResult, UpdateResult,
    check, self_check, print_self_check, changelog_diff, update,
    _get_local_version, _fetch_url, _PROJECT_ROOT,
)

results = []

def test(name, fn):
    try:
        fn()
        results.append(("OK", name))
        print(f"  ✓ {name}")
    except Exception as e:
        results.append(("FAIL", name, str(e), traceback.format_exc()))
        print(f"  ✗ {name}: {e}")


# ════════════════════════════════════════════════════════════
#  U01 - U04  VersionInfo
# ════════════════════════════════════════════════════════════

def u01_version_parse():
    v = VersionInfo.parse("1.2.3")
    assert v.major == 1 and v.minor == 2 and v.patch == 3
    assert v.raw == "1.2.3"

    v2 = VersionInfo.parse("v2.2.0")
    assert v2.major == 2 and v2.minor == 2 and v2.patch == 0

    v3 = VersionInfo.parse("1.1")     # 只有两段
    assert v3.major == 1 and v3.minor == 1 and v3.patch == 0

    v4 = VersionInfo.parse("0.0.0")
    assert v4.major == 0
test("U01 VersionInfo.parse", u01_version_parse)


def u02_version_compare():
    v100 = VersionInfo.parse("1.0.0")
    v110 = VersionInfo.parse("1.1.0")
    v111 = VersionInfo.parse("1.1.1")
    v200 = VersionInfo.parse("2.0.0")

    assert v100 < v110
    assert v110 < v111
    assert v111 < v200
    assert not (v200 < v100)
    assert v100 == VersionInfo.parse("1.0.0")
    assert v110 <= v111
    assert not (v200 <= v100)
test("U02 VersionInfo 比较", u02_version_compare)


def u03_version_str():
    v = VersionInfo.parse("1.2.3")
    assert str(v) == "1.2.3"
test("U03 VersionInfo __str__", u03_version_str)


def u04_version_edge_cases():
    v_bad = VersionInfo.parse("not-a-version")
    assert v_bad.major == 0 and v_bad.minor == 0

    v_empty = VersionInfo.parse("")
    assert v_empty.major == 0
test("U04 VersionInfo 边界情况", u04_version_edge_cases)


# ════════════════════════════════════════════════════════════
#  U05 - U07  _fetch_url
# ════════════════════════════════════════════════════════════

def u05_fetch_url_success():
    """访问一个稳定的公共 URL。"""
    status, content = _fetch_url("https://httpbin.org/status/200", timeout=8)
    # httpbin 可能不可用，只要不抛异常即可
    assert isinstance(status, int)
    assert isinstance(content, str)
test("U05 _fetch_url 基本访问", u05_fetch_url_success)


def u06_fetch_url_404():
    status, content = _fetch_url(
        "https://raw.githubusercontent.com/whuyao/GeoClaw_Claude/main/NONEXISTENT_FILE_12345.py",
        timeout=8,
    )
    assert status == 404
test("U06 _fetch_url 404 处理", u06_fetch_url_404)


def u07_fetch_url_invalid():
    """无效域名应返回 status=0。"""
    status, content = _fetch_url(
        "https://this-domain-does-not-exist-geoclaw-12345.com/file.py",
        timeout=3,
    )
    assert status == 0
    assert isinstance(content, str)
test("U07 _fetch_url 无效域名", u07_fetch_url_invalid)


# ════════════════════════════════════════════════════════════
#  U08 - U10  check()
# ════════════════════════════════════════════════════════════

def u08_check_returns_result():
    """check() 必须返回 CheckResult，无论网络是否可用。"""
    result = check(verbose=False)
    assert isinstance(result, CheckResult)
    assert isinstance(result.local_version, str)
    assert isinstance(result.remote_version, str)
    assert isinstance(result.has_update, bool)
    assert result.status in ("up_to_date", "outdated", "ahead", "error")
test("U08 check() 返回 CheckResult", u08_check_returns_result)


def u09_check_local_version_correct():
    """check() 返回的 local_version 必须与 __init__.py 一致。"""
    import geoclaw_claude
    result = check(verbose=False)
    assert result.local_version == geoclaw_claude.__version__
test("U09 check() 本地版本正确", u09_check_local_version_correct)


def u10_check_summary_str():
    """CheckResult.summary() 必须返回非空字符串。"""
    result = check(verbose=False)
    s = result.summary()
    assert isinstance(s, str) and len(s) > 0
    # 必须包含版本号
    assert result.local_version in s or "失败" in s
test("U10 CheckResult.summary() 正常", u10_check_summary_str)


# ════════════════════════════════════════════════════════════
#  U11 - U13  self_check()
# ════════════════════════════════════════════════════════════

def u11_self_check_structure():
    """self_check() 报告结构完整。"""
    report = self_check()
    required_keys = ["version", "modules", "dependencies", "update", "git"]
    for k in required_keys:
        assert k in report, f"缺少 key: {k}"

    assert "local" in report["version"]
    assert "_summary" in report["modules"]
    assert "_summary" in report["dependencies"]
    assert "status" in report["update"]
    assert "available" in report["git"]
test("U11 self_check() 报告结构", u11_self_check_structure)


def u12_self_check_modules():
    """self_check() 应报告核心模块状态。"""
    report = self_check()
    mods = report["modules"]
    # 核心模块必须在报告中且为 ok
    core_mods = ["geoclaw_claude", "geoclaw_claude.memory", "geoclaw_claude.cli"]
    for m in core_mods:
        assert m in mods, f"报告中缺少模块: {m}"
        assert mods[m] == "ok", f"模块异常: {m} = {mods[m]}"
test("U12 self_check() 核心模块正常", u12_self_check_modules)


def u13_print_self_check_no_crash():
    """print_self_check() 不抛异常。"""
    import io
    report = self_check()
    # 重定向 stdout 避免测试输出混乱
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        print_self_check(report)
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout
    assert len(output) > 10
    assert "GeoClaw" in output
test("U13 print_self_check() 正常打印", u13_print_self_check_no_crash)


# ════════════════════════════════════════════════════════════
#  U14 - U15  changelog_diff()
# ════════════════════════════════════════════════════════════

def u14_changelog_diff_returns_str():
    """changelog_diff() 必须返回字符串，无论网络是否可用。"""
    result = changelog_diff("0.0.0")
    assert isinstance(result, str)
    # 有内容（非空 或 说明无法获取）
    assert len(result) > 0
test("U14 changelog_diff() 返回字符串", u14_changelog_diff_returns_str)


def u15_changelog_diff_filter():
    """changelog_diff() 对于高版本不应返回旧版本内容。"""
    # 传入一个非常高的版本，期望返回空或提示无更新
    result = changelog_diff("99.99.99")
    # 不应包含 v1.x 的内容
    assert "v1.0" not in result or "之后无" in result
test("U15 changelog_diff() 版本过滤", u15_changelog_diff_filter)


# ════════════════════════════════════════════════════════════
#  U16 - U18  update() 逻辑
# ════════════════════════════════════════════════════════════

def u16_update_no_git():
    """无 .git 目录时 update() 应返回失败（不崩溃）。"""
    # Mock _PROJECT_ROOT 到无 .git 的临时目录
    tmp = Path(tempfile.mkdtemp())
    with patch("geoclaw_claude.updater._PROJECT_ROOT", tmp):
        result = update(verbose=False, force=True)
    assert isinstance(result, UpdateResult)
    assert not result.success
    assert ".git" in result.error or "git" in result.error.lower()
test("U16 update() 无 .git 处理", u16_update_no_git)


def u17_update_already_latest():
    """已是最新版本时 update() 应返回成功（无需操作）。"""
    # Mock check() 返回无更新
    mock_check = MagicMock(return_value=CheckResult(
        local_version="99.99.99",
        remote_version="99.99.99",
        has_update=False,
    ))
    with patch("geoclaw_claude.updater.check", mock_check):
        result = update(verbose=False, force=False)
    assert result.success
    assert "最新" in result.summary() or result.previous_version == result.current_version
test("U17 update() 已是最新", u17_update_already_latest)


def u18_update_result_dataclass():
    """UpdateResult 数据类接口正常。"""
    r = UpdateResult(
        success=True,
        previous_version="1.0.0",
        current_version="1.1.0",
        steps=["step1", "step2"],
    )
    assert r.success
    assert "1.0.0" in r.summary()
    assert "1.1.0" in r.summary()

    r_fail = UpdateResult(
        success=False,
        previous_version="1.0.0",
        current_version="1.0.0",
        error="Network timeout",
    )
    assert not r_fail.success
    assert "失败" in r_fail.summary()
test("U18 UpdateResult 数据类", u18_update_result_dataclass)


# ════════════════════════════════════════════════════════════
#  U19  CLI 命令注册验证
# ════════════════════════════════════════════════════════════

def u19_cli_commands():
    """CLI 中应包含 check / update / self-check 命令。"""
    import subprocess

    # 通过 subprocess 调用，避免 CliRunner 与内部 cli 结构不兼容
    def run_cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "geoclaw_claude.cli"] + list(args),
            capture_output=True, text=True,
            cwd=str(_PROJECT_ROOT),
        )

    # 检查 --help 包含三个命令
    r = run_cli("--help")
    assert r.returncode == 0, f"main --help 失败: {r.stderr}"
    for cmd in ["check", "update", "self-check"]:
        assert cmd in r.stdout, f"CLI 缺少命令: {cmd}"

    # 各子命令 --help 不崩溃
    assert run_cli("check", "--help").returncode == 0
    assert run_cli("self-check", "--help").returncode == 0
    assert run_cli("update", "--help").returncode == 0
test("U19 CLI 命令注册", u19_cli_commands)


# ════════════════════════════════════════════════════════════
#  U20  版本号验证
# ════════════════════════════════════════════════════════════

def u20_version():
    import geoclaw_claude
    assert geoclaw_claude.__version__ == "2.3.0", \
        f"期望 2.3.0，实际 {geoclaw_claude.__version__}"
    assert geoclaw_claude.__author__ == "UrbanComp Lab"
    # updater 模块的版本读取应与 __init__ 一致
    assert _get_local_version() == "2.3.0"
test("U20 版本号 v2.3.0", u20_version)


# ════════════════════════════════════════════════════════════
#  汇总
# ════════════════════════════════════════════════════════════

ok   = [r for r in results if r[0] == "OK"]
fail = [r for r in results if r[0] == "FAIL"]

print(f"\n{'═'*52}")
print(f"  Updater 测试结果: {len(ok)}/{len(results)} 通过")
print(f"  UrbanComp Lab — GeoClaw-claude v2.3.0")
print(f"{'═'*52}")

if fail:
    print("\n❌ 失败详情:")
    for r in fail:
        print(f"\n  ✗ {r[1]}")
        print(f"    错误: {r[2]}")
        for line in r[3].strip().split("\n")[-4:]:
            print(f"    {line}")
else:
    print("\n✅ 全部通过！Updater 系统运行正常。\n")

if fail:
    sys.exit(1)
