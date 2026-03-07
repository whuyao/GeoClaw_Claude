"""
geoclaw_claude/updater.py
==========================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

自我检测与自动更新模块。

功能:
  - check()  : 检测 GitHub 最新版本，与本地版本对比，返回检测报告
  - update() : 拉取最新代码并自动安装（git pull + pip install）
  - changelog_diff(): 获取两个版本之间的 CHANGELOG 内容

检测源: https://github.com/whuyao/GeoClaw_Claude
  - 版本信息：读取 GitHub Raw 的 geoclaw_claude/__init__.py
  - CHANGELOG：读取 GitHub Raw 的 CHANGELOG.md

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass, field

# GitHub 仓库配置
GITHUB_REPO   = "whuyao/GeoClaw_Claude"
GITHUB_BRANCH = "main"
GITHUB_RAW    = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_API    = f"https://api.github.com/repos/{GITHUB_REPO}"

# 本地项目根目录（相对于本文件）
_PACKAGE_DIR  = Path(__file__).parent
_PROJECT_ROOT = _PACKAGE_DIR.parent


# ── 数据类 ───────────────────────────────────────────────────────────────────

@dataclass
class VersionInfo:
    """版本信息容器。"""
    major:  int
    minor:  int
    patch:  int
    raw:    str

    @classmethod
    def parse(cls, version_str: str) -> "VersionInfo":
        """解析 '1.2.3' 格式的版本字符串。"""
        v = version_str.strip().lstrip("v")
        parts = v.split(".")
        try:
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, IndexError):
            major = minor = patch = 0
        return cls(major=major, minor=minor, patch=patch, raw=v)

    def __lt__(self, other: "VersionInfo") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VersionInfo):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __le__(self, other: "VersionInfo") -> bool:
        return self < other or self == other

    def __str__(self) -> str:
        return self.raw


@dataclass
class CheckResult:
    """版本检测结果。"""
    local_version:    str
    remote_version:   str
    has_update:       bool
    is_ahead:         bool         = False   # 本地版本高于远程（开发状态）
    error:            Optional[str] = None
    check_time:       float        = field(default_factory=time.time)
    latest_commit:    str          = ""
    latest_message:   str          = ""

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if self.is_ahead:
            return "ahead"
        if self.has_update:
            return "outdated"
        return "up_to_date"

    def summary(self) -> str:
        if self.error:
            return f"检测失败: {self.error}"
        if self.is_ahead:
            return f"本地 v{self.local_version} 领先于远程 v{self.remote_version}（开发版本）"
        if self.has_update:
            return (f"发现新版本: v{self.local_version} → v{self.remote_version}\n"
                    f"  最新提交: {self.latest_message or '(未获取)'}\n"
                    f"  运行 `geoclaw-claude update` 可自动升级")
        return f"已是最新版本 v{self.local_version} ✓"


@dataclass
class UpdateResult:
    """更新操作结果。"""
    success:          bool
    previous_version: str
    current_version:  str
    steps:            list         = field(default_factory=list)
    error:            Optional[str] = None

    def summary(self) -> str:
        if not self.success:
            return f"更新失败: {self.error}"
        if self.previous_version == self.current_version:
            return f"已是最新版本 v{self.current_version}，无需更新"
        return (f"更新成功: v{self.previous_version} → v{self.current_version}\n" +
                "\n".join(f"  {s}" for s in self.steps))


# ── 核心函数 ─────────────────────────────────────────────────────────────────

def _fetch_url(url: str, timeout: int = 10) -> Tuple[int, str]:
    """
    用 urllib 获取 URL 内容（避免引入额外依赖）。
    返回 (status_code, text)。
    """
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"GeoClaw-claude/{_get_local_version()}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except urllib.error.URLError as e:
        return 0, str(e)
    except Exception as e:
        return 0, str(e)


def _get_local_version() -> str:
    """读取本地版本号。"""
    try:
        from geoclaw_claude import __version__
        return __version__
    except ImportError:
        # 直接读文件，避免循环导入
        init_file = _PACKAGE_DIR / "__init__.py"
        content   = init_file.read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        return m.group(1) if m else "0.0.0"


def _fetch_remote_version() -> Tuple[str, str, str]:
    """
    从 GitHub Raw 获取远程最新版本号和 commit 信息。
    返回 (version, commit_sha, commit_message)。
    """
    # 方法1: 读取 __init__.py 中的 __version__
    raw_url   = f"{GITHUB_RAW}/geoclaw_claude/__init__.py"
    status, content = _fetch_url(raw_url)

    version = "0.0.0"
    if status == 200:
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if m:
            version = m.group(1)

    # 方法2: 获取最新 commit 信息（GitHub API）
    commit_sha = commit_msg = ""
    api_url  = f"{GITHUB_API}/commits/{GITHUB_BRANCH}"
    api_status, api_content = _fetch_url(api_url)
    if api_status == 200:
        try:
            import json
            data       = json.loads(api_content)
            commit_sha = data.get("sha", "")[:7]
            commit_msg = data.get("commit", {}).get("message", "").split("\n")[0]
        except Exception:
            pass

    return version, commit_sha, commit_msg


def check(verbose: bool = True) -> CheckResult:
    """
    检测是否有可用更新。

    Args:
        verbose: 是否打印检测过程

    Returns:
        CheckResult 对象
    """
    if verbose:
        print("  [Check] 正在检测最新版本...")

    local_ver = _get_local_version()

    try:
        remote_ver, commit_sha, commit_msg = _fetch_remote_version()
    except Exception as e:
        return CheckResult(
            local_version=local_ver,
            remote_version="unknown",
            has_update=False,
            error=str(e),
        )

    local_v  = VersionInfo.parse(local_ver)
    remote_v = VersionInfo.parse(remote_ver)

    has_update = remote_v > local_v
    is_ahead   = local_v  > remote_v

    result = CheckResult(
        local_version=local_ver,
        remote_version=remote_ver,
        has_update=has_update,
        is_ahead=is_ahead,
        latest_commit=commit_sha,
        latest_message=commit_msg,
    )

    if verbose:
        print(f"  [Check] 本地版本: v{local_ver}")
        print(f"  [Check] 远程版本: v{remote_ver}")
        if commit_sha:
            print(f"  [Check] 最新提交: [{commit_sha}] {commit_msg}")
        print(f"  [Check] {result.summary()}")

    return result


def changelog_diff(from_version: str, to_version: str = "latest") -> str:
    """
    获取两个版本间的 CHANGELOG 内容。

    Args:
        from_version: 起始版本（不包含）
        to_version  : 目标版本（默认最新）

    Returns:
        CHANGELOG 文本片段
    """
    raw_url = f"{GITHUB_RAW}/CHANGELOG.md"
    status, content = _fetch_url(raw_url)

    if status != 200:
        return f"(无法获取 CHANGELOG: HTTP {status})"

    # 提取 from_version 之后的所有版本记录
    lines   = content.split("\n")
    result  = []
    capture = False

    from_v = VersionInfo.parse(from_version)

    for line in lines:
        # 检测版本标题行，如 "## v1.2.0 (2025-03-07)"
        m = re.match(r"^##\s+v?([\d.]+)", line)
        if m:
            section_v = VersionInfo.parse(m.group(1))
            if section_v > from_v:
                capture = True
            else:
                if capture:
                    break   # 已经过了所有新版本
                capture = False

        if capture:
            result.append(line)

    return "\n".join(result).strip() if result else f"(v{from_version} 之后无 CHANGELOG 记录)"


def update(
    verbose:    bool = True,
    run_tests:  bool = False,
    force:      bool = False,
) -> UpdateResult:
    """
    拉取最新代码并安装。

    步骤:
      1. 检测版本（若已最新且 force=False 则跳过）
      2. git pull origin main
      3. pip install -e . (或 pip install .)
      4. （可选）运行测试

    Args:
        verbose   : 是否打印更新过程
        run_tests : 更新后是否运行测试套件
        force     : 强制更新，即使已是最新版本

    Returns:
        UpdateResult 对象
    """
    prev_ver = _get_local_version()
    steps    = []

    def log(msg: str) -> None:
        steps.append(msg)
        if verbose:
            print(f"  [Update] {msg}")

    # ── Step 1: 版本检测 ──────────────────────────────────────────────────────
    check_result = check(verbose=verbose)

    if check_result.error:
        return UpdateResult(
            success=False,
            previous_version=prev_ver,
            current_version=prev_ver,
            error=f"版本检测失败: {check_result.error}",
        )

    if not check_result.has_update and not force:
        log(f"已是最新版本 v{prev_ver}，无需更新")
        return UpdateResult(
            success=True,
            previous_version=prev_ver,
            current_version=prev_ver,
            steps=steps,
        )

    if check_result.has_update:
        log(f"准备更新: v{prev_ver} → v{check_result.remote_version}")
    else:
        log(f"强制更新: 当前 v{prev_ver}（force=True）")

    # ── Step 2: 检测 git ──────────────────────────────────────────────────────
    git_dir = _PROJECT_ROOT / ".git"
    if not git_dir.exists():
        return UpdateResult(
            success=False,
            previous_version=prev_ver,
            current_version=prev_ver,
            error=(
                "未检测到 .git 目录。\n"
                "  请使用 git clone 安装本项目以支持自动更新:\n"
                "  git clone https://github.com/whuyao/GeoClaw_Claude.git\n"
                "  cd GeoClaw_Claude && pip install -e ."
            ),
        )

    # ── Step 3: git pull ──────────────────────────────────────────────────────
    log("执行 git pull origin main ...")
    pull_result = subprocess.run(
        ["git", "pull", "origin", GITHUB_BRANCH],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    if pull_result.returncode != 0:
        return UpdateResult(
            success=False,
            previous_version=prev_ver,
            current_version=prev_ver,
            steps=steps,
            error=f"git pull 失败:\n{pull_result.stderr}",
        )

    pull_out = pull_result.stdout.strip()
    log(f"git pull 完成: {pull_out.split(chr(10))[0]}")

    # ── Step 4: pip install ───────────────────────────────────────────────────
    setup_py  = _PROJECT_ROOT / "setup.py"
    pyproject = _PROJECT_ROOT / "pyproject.toml"

    if setup_py.exists() or pyproject.exists():
        log("重新安装依赖 (pip install -e .) ...")
        pip_result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".",
             "--break-system-packages", "-q"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if pip_result.returncode != 0:
            log(f"⚠ pip install 警告: {pip_result.stderr[:200]}")
        else:
            log("pip install 成功")
    else:
        log("(跳过 pip install：无 setup.py / pyproject.toml)")

    # ── Step 5: 读取新版本号 ──────────────────────────────────────────────────
    # 重新读取文件（避免 Python 模块缓存旧值）
    init_file  = _PACKAGE_DIR / "__init__.py"
    new_content = init_file.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', new_content)
    new_ver = m.group(1) if m else prev_ver

    log(f"版本已更新: v{prev_ver} → v{new_ver}")

    # ── Step 6: 打印 CHANGELOG ────────────────────────────────────────────────
    if new_ver != prev_ver:
        log("获取更新内容...")
        diff = changelog_diff(from_version=prev_ver)
        if diff and not diff.startswith("("):
            # 只打印前 20 行，避免刷屏
            diff_lines = diff.split("\n")[:20]
            if verbose:
                print("\n  ── 更新内容 " + "─"*36)
                for ln in diff_lines:
                    print(f"  {ln}")
                if len(diff.split('\n')) > 20:
                    print("  ... (更多内容见 CHANGELOG.md)")
                print("  " + "─"*46 + "\n")

    # ── Step 7: 可选测试 ──────────────────────────────────────────────────────
    if run_tests:
        log("运行测试套件...")
        test_file = _PROJECT_ROOT / "tests" / "test_memory.py"
        if test_file.exists():
            test_result = subprocess.run(
                [sys.executable, str(test_file)],
                cwd=_PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            if test_result.returncode == 0:
                log("✓ 测试全部通过")
            else:
                log(f"⚠ 测试有失败项:\n{test_result.stdout[-500:]}")
        else:
            log("(测试文件不存在，跳过)")

    return UpdateResult(
        success=True,
        previous_version=prev_ver,
        current_version=new_ver,
        steps=steps,
    )


def self_check() -> dict:
    """
    全面自我检测报告：版本 + 依赖 + 模块完整性 + 更新状态。

    Returns:
        dict: 检测报告
    """
    report = {
        "version":      {},
        "modules":      {},
        "dependencies": {},
        "update":       {},
        "git":          {},
    }

    # ── 版本信息 ───────────────────────────────────────────────────────────────
    local_ver = _get_local_version()
    report["version"]["local"] = local_ver
    report["version"]["repo"]  = GITHUB_REPO

    # ── 模块完整性检测 ─────────────────────────────────────────────────────────
    modules_to_check = [
        "geoclaw_claude",
        "geoclaw_claude.config",
        "geoclaw_claude.core.layer",
        "geoclaw_claude.core.project",
        "geoclaw_claude.analysis.spatial_ops",
        "geoclaw_claude.analysis.network",
        "geoclaw_claude.analysis.raster_ops",
        "geoclaw_claude.cartography.renderer",
        "geoclaw_claude.io.vector",
        "geoclaw_claude.io.osm",
        "geoclaw_claude.memory",
        "geoclaw_claude.memory.short_term",
        "geoclaw_claude.memory.long_term",
        "geoclaw_claude.memory.manager",
        "geoclaw_claude.utils.coord_transform",
        "geoclaw_claude.skill_manager",
        "geoclaw_claude.cli",
    ]
    ok_mods = fail_mods = 0
    for mod in modules_to_check:
        try:
            __import__(mod)
            report["modules"][mod] = "ok"
            ok_mods += 1
        except Exception as e:
            report["modules"][mod] = f"ERROR: {e}"
            fail_mods += 1
    report["modules"]["_summary"] = f"{ok_mods}/{ok_mods+fail_mods} 模块正常"

    # ── 依赖检测 ───────────────────────────────────────────────────────────────
    deps = {
        "geopandas":   "geopandas",
        "shapely":     "shapely",
        "pyproj":      "pyproj",
        "numpy":       "numpy",
        "pandas":      "pandas",
        "matplotlib":  "matplotlib",
        "rasterio":    "rasterio",
        "networkx":    "networkx",
        "scipy":       "scipy",
        "folium":      "folium",
        "click":       "click",
    }
    ok_deps = fail_deps = 0
    for name, pkg in deps.items():
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "?")
            report["dependencies"][name] = ver
            ok_deps += 1
        except ImportError:
            report["dependencies"][name] = "NOT INSTALLED"
            fail_deps += 1
    report["dependencies"]["_summary"] = f"{ok_deps}/{ok_deps+fail_deps} 依赖就绪"

    # ── git 状态 ───────────────────────────────────────────────────────────────
    git_dir = _PROJECT_ROOT / ".git"
    if git_dir.exists():
        try:
            git_log = subprocess.run(
                ["git", "log", "--oneline", "-3"],
                cwd=_PROJECT_ROOT, capture_output=True, text=True
            )
            git_status = subprocess.run(
                ["git", "status", "--short"],
                cwd=_PROJECT_ROOT, capture_output=True, text=True
            )
            report["git"]["available"]    = True
            report["git"]["recent_commits"] = git_log.stdout.strip().split("\n")
            report["git"]["dirty_files"]  = len(git_status.stdout.strip().split("\n")) if git_status.stdout.strip() else 0
        except Exception as e:
            report["git"]["available"] = False
            report["git"]["error"]     = str(e)
    else:
        report["git"]["available"] = False
        report["git"]["note"]      = "非 git 安装，无法使用自动更新"

    # ── 更新检测 ───────────────────────────────────────────────────────────────
    check_result = check(verbose=False)
    report["update"]["status"]         = check_result.status
    report["update"]["local_version"]  = check_result.local_version
    report["update"]["remote_version"] = check_result.remote_version
    report["update"]["has_update"]     = check_result.has_update
    report["update"]["summary"]        = check_result.summary()
    if check_result.latest_commit:
        report["update"]["latest_commit"]  = check_result.latest_commit
        report["update"]["latest_message"] = check_result.latest_message

    return report


def print_self_check(report: dict) -> None:
    """美化打印 self_check() 的报告。"""
    print("\n  ╔══ GeoClaw-claude 自我检测报告 ══════════════════════╗")

    # 版本
    v = report["version"]
    print(f"  ║ 版本       本地: v{v['local']}")

    # 更新状态
    u = report["update"]
    icons = {"up_to_date": "✓", "outdated": "↑", "ahead": "↑", "error": "?"}
    icon  = icons.get(u["status"], "?")
    print(f"  ║ 更新状态   {icon} {u['summary'].split(chr(10))[0]}")
    if u.get("latest_commit"):
        print(f"  ║            最新提交: [{u['latest_commit']}] {u.get('latest_message','')}")

    # 模块
    mod_summary = report["modules"].get("_summary", "")
    failed_mods = [k for k, v in report["modules"].items()
                   if k != "_summary" and v != "ok"]
    print(f"  ║ 模块完整性 {mod_summary}")
    for m in failed_mods:
        print(f"  ║             ✗ {m}")

    # 依赖
    dep_summary = report["dependencies"].get("_summary", "")
    missing_deps = [k for k, v in report["dependencies"].items()
                    if k != "_summary" and v == "NOT INSTALLED"]
    print(f"  ║ 依赖包     {dep_summary}")
    for d in missing_deps:
        print(f"  ║             ✗ {d} 未安装")

    # git
    g = report["git"]
    if g.get("available"):
        commits = g.get("recent_commits", [])
        print(f"  ║ Git        {commits[0] if commits else '(无提交)'}")
        dirty = g.get("dirty_files", 0)
        if dirty:
            print(f"  ║             {dirty} 个文件有未提交修改")
    else:
        print(f"  ║ Git        {g.get('note', '不可用')}")

    print(f"  ╚══════════════════════════════════════════════════════╝\n")
