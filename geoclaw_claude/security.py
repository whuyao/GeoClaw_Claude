"""
geoclaw_claude/security.py
============================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

安全机制 (SecurityGuard)

保护用户的输入文件不被意外覆盖或删除，并确保所有输出写入到
固定的安全输出目录中。

核心保护规则:
  1. 输出目录固定  : 所有写文件操作必须在 output_dir 下，禁止写入其他路径
  2. 输入文件保护  : data_dir、uploads 目录下的文件禁止被覆盖或删除
  3. 系统目录保护  : 禁止写入系统关键目录（/etc、/usr、/bin 等）
  4. 软链接保护    : 禁止通过软链接绕过路径检查
  5. 路径穿越防护  : 拒绝包含 .. 的路径（路径遍历攻击防护）

使用方式:
  - 主动检查: guard.check_write(path) → 抛出 SecurityError 或返回安全路径
  - 路径重定向: guard.safe_output_path(filename) → 自动放到 output_dir 下
  - 装饰器: @guard.protect_write → 自动拦截文件写入函数

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import os
import re
import functools
from pathlib import Path
from typing import Callable, List, Optional, Set, Union


# ── 自定义异常 ────────────────────────────────────────────────────────────────

class SecurityError(Exception):
    """安全违规错误。"""
    def __init__(self, msg: str, path: str = "", rule: str = ""):
        self.violated_path = path
        self.rule = rule
        super().__init__(msg)


# ── 系统保护目录（绝对禁止写入）────────────────────────────────────────────────

_SYSTEM_PROTECTED = [
    "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
    "/boot", "/proc", "/sys", "/dev", "/run",
    "/var/log", "/var/lib",
]

# 危险文件后缀（禁止输出）
_DANGEROUS_EXTENSIONS = {
    ".sh", ".bash", ".zsh", ".fish", ".py",  # 可执行脚本（禁止通过输出覆盖）
    ".exe", ".dll", ".so", ".dylib",          # 二进制
    ".bat", ".cmd", ".ps1",                   # Windows 脚本
}


# ── 安全守卫 ─────────────────────────────────────────────────────────────────

class SecurityGuard:
    """
    文件系统安全守卫。

    Usage::

        guard = SecurityGuard.from_config()

        # 检查写入路径（不合规则抛出 SecurityError）
        safe_path = guard.check_write("output/result.geojson")

        # 生成安全输出路径
        path = guard.safe_output_path("result.geojson")  # → output_dir/result.geojson

        # 检查是否为受保护的输入文件
        if guard.is_input_file("data/hospitals.geojson"):
            print("这是输入文件，不可覆盖")
    """

    def __init__(
        self,
        output_dir:    str,
        protected_dirs: List[str],
        verbose: bool = False,
    ):
        """
        Args:
            output_dir    : 允许写入的输出目录（绝对路径）
            protected_dirs: 受保护的输入目录列表（绝对路径）
            verbose       : 是否打印安全日志
        """
        self.output_dir     = Path(output_dir).resolve()
        self.protected_dirs = [Path(d).resolve() for d in protected_dirs]
        self.verbose        = verbose
        self._audit_log: List[dict] = []   # 操作审计日志

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── 工厂方法 ─────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, verbose: bool = False) -> "SecurityGuard":
        """从 geoclaw_claude.config.Config 读取目录配置。"""
        try:
            from geoclaw_claude.config import Config
            cfg = Config.load()
            output_dir = cfg.output_dir
            protected  = [cfg.data_dir]
        except Exception:
            output_dir = str(Path.home() / "geoclaw_output")
            protected  = [str(Path.home() / "geoclaw_data")]

        # 追加常见上传目录
        protected.extend([
            str(Path.home() / "uploads"),
            "/mnt/user-data/uploads",
            str(Path.cwd() / "data"),
        ])
        return cls(output_dir=output_dir, protected_dirs=protected, verbose=verbose)

    # ── 核心检查接口 ──────────────────────────────────────────────────────────

    def check_write(self, path: Union[str, Path]) -> Path:
        """
        检查路径是否可以安全写入。

        Returns:
            解析后的安全绝对路径

        Raises:
            SecurityError: 违反安全规则时抛出
        """
        path_str = str(path)
        resolved = self._resolve_path(path_str)

        # 规则 1: 路径穿越检测
        self._check_path_traversal(path_str)

        # 规则 2: 系统目录保护
        self._check_system_dirs(resolved)

        # 规则 3: 输入文件保护
        self._check_input_protection(resolved)

        # 规则 4: 软链接保护
        self._check_symlink(resolved)

        # 规则 5: 危险文件后缀（仅对非 output_dir 内的路径）
        if not self._is_under_output(resolved):
            self._check_dangerous_extension(resolved)

        # 规则 6: 必须在 output_dir 下（写操作）
        if not self._is_under_output(resolved):
            raise SecurityError(
                f"写入路径 '{path_str}' 不在允许的输出目录 '{self.output_dir}' 下。\n"
                f"请使用 guard.safe_output_path(filename) 获取安全路径。",
                path=path_str,
                rule="output_dir_restriction",
            )

        self._audit("write_allowed", str(resolved))
        return resolved

    def check_delete(self, path: Union[str, Path]) -> Path:
        """
        检查路径是否可以安全删除。

        Raises:
            SecurityError: 违反安全规则时抛出
        """
        path_str = str(path)
        resolved = self._resolve_path(path_str)

        self._check_path_traversal(path_str)
        self._check_system_dirs(resolved)
        self._check_input_protection(resolved)

        # 禁止删除 output_dir 本身
        if resolved == self.output_dir:
            raise SecurityError(
                f"禁止删除输出根目录 '{resolved}'。",
                path=path_str,
                rule="output_dir_protection",
            )

        self._audit("delete_allowed", str(resolved))
        return resolved

    def is_input_file(self, path: Union[str, Path]) -> bool:
        """判断路径是否是受保护的输入文件。"""
        try:
            resolved = self._resolve_path(str(path))
            return any(
                self._is_under(resolved, pd)
                for pd in self.protected_dirs
            )
        except Exception:
            return False

    # ── 安全路径生成 ──────────────────────────────────────────────────────────

    def safe_output_path(
        self,
        filename: str,
        subdir: str = "",
        auto_rename: bool = True,
    ) -> Path:
        """
        生成一个确保在 output_dir 下的安全输出路径。

        Args:
            filename   : 文件名（不含目录，或相对路径）
            subdir     : 在 output_dir 下的子目录（可选）
            auto_rename: 若文件已存在，自动添加序号避免覆盖

        Returns:
            安全的绝对路径（父目录已创建）
        """
        # 清理文件名，去掉任何目录部分
        clean_name = Path(filename).name
        # 过滤危险字符
        clean_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', clean_name)

        if subdir:
            target_dir = self.output_dir / subdir
        else:
            target_dir = self.output_dir

        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / clean_name

        # 自动重命名避免覆盖
        if auto_rename and target.exists():
            stem = target.stem
            suffix = target.suffix
            counter = 1
            while target.exists():
                target = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        return target

    def redirect_to_output(
        self, path: Union[str, Path], subdir: str = ""
    ) -> Path:
        """
        将任意路径重定向到 output_dir 下（仅取文件名）。
        用于自动修正用户输入的输出路径。
        """
        filename = Path(str(path)).name
        return self.safe_output_path(filename, subdir=subdir, auto_rename=False)

    # ── 装饰器 ────────────────────────────────────────────────────────────────

    def protect_write(self, path_arg: str = "path") -> Callable:
        """
        函数装饰器：自动检查并重定向写入路径。

        Usage::
            @guard.protect_write(path_arg="save_path")
            def save_layer(layer, save_path):
                ...  # save_path 会被自动重定向到 output_dir
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())

                # 从 kwargs 或 args 中找到路径参数
                if path_arg in kwargs:
                    original = kwargs[path_arg]
                    safe = self.redirect_to_output(original)
                    kwargs[path_arg] = str(safe)
                    if self.verbose:
                        print(f"  [安全] 路径重定向: {original} → {safe}")
                elif path_arg in params:
                    idx = params.index(path_arg)
                    if idx < len(args):
                        original = args[idx]
                        safe = self.redirect_to_output(original)
                        args = list(args)
                        args[idx] = str(safe)
                        if self.verbose:
                            print(f"  [安全] 路径重定向: {original} → {safe}")

                return func(*args, **kwargs)
            return wrapper
        return decorator

    # ── 审计日志 ──────────────────────────────────────────────────────────────

    def get_audit_log(self) -> List[dict]:
        """获取操作审计日志。"""
        return list(self._audit_log)

    def clear_audit_log(self) -> None:
        """清空审计日志。"""
        self._audit_log.clear()

    # ── 内部规则检查 ──────────────────────────────────────────────────────────

    def _resolve_path(self, path: str) -> Path:
        """解析路径为绝对路径（相对路径以 output_dir 为基准）。"""
        p = Path(path)
        if not p.is_absolute():
            p = self.output_dir / p
        return p.resolve()

    def _check_path_traversal(self, path: str) -> None:
        """检测路径穿越攻击（..）。"""
        # 规范化后再检查，避免 ./../../ 等变体
        norm = os.path.normpath(path)
        parts = norm.replace("\\", "/").split("/")
        if ".." in parts:
            raise SecurityError(
                f"路径 '{path}' 包含路径穿越序列 '..'，已拒绝。",
                path=path,
                rule="path_traversal",
            )

    def _check_system_dirs(self, resolved: Path) -> None:
        """检查是否试图写入系统保护目录。"""
        for sys_dir in _SYSTEM_PROTECTED:
            if str(resolved).startswith(sys_dir + "/") or str(resolved) == sys_dir:
                raise SecurityError(
                    f"禁止写入系统目录 '{sys_dir}'（路径: '{resolved}'）。",
                    path=str(resolved),
                    rule="system_dir_protection",
                )

    def _check_input_protection(self, resolved: Path) -> None:
        """检查是否试图覆盖/删除受保护的输入文件。"""
        for pd in self.protected_dirs:
            if self._is_under(resolved, pd):
                raise SecurityError(
                    f"路径 '{resolved}' 在受保护的输入目录 '{pd}' 下，\n"
                    f"禁止覆盖或删除输入文件。\n"
                    f"如需输出，请使用 guard.safe_output_path(filename)。",
                    path=str(resolved),
                    rule="input_file_protection",
                )

    def _check_symlink(self, resolved: Path) -> None:
        """检查软链接（防止通过软链接绕过路径检查）。"""
        check = resolved
        while check != check.parent:
            if check.is_symlink():
                raise SecurityError(
                    f"路径 '{resolved}' 包含软链接 '{check}'，\n"
                    f"为防止路径绕过，已拒绝写入。",
                    path=str(resolved),
                    rule="symlink_protection",
                )
            check = check.parent

    def _check_dangerous_extension(self, resolved: Path) -> None:
        """检查危险文件后缀。"""
        ext = resolved.suffix.lower()
        if ext in _DANGEROUS_EXTENSIONS:
            raise SecurityError(
                f"禁止输出文件后缀 '{ext}'（路径: '{resolved}'）。\n"
                f"可执行文件和脚本文件不能作为输出目标。",
                path=str(resolved),
                rule="dangerous_extension",
            )

    def _is_under(self, child: Path, parent: Path) -> bool:
        """判断 child 是否在 parent 目录下（包含 parent 本身）。"""
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    def _is_under_output(self, resolved: Path) -> bool:
        return self._is_under(resolved, self.output_dir)

    def _audit(self, action: str, path: str) -> None:
        import time
        self._audit_log.append({
            "time": time.time(),
            "action": action,
            "path": path,
        })
        if self.verbose:
            print(f"  [安全审计] {action}: {path}")


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_guard: Optional[SecurityGuard] = None


def get_guard(force_reload: bool = False) -> SecurityGuard:
    """获取全局 SecurityGuard 单例。"""
    global _guard
    if _guard is None or force_reload:
        _guard = SecurityGuard.from_config()
    return _guard


def check_write(path: Union[str, Path]) -> Path:
    """便捷函数：检查写入路径。"""
    return get_guard().check_write(path)


def safe_output_path(filename: str, subdir: str = "") -> Path:
    """便捷函数：生成安全输出路径。"""
    return get_guard().safe_output_path(filename, subdir=subdir)
