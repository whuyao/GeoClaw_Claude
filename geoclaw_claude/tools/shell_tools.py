# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools.shell_tools
---------------------------------
Shell 命令执行工具。

权限层级
--------
- 硬性保护（任何模式都拦截）: rm -rf、mkfs、dd、fork bomb、远程代码管道等
- SANDBOX 拦截: sudo、systemctl、crontab、ssh、nmap 等
- FULL: 只受硬性保护限制，其余放行

超时
----
默认 30 秒，最长 300 秒，防止挂死。
"""

from __future__ import annotations

import re
import subprocess
import time
from typing import List, Optional

from .base import (
    ToolResult, ToolError, ToolPermission, ToolSpec,
    SHELL_HARD_BLOCK_PATTERNS, SANDBOX_BLOCK_KEYWORDS,
    HOME_CONFIG_HARD_BLOCK, PATH_HARD_BLOCK_PREFIXES,
)


# ── 安全检查 ──────────────────────────────────────────────────────────────────

def _check_cmd(cmd: str, permission: ToolPermission) -> None:
    """检查命令是否安全，不通过则抛出 ToolError。"""
    # 1. 硬性保护（所有模式）
    for pattern in SHELL_HARD_BLOCK_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            raise ToolError(
                f"命令被安全策略拒绝（硬性保护）: {cmd[:80]}",
                tool="shell", rule=f"hard_block:{pattern}"
            )

    # 硬性保护：不允许写入 home 目录配置文件（通过重定向）
    import os
    from pathlib import Path
    home = str(Path.home())
    for cfg in HOME_CONFIG_HARD_BLOCK:
        blocked_path = f"{home}/{cfg}"
        if blocked_path in cmd or (cfg.startswith("/") and cfg in cmd):
            raise ToolError(
                f"禁止通过 shell 修改 shell/系统配置文件: {cfg}",
                tool="shell", rule="home_config_hard_block"
            )

    # 2. SANDBOX 模式额外拦截
    if permission == ToolPermission.SANDBOX:
        cmd_lower = cmd.lower()
        for kw in SANDBOX_BLOCK_KEYWORDS:
            if kw in cmd_lower:
                raise ToolError(
                    f"SANDBOX 模式拦截危险命令关键词 '{kw}'。"
                    f"如需执行，请使用 FULL 模式（geoclaw-claude tools enable --full）",
                    tool="shell", rule=f"sandbox_block:{kw}"
                )


# ── 工具实现 ───────────────────────────────────────────────────────────────────

def tool_shell(
    cmd:        str,
    cwd:        Optional[str] = None,
    timeout:    int = 30,
    permission: ToolPermission = ToolPermission.SANDBOX,
    env_extra:  Optional[dict] = None,
) -> ToolResult:
    """
    执行 Shell 命令。

    Args:
        cmd     : Shell 命令字符串
        cwd     : 工作目录（默认不变）
        timeout : 超时秒数（默认 30，最大 300）
        env_extra: 额外注入的环境变量（不覆盖系统变量）
    """
    t0 = time.time()
    timeout = min(max(1, timeout), 300)

    try:
        _check_cmd(cmd, permission)
    except ToolError as e:
        return ToolResult(tool="shell", success=False,
                          error=str(e), duration=time.time() - t0)

    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        returncode = proc.returncode

        # 合并输出
        output_parts = []
        if stdout.strip():
            output_parts.append(stdout)
        if stderr.strip():
            output_parts.append(f"[stderr]\n{stderr}")

        output = "\n".join(output_parts) if output_parts else "(无输出)"

        return ToolResult(
            tool="shell",
            success=(returncode == 0),
            output=output,
            error=f"退出码 {returncode}" if returncode != 0 else "",
            duration=time.time() - t0,
            metadata={"returncode": returncode, "cmd": cmd[:200]},
        )

    except subprocess.TimeoutExpired:
        return ToolResult(
            tool="shell",
            success=False,
            error=f"命令超时（{timeout}s）: {cmd[:80]}",
            duration=time.time() - t0,
        )
    except Exception as e:
        return ToolResult(tool="shell", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_exec(
    args:       List[str],
    cwd:        Optional[str] = None,
    timeout:    int = 30,
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    以参数列表方式执行命令（更安全，不经 shell 解析）。

    Args:
        args   : 命令参数列表，如 ["python3", "script.py", "--input", "data.geojson"]
        cwd    : 工作目录
        timeout: 超时秒数
    """
    t0 = time.time()
    cmd_str = " ".join(str(a) for a in args)

    try:
        _check_cmd(cmd_str, permission)
    except ToolError as e:
        return ToolResult(tool="exec", success=False,
                          error=str(e), duration=time.time() - t0)

    try:
        proc = subprocess.run(
            [str(a) for a in args],
            capture_output=True,
            text=True,
            timeout=min(max(1, timeout), 300),
            cwd=cwd,
        )
        output_parts = []
        if proc.stdout.strip():
            output_parts.append(proc.stdout)
        if proc.stderr.strip():
            output_parts.append(f"[stderr]\n{proc.stderr}")
        output = "\n".join(output_parts) if output_parts else "(无输出)"

        return ToolResult(
            tool="exec",
            success=(proc.returncode == 0),
            output=output,
            error=f"退出码 {proc.returncode}" if proc.returncode != 0 else "",
            duration=time.time() - t0,
            metadata={"returncode": proc.returncode, "args": args[:10]},
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool="exec",
            success=False,
            error=f"命令超时（{timeout}s）",
            duration=time.time() - t0,
        )
    except Exception as e:
        return ToolResult(tool="exec", success=False,
                          error=str(e), duration=time.time() - t0)


# ── 工具规格（供 LLM）────────────────────────────────────────────────────────

SHELL_TOOL_SPECS = [
    ToolSpec(
        name="shell",
        description="执行 Shell 命令（bash）。返回 stdout/stderr 和退出码",
        parameters={
            "type": "object",
            "properties": {
                "cmd":     {"type": "string",  "description": "Shell 命令字符串"},
                "cwd":     {"type": "string",  "description": "工作目录（可选）"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 30，最大 300"},
            },
            "required": ["cmd"],
        },
    ),
    ToolSpec(
        name="exec",
        description="以参数列表方式执行命令（更安全，适合执行 Python 脚本等）",
        parameters={
            "type": "object",
            "properties": {
                "args":    {"type": "array", "items": {"type": "string"},
                            "description": "命令参数列表，如 [\"python3\", \"analyze.py\"]"},
                "cwd":     {"type": "string",  "description": "工作目录（可选）"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
            },
            "required": ["args"],
        },
    ),
]
