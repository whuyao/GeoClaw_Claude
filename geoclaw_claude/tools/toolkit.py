# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools.toolkit
-----------------------------
LocalToolKit：统一的工具分发器。

所有工具通过 kit.run(tool_name, **kwargs) 调用，
结果统一返回 ToolResult，并记录执行历史。

权限配置
--------
    kit = LocalToolKit(permission=ToolPermission.FULL)
    kit = LocalToolKit(permission=ToolPermission.SANDBOX)  # 默认

白名单配置
----------
    kit = LocalToolKit(
        permission=ToolPermission.WHITELIST,
        whitelist_cmds=["python3", "ls", "cat"],
        whitelist_paths=["/home/user/data/", "~/geoclaw_output/"],
    )
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ToolResult, ToolError, ToolPermission, ToolSpec
from .fs_tools import (
    tool_file_find, tool_file_read, tool_file_write, tool_file_list,
    FS_TOOL_SPECS,
)
from .shell_tools import tool_shell, tool_exec, SHELL_TOOL_SPECS
from .http_tools import tool_http_get, tool_http_post, tool_curl, HTTP_TOOL_SPECS
from .sys_tools import (
    tool_sys_info, tool_sys_processes, tool_sys_disk, tool_sys_env,
    SYS_TOOL_SPECS,
)


# ── LocalToolKit ──────────────────────────────────────────────────────────────

class LocalToolKit:
    """
    统一的本地工具执行器。

    Args:
        permission      : 权限模式（FULL / SANDBOX / WHITELIST）
        whitelist_cmds  : WHITELIST 模式下允许的命令前缀
        whitelist_paths : WHITELIST 模式下允许读写的路径前缀
        history_limit   : 保留的历史记录条数上限
    """

    ALL_TOOLS: List[str] = [
        # 文件系统
        "file_find", "file_read", "file_write", "file_list",
        # Shell
        "shell", "exec",
        # HTTP
        "http_get", "http_post", "curl",
        # 系统信息
        "sys_info", "sys_processes", "sys_disk", "sys_env",
    ]

    def __init__(
        self,
        permission:      ToolPermission = ToolPermission.SANDBOX,
        whitelist_cmds:  Optional[List[str]] = None,
        whitelist_paths: Optional[List[str]] = None,
        history_limit:   int = 200,
    ):
        self.permission      = permission
        self._whitelist_cmds  = [c.lower() for c in (whitelist_cmds or [])]
        self._whitelist_paths = [str(Path(p).expanduser().resolve())
                                 for p in (whitelist_paths or [])]
        self._history:    List[Dict[str, Any]] = []
        self._history_limit = history_limit

    # ── 主调用入口 ────────────────────────────────────────────────────────────

    def run(self, tool: str, **kwargs) -> ToolResult:
        """
        执行工具。

        Args:
            tool  : 工具名称（见 ALL_TOOLS）
            **kwargs: 工具参数（参见各工具 docstring）

        Returns:
            ToolResult
        """
        t0 = time.time()

        # WHITELIST 预检查
        if self.permission == ToolPermission.WHITELIST:
            result = self._whitelist_check(tool, kwargs)
            if result is not None:
                self._record(tool, kwargs, result)
                return result

        try:
            result = self._dispatch(tool, kwargs)
        except ToolError as e:
            result = ToolResult(tool=tool, success=False, error=str(e),
                                duration=time.time() - t0)
        except Exception as e:
            result = ToolResult(tool=tool, success=False,
                                error=f"内部错误: {e}",
                                duration=time.time() - t0)

        self._record(tool, kwargs, result)
        return result

    def run_many(self, calls: List[Dict[str, Any]]) -> List[ToolResult]:
        """
        批量执行工具调用。

        Args:
            calls: [{"tool": "shell", "cmd": "ls"}, ...]

        Returns:
            List[ToolResult]
        """
        results = []
        for call in calls:
            tool = call.pop("tool", "")
            results.append(self.run(tool, **call))
        return results

    # ── 分发 ─────────────────────────────────────────────────────────────────

    def _dispatch(self, tool: str, kwargs: Dict[str, Any]) -> ToolResult:
        kwargs = {**kwargs, "permission": self.permission}
        dispatch = {
            # 文件系统
            "file_find":  tool_file_find,
            "file_read":  tool_file_read,
            "file_write": tool_file_write,
            "file_list":  tool_file_list,
            # Shell
            "shell":      tool_shell,
            "exec":       tool_exec,
            # HTTP
            "http_get":   tool_http_get,
            "http_post":  tool_http_post,
            "curl":       tool_curl,
            # 系统
            "sys_info":      tool_sys_info,
            "sys_processes": tool_sys_processes,
            "sys_disk":      tool_sys_disk,
            "sys_env":       tool_sys_env,
        }
        fn = dispatch.get(tool)
        if fn is None:
            return ToolResult(
                tool=tool,
                success=False,
                error=f"未知工具 '{tool}'。可用工具: {', '.join(self.ALL_TOOLS)}",
            )
        return fn(**kwargs)

    # ── WHITELIST 检查 ────────────────────────────────────────────────────────

    def _whitelist_check(self, tool: str, kwargs: Dict) -> Optional[ToolResult]:
        """检查白名单，返回 None 表示通过，返回 ToolResult 表示被拒绝。"""
        if tool in ("shell", "exec"):
            cmd = kwargs.get("cmd", "") or " ".join(str(a) for a in kwargs.get("args", []))
            allowed = any(cmd.lower().startswith(c) for c in self._whitelist_cmds)
            if not allowed:
                return ToolResult(
                    tool=tool,
                    success=False,
                    error=(
                        f"WHITELIST 模式：命令 '{cmd[:60]}' 不在白名单中。\n"
                        f"已允许命令: {', '.join(self._whitelist_cmds) or '(未配置)'}"
                    ),
                )
        if tool in ("file_read", "file_write", "file_find", "file_list"):
            path = kwargs.get("path", kwargs.get("root", "."))
            from .fs_tools import _expand
            resolved = str(_expand(path))
            allowed = (not self._whitelist_paths or
                       any(resolved.startswith(p) for p in self._whitelist_paths))
            if not allowed:
                return ToolResult(
                    tool=tool,
                    success=False,
                    error=(
                        f"WHITELIST 模式：路径 '{resolved}' 不在白名单中。\n"
                        f"已允许路径: {', '.join(self._whitelist_paths) or '(未配置)'}"
                    ),
                )
        return None  # 通过

    # ── 历史记录 ──────────────────────────────────────────────────────────────

    def _record(self, tool: str, kwargs: Dict, result: ToolResult) -> None:
        entry = {
            "tool":    tool,
            "kwargs":  {k: v for k, v in kwargs.items() if k != "permission"},
            "success": result.success,
            "error":   result.error,
            "duration": result.duration,
        }
        self._history.append(entry)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

    def history(self, last_n: int = 20) -> List[Dict]:
        """返回最近 n 条工具调用记录（不含输出，避免过大）。"""
        return self._history[-last_n:]

    def history_summary(self) -> str:
        """返回历史记录的文本摘要。"""
        lines = [f"工具调用历史（最近 {len(self._history)} 条）:"]
        for i, h in enumerate(self._history[-20:], 1):
            status = "✓" if h["success"] else "✗"
            kw_str = ", ".join(f"{k}={str(v)[:30]}" for k, v in h["kwargs"].items())
            lines.append(f"  {i:2}. {status} {h['tool']}({kw_str})  {h['duration']:.2f}s")
        return "\n".join(lines)

    # ── LLM 工具规格 ──────────────────────────────────────────────────────────

    @property
    def specs(self) -> List[ToolSpec]:
        """返回所有工具的 ToolSpec 列表，供 LLM 了解可用工具。"""
        return FS_TOOL_SPECS + SHELL_TOOL_SPECS + HTTP_TOOL_SPECS + SYS_TOOL_SPECS

    def specs_text(self) -> str:
        """返回工具规格的文本描述，适合注入到 LLM system prompt。"""
        lines = ["## 可用本地工具\n"]
        for spec in self.specs:
            props = spec.parameters.get("properties", {})
            required = spec.parameters.get("required", [])
            params_desc = []
            for pname, pschema in props.items():
                req_mark = "*" if pname in required else ""
                desc = pschema.get("description", "")
                params_desc.append(f"    - {pname}{req_mark}: {desc}")
            lines.append(f"### {spec.name}")
            lines.append(f"{spec.description}")
            if params_desc:
                lines.append("参数（* 为必填）:")
                lines.extend(params_desc)
            lines.append("")
        return "\n".join(lines)

    # ── 权限描述 ──────────────────────────────────────────────────────────────

    def permission_summary(self) -> str:
        mode_desc = {
            ToolPermission.FULL:      "完全授权（仍受硬性系统保护）",
            ToolPermission.SANDBOX:   "沙箱模式（拦截危险命令）",
            ToolPermission.WHITELIST: "白名单模式（仅允许预配置操作）",
        }
        desc = mode_desc.get(self.permission, str(self.permission))
        return f"当前工具权限: {desc}"
