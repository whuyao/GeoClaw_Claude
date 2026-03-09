# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools.base
--------------------------
基础数据类型：权限枚举、工具结果、工具规格。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── 权限模式 ──────────────────────────────────────────────────────────────────

class ToolPermission(str, Enum):
    """
    工具执行权限模式。

    FULL      : 用户显式启用后，操作级别不加软性限制。
                仍保留不可绕过的系统硬性保护（shell 锁定目录写入等）。
    SANDBOX   : 拦截危险命令（rm -rf、chmod 系统目录等），限制写入路径。
    WHITELIST : 只允许预先配置的命令/路径，其余一律拒绝。
    """
    FULL      = "full"
    SANDBOX   = "sandbox"
    WHITELIST = "whitelist"


# ── 工具调用结果 ──────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """工具执行结果。"""
    tool:       str                       # 工具名称
    success:    bool                      # 是否成功
    output:     Any          = None       # 执行输出（str / dict / bytes）
    error:      str          = ""         # 错误信息（success=False 时填写）
    duration:   float        = 0.0        # 执行耗时（秒）
    metadata:   Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        if self.success:
            out = str(self.output)
            preview = out[:500] + "..." if len(out) > 500 else out
            return f"[{self.tool}] OK ({self.duration:.2f}s)\n{preview}"
        return f"[{self.tool}] ERROR: {self.error}"

    def to_llm_text(self) -> str:
        """序列化为 LLM 可读格式，用于 ReAct 观察步骤。"""
        if self.success:
            out = str(self.output) if not isinstance(self.output, str) else self.output
            # 超长截断，保留 LLM 上下文
            if len(out) > 3000:
                out = out[:3000] + f"\n... [截断，共 {len(out)} 字符]"
            return f"<tool_result tool=\"{self.tool}\" status=\"ok\">\n{out}\n</tool_result>"
        return f"<tool_result tool=\"{self.tool}\" status=\"error\">\n{self.error}\n</tool_result>"


# ── 工具错误 ──────────────────────────────────────────────────────────────────

class ToolError(Exception):
    """工具执行错误（权限拒绝、参数错误、执行失败等）。"""
    def __init__(self, msg: str, tool: str = "", rule: str = ""):
        self.tool = tool
        self.rule = rule
        super().__init__(msg)


# ── 工具规格（供 LLM function-calling 使用）──────────────────────────────────

@dataclass
class ToolSpec:
    """工具规格描述，供 LLM 了解如何调用。"""
    name:        str
    description: str
    parameters:  Dict[str, Any]   # JSON Schema 风格

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "parameters":  self.parameters,
        }


# ── 不可绕过的系统硬性保护（全权限模式也生效）────────────────────────────────

# Shell 命令中的绝对禁止模式（正则）
SHELL_HARD_BLOCK_PATTERNS = [
    r"rm\s+.*-[a-z]*r[a-z]*f",          # rm -rf 任意变体
    r":\s*\(\s*\)\s*\{.*\|\s*:\s*&",     # fork bomb
    r"mkfs\b",                            # 格式化磁盘
    r"dd\s+.*of=\s*/dev/[sh]d",          # 覆写磁盘
    r">\s*/dev/(s[da]|hd|nvme)",          # 重定向到块设备
    r"chmod\s+-R\s+[0-7]*7[0-7]*\s+/",  # 递归改全局权限
    r"chown\s+-R.*\s+/",                 # 递归改全局属主
    r"(curl|wget).*\|\s*(bash|sh|python)", # 远程代码执行管道
    r"base64\s+-d.*\|\s*(bash|sh)",       # base64 解码执行
    r"python[23]?\s+-c\s+.*os\.system",   # python 内嵌 shell
]

# 写入目标中的绝对禁止路径前缀
PATH_HARD_BLOCK_PREFIXES = [
    "/etc/", "/usr/", "/bin/", "/sbin/", "/lib", "/boot/",
    "/proc/", "/sys/", "/dev/", "/var/log/", "/var/lib/",
]

# Shell 写入的 home 目录下的禁止配置文件
HOME_CONFIG_HARD_BLOCK = [
    ".bashrc", ".bash_profile", ".zshrc", ".zprofile",
    ".profile", ".bash_logout", ".login",
    "Library/LaunchAgents/", "Library/LaunchDaemons/",  # macOS launchd
    ".config/systemd/",                                  # Linux systemd user
    ".ssh/authorized_keys", ".ssh/config",               # SSH
    ".gnupg/",
    ".aws/credentials", ".aws/config",
    ".gitconfig",
]

# SANDBOX 模式额外拦截的危险命令关键词
SANDBOX_BLOCK_KEYWORDS = [
    "sudo", "su ", "passwd", "visudo",
    "iptables", "ufw", "firewall",
    "launchctl", "systemctl", "service ",
    "crontab", "at ",
    "scp ", "rsync ", "ssh ",
    "nmap", "tcpdump", "wireshark",
    "kill -9 1",                  # 杀 init
]
