# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools.fs_tools
------------------------------
文件系统工具：查找、读取、写入、目录列表。
"""

from __future__ import annotations

import os
import re
import glob
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import (
    ToolResult, ToolError, ToolPermission, ToolSpec,
    PATH_HARD_BLOCK_PREFIXES, HOME_CONFIG_HARD_BLOCK,
)


# ── 安全路径检查 ───────────────────────────────────────────────────────────────

def _expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


def _check_write_path(path: str, permission: ToolPermission) -> Path:
    """检查写入路径是否安全，返回解析后的绝对路径。"""
    resolved = _expand(path)
    path_str = str(resolved)

    # 硬性保护：系统路径
    for prefix in PATH_HARD_BLOCK_PREFIXES:
        if path_str.startswith(prefix):
            raise ToolError(
                f"禁止写入系统保护路径: {path_str}",
                tool="file_write", rule="system_path_hard_block"
            )

    # 硬性保护：home 目录配置文件
    home = str(Path.home())
    rel = path_str.replace(home + "/", "")
    for blocked in HOME_CONFIG_HARD_BLOCK:
        if rel.startswith(blocked) or rel == blocked.rstrip("/"):
            raise ToolError(
                f"禁止写入 shell/系统配置文件: {path_str}",
                tool="file_write", rule="home_config_hard_block"
            )

    return resolved


# ── 工具实现 ───────────────────────────────────────────────────────────────────

def tool_file_find(
    pattern:   str,
    root:      str = ".",
    recursive: bool = True,
    max_results: int = 200,
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    查找文件。支持 glob 模式（如 *.geojson）。

    Args:
        pattern    : 文件名模式，支持 * ? ** 通配符
        root       : 搜索根目录（默认当前目录）
        recursive  : 是否递归搜索子目录
        max_results: 最多返回结果数
    """
    t0 = time.time()
    try:
        root_path = _expand(root)
        if recursive:
            matches = list(root_path.rglob(pattern))[:max_results]
        else:
            matches = list(root_path.glob(pattern))[:max_results]

        result_list = [str(m) for m in matches]
        return ToolResult(
            tool="file_find",
            success=True,
            output="\n".join(result_list) if result_list else "(无匹配文件)",
            duration=time.time() - t0,
            metadata={"count": len(result_list), "root": str(root_path)},
        )
    except Exception as e:
        return ToolResult(tool="file_find", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_file_read(
    path:       str,
    encoding:   str = "utf-8",
    max_bytes:  int = 1_000_000,
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    读取文件内容。超过 max_bytes 时自动截断并提示。

    Args:
        path    : 文件路径（支持 ~ 和环境变量）
        encoding: 文本编码（默认 utf-8）
        max_bytes: 最大读取字节数
    """
    t0 = time.time()
    try:
        resolved = _expand(path)
        if not resolved.exists():
            raise ToolError(f"文件不存在: {resolved}", tool="file_read")
        if not resolved.is_file():
            raise ToolError(f"不是普通文件: {resolved}", tool="file_read")

        size = resolved.stat().st_size
        truncated = size > max_bytes

        with open(resolved, "r", encoding=encoding, errors="replace") as f:
            content = f.read(max_bytes)

        suffix = f"\n... [文件共 {size} 字节，已截断]" if truncated else ""
        return ToolResult(
            tool="file_read",
            success=True,
            output=content + suffix,
            duration=time.time() - t0,
            metadata={"path": str(resolved), "size": size, "truncated": truncated},
        )
    except ToolError:
        raise
    except Exception as e:
        return ToolResult(tool="file_read", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_file_write(
    path:       str,
    content:    str,
    append:     bool = False,
    encoding:   str = "utf-8",
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    写入文件。

    Args:
        path    : 目标路径（支持 ~ 和环境变量）
        content : 写入内容
        append  : True 则追加，False 则覆盖
        encoding: 文本编码
    """
    t0 = time.time()
    try:
        resolved = _check_write_path(path, permission)
        resolved.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with open(resolved, mode, encoding=encoding) as f:
            f.write(content)

        return ToolResult(
            tool="file_write",
            success=True,
            output=f"已{'追加' if append else '写入'} {len(content)} 字符 → {resolved}",
            duration=time.time() - t0,
            metadata={"path": str(resolved), "bytes": len(content.encode(encoding))},
        )
    except ToolError:
        raise
    except Exception as e:
        return ToolResult(tool="file_write", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_file_list(
    path:       str = ".",
    show_hidden: bool = False,
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    列出目录内容（ls 风格）。

    Args:
        path       : 目录路径
        show_hidden: 是否显示隐藏文件（以 . 开头）
    """
    t0 = time.time()
    try:
        resolved = _expand(path)
        if not resolved.exists():
            raise ToolError(f"路径不存在: {resolved}", tool="file_list")

        entries = sorted(resolved.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for e in entries:
            if not show_hidden and e.name.startswith("."):
                continue
            if e.is_dir():
                lines.append(f"  [DIR]  {e.name}/")
            else:
                sz = e.stat().st_size
                unit = "B"
                for u in ("KB", "MB", "GB"):
                    if sz >= 1024:
                        sz /= 1024
                        unit = u
                lines.append(f"  [FILE] {e.name}  ({sz:.1f}{unit})")

        return ToolResult(
            tool="file_list",
            success=True,
            output=f"目录: {resolved}\n" + ("\n".join(lines) if lines else "  (空目录)"),
            duration=time.time() - t0,
            metadata={"path": str(resolved), "count": len(lines)},
        )
    except ToolError:
        raise
    except Exception as e:
        return ToolResult(tool="file_list", success=False,
                          error=str(e), duration=time.time() - t0)


# ── 工具规格（供 LLM）────────────────────────────────────────────────────────

FS_TOOL_SPECS = [
    ToolSpec(
        name="file_find",
        description="按文件名模式（glob）在指定目录下查找文件",
        parameters={
            "type": "object",
            "properties": {
                "pattern":     {"type": "string", "description": "文件名模式，如 *.geojson"},
                "root":        {"type": "string", "description": "搜索根目录，默认 ."},
                "recursive":   {"type": "boolean", "description": "是否递归，默认 true"},
                "max_results": {"type": "integer", "description": "最多返回数量，默认 200"},
            },
            "required": ["pattern"],
        },
    ),
    ToolSpec(
        name="file_read",
        description="读取文件内容（文本）",
        parameters={
            "type": "object",
            "properties": {
                "path":      {"type": "string", "description": "文件路径"},
                "max_bytes": {"type": "integer", "description": "最大读取字节，默认 1000000"},
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="file_write",
        description="写入或追加文本到文件",
        parameters={
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "目标文件路径"},
                "content": {"type": "string", "description": "写入内容"},
                "append":  {"type": "boolean", "description": "true=追加，false=覆盖，默认 false"},
            },
            "required": ["path", "content"],
        },
    ),
    ToolSpec(
        name="file_list",
        description="列出目录内容（类似 ls）",
        parameters={
            "type": "object",
            "properties": {
                "path":        {"type": "string", "description": "目录路径，默认 ."},
                "show_hidden": {"type": "boolean", "description": "显示隐藏文件，默认 false"},
            },
            "required": [],
        },
    ),
]
