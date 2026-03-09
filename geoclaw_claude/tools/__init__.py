# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools
=====================
本地工具执行框架。为 GeoAgent 提供文件系统、Shell、HTTP、系统信息四类本地工具，
支持 LLM 自动调用（ReAct 风格）和用户自然语言触发两种模式。

权限模式
--------
- FULL      : 用户显式启用，无操作级别限制（仍有不可绕过的系统保护）
- SANDBOX   : 默认模式，拦截危险命令，限制写入范围
- WHITELIST : 只允许预先配置的命令/路径（最严格）

用法
----
    from geoclaw_claude.tools import LocalToolKit, ToolPermission
    kit = LocalToolKit(permission=ToolPermission.FULL)
    result = kit.run("shell", cmd="ls -la ~/geoclaw_output")
    result = kit.run("file_read", path="~/data/wuhan.geojson")
"""

from .base import ToolResult, ToolError, ToolPermission
from .toolkit import LocalToolKit
from .react_agent import ReActAgent

__all__ = [
    "LocalToolKit",
    "ToolResult",
    "ToolError",
    "ToolPermission",
    "ReActAgent",
]
