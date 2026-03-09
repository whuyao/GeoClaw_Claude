# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools.sys_tools
--------------------------------
系统信息查询工具：进程列表、内存、磁盘、CPU 等只读信息。
这些工具是纯只读的，不修改任何系统状态。
"""

from __future__ import annotations

import time
from typing import Optional

from .base import ToolResult, ToolPermission, ToolSpec


# ── 工具实现 ───────────────────────────────────────────────────────────────────

def tool_sys_info(
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    获取系统概况：OS、Python、内存、CPU 核数。
    """
    t0 = time.time()
    try:
        import platform, sys, os
        lines = [
            f"OS      : {platform.system()} {platform.release()} ({platform.machine()})",
            f"Python  : {sys.version.split()[0]}",
            f"CPU     : {os.cpu_count()} 核",
        ]
        try:
            import psutil
            mem = psutil.virtual_memory()
            lines.append(f"内存    : 总计 {mem.total/1e9:.1f}GB | 已用 {mem.used/1e9:.1f}GB ({mem.percent:.0f}%)")
            disk = psutil.disk_usage("/")
            lines.append(f"磁盘(/): 总计 {disk.total/1e9:.1f}GB | 可用 {disk.free/1e9:.1f}GB")
            cpu_pct = psutil.cpu_percent(interval=0.2)
            lines.append(f"CPU使用: {cpu_pct:.1f}%")
        except ImportError:
            # psutil 不可用时降级
            try:
                import resource
                r = resource.getrusage(resource.RUSAGE_SELF)
                lines.append(f"进程内存(RSS): {r.ru_maxrss / 1024:.1f} MB（近似）")
            except Exception:
                lines.append("详细内存信息：需安装 psutil（pip install psutil）")

        return ToolResult(
            tool="sys_info",
            success=True,
            output="\n".join(lines),
            duration=time.time() - t0,
        )
    except Exception as e:
        return ToolResult(tool="sys_info", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_sys_processes(
    filter_name: Optional[str] = None,
    max_results: int = 50,
    permission:  ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    列出当前进程（类似 ps aux）。可按名称过滤。

    Args:
        filter_name: 按进程名过滤（包含匹配）
        max_results: 最多返回数量
    """
    t0 = time.time()
    try:
        try:
            import psutil
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
                try:
                    info = p.info
                    name = info["name"] or ""
                    if filter_name and filter_name.lower() not in name.lower():
                        continue
                    mem_mb = (info["memory_info"].rss / 1e6) if info["memory_info"] else 0
                    procs.append(
                        f"  PID {info['pid']:6d}  {name[:20]:20s}  "
                        f"{info['cpu_percent']:5.1f}% CPU  {mem_mb:7.1f}MB  {info['status']}"
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            procs = procs[:max_results]
            header = f"{'PID':>8}  {'名称':20}  {'CPU':>7}  {'内存':>9}  状态"
            output = header + "\n" + ("\n".join(procs) if procs else "  (无匹配进程)")
        except ImportError:
            # 降级到 shell ps
            import subprocess
            cmd = "ps aux"
            if filter_name:
                cmd += f" | grep {filter_name}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            output = result.stdout[:5000]

        return ToolResult(
            tool="sys_processes",
            success=True,
            output=output,
            duration=time.time() - t0,
            metadata={"filter": filter_name},
        )
    except Exception as e:
        return ToolResult(tool="sys_processes", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_sys_disk(
    path: str = "/",
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    查询指定路径的磁盘使用情况。

    Args:
        path: 要查询的路径（默认 /）
    """
    t0 = time.time()
    try:
        import shutil, os
        path_exp = os.path.expanduser(path)
        total, used, free = shutil.disk_usage(path_exp)
        output = (
            f"路径  : {path_exp}\n"
            f"总计  : {total/1e9:.2f} GB\n"
            f"已用  : {used/1e9:.2f} GB ({used/total*100:.1f}%)\n"
            f"可用  : {free/1e9:.2f} GB ({free/total*100:.1f}%)"
        )
        return ToolResult(
            tool="sys_disk",
            success=True,
            output=output,
            duration=time.time() - t0,
            metadata={"total_gb": round(total/1e9, 2),
                      "used_gb":  round(used/1e9, 2),
                      "free_gb":  round(free/1e9, 2)},
        )
    except Exception as e:
        return ToolResult(tool="sys_disk", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_sys_env(
    key:        Optional[str] = None,
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    查询环境变量。不指定 key 则列出所有（敏感值自动脱敏）。

    Args:
        key: 环境变量名（可选，不填则列出全部）
    """
    t0 = time.time()
    import os
    SENSITIVE_KEYS = {"PASSWORD", "SECRET", "TOKEN", "KEY", "AUTH", "CREDENTIAL",
                      "API_KEY", "PRIVATE", "ANTHROPIC", "OPENAI", "GEMINI", "QWEN"}

    def _mask(k: str, v: str) -> str:
        if any(s in k.upper() for s in SENSITIVE_KEYS):
            return v[:4] + "****" if len(v) > 4 else "****"
        return v

    try:
        if key:
            val = os.environ.get(key, "(未设置)")
            output = f"{key}={_mask(key, val)}"
        else:
            lines = []
            for k, v in sorted(os.environ.items()):
                lines.append(f"  {k}={_mask(k, v)}")
            output = "\n".join(lines[:100])
            if len(os.environ) > 100:
                output += f"\n... [共 {len(os.environ)} 个，已截断]"

        return ToolResult(
            tool="sys_env",
            success=True,
            output=output,
            duration=time.time() - t0,
        )
    except Exception as e:
        return ToolResult(tool="sys_env", success=False,
                          error=str(e), duration=time.time() - t0)


# ── 工具规格（供 LLM）────────────────────────────────────────────────────────

SYS_TOOL_SPECS = [
    ToolSpec(
        name="sys_info",
        description="获取系统概况：OS 版本、Python 版本、CPU、内存、磁盘",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolSpec(
        name="sys_processes",
        description="列出当前运行的进程（类似 ps aux），可按名称过滤",
        parameters={
            "type": "object",
            "properties": {
                "filter_name": {"type": "string", "description": "按进程名过滤（包含匹配）"},
                "max_results": {"type": "integer", "description": "最多返回数量，默认 50"},
            },
            "required": [],
        },
    ),
    ToolSpec(
        name="sys_disk",
        description="查询指定路径的磁盘使用情况",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要查询的路径，默认 /"},
            },
            "required": [],
        },
    ),
    ToolSpec(
        name="sys_env",
        description="查询环境变量（敏感值自动脱敏）",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "变量名（不填则列出全部）"},
            },
            "required": [],
        },
    ),
]
