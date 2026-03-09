# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools.http_tools
--------------------------------
网络请求工具：HTTP GET / POST / curl 风格接口。

安全控制
--------
- 禁止请求本地回环地址（127.0.0.1、localhost、::1）防止 SSRF
- 禁止请求云服务元数据端点（169.254.169.254 等）
- 响应体超过 5MB 时自动截断
- SANDBOX 模式限制只允许 http/https 协议
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Union

from .base import ToolResult, ToolError, ToolPermission, ToolSpec


# ── 安全检查 ──────────────────────────────────────────────────────────────────

# 禁止访问的地址（SSRF 防护）
_BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "169.254.169.254",   # AWS/GCP/Azure 元数据
    "metadata.google.internal",
    "metadata.internal",
}

_BLOCKED_HOST_PREFIXES = ("192.168.", "10.", "172.16.", "172.17.", "172.18.",
                           "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
                           "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
                           "172.29.", "172.30.", "172.31.")

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


def _check_url(url: str, permission: ToolPermission) -> None:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        raise ToolError(f"无效 URL: {url}", tool="http")

    # 协议检查
    if parsed.scheme not in ("http", "https"):
        raise ToolError(
            f"仅支持 http/https 协议，收到: {parsed.scheme}",
            tool="http", rule="unsupported_scheme"
        )

    # SSRF 防护
    host = parsed.hostname or ""
    if host in _BLOCKED_HOSTS:
        raise ToolError(
            f"禁止访问本地/元数据地址: {host}",
            tool="http", rule="ssrf_block"
        )
    for prefix in _BLOCKED_HOST_PREFIXES:
        if host.startswith(prefix):
            raise ToolError(
                f"禁止访问内网地址: {host}",
                tool="http", rule="ssrf_private_ip"
            )


# ── 工具实现 ───────────────────────────────────────────────────────────────────

def tool_http_get(
    url:        str,
    headers:    Optional[Dict[str, str]] = None,
    params:     Optional[Dict[str, str]] = None,
    timeout:    int = 30,
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    HTTP GET 请求。

    Args:
        url    : 请求 URL
        headers: 额外请求头
        params : URL 查询参数（自动 URL encode）
        timeout: 超时秒数
    """
    t0 = time.time()
    try:
        _check_url(url, permission)
    except ToolError as e:
        return ToolResult(tool="http_get", success=False,
                          error=str(e), duration=time.time() - t0)

    try:
        import urllib.request
        if params:
            url = url + "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "GeoClaw-claude/3.1 (+https://urbancomp.net)")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(_MAX_RESPONSE_BYTES)
            truncated = len(raw) >= _MAX_RESPONSE_BYTES

        # 尝试解析为文本
        encoding = "utf-8"
        if "charset=" in content_type:
            encoding = content_type.split("charset=")[-1].strip()
        try:
            text = raw.decode(encoding, errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")

        if truncated:
            text += f"\n... [响应被截断，已读 {len(raw)} 字节]"

        return ToolResult(
            tool="http_get",
            success=(200 <= status < 300),
            output=text,
            error="" if 200 <= status < 300 else f"HTTP {status}",
            duration=time.time() - t0,
            metadata={"status": status, "url": url, "content_type": content_type},
        )
    except ToolError:
        raise
    except Exception as e:
        return ToolResult(tool="http_get", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_http_post(
    url:         str,
    data:        Optional[Union[str, Dict]] = None,
    json_data:   Optional[Dict] = None,
    headers:     Optional[Dict[str, str]] = None,
    timeout:     int = 30,
    permission:  ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    HTTP POST 请求。

    Args:
        url      : 请求 URL
        data     : 表单数据（str 或 dict）
        json_data: JSON body（优先于 data）
        headers  : 额外请求头
        timeout  : 超时秒数
    """
    t0 = time.time()
    try:
        _check_url(url, permission)
    except ToolError as e:
        return ToolResult(tool="http_post", success=False,
                          error=str(e), duration=time.time() - t0)

    try:
        import urllib.request

        body: bytes
        content_type = "application/x-www-form-urlencoded"

        if json_data is not None:
            body = json.dumps(json_data).encode("utf-8")
            content_type = "application/json"
        elif isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode("utf-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = b""

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", content_type)
        req.add_header("User-Agent", "GeoClaw-claude/3.1 (+https://urbancomp.net)")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            content_type_resp = resp.headers.get("Content-Type", "")
            raw = resp.read(_MAX_RESPONSE_BYTES)

        text = raw.decode("utf-8", errors="replace")
        return ToolResult(
            tool="http_post",
            success=(200 <= status < 300),
            output=text,
            error="" if 200 <= status < 300 else f"HTTP {status}",
            duration=time.time() - t0,
            metadata={"status": status, "url": url},
        )
    except ToolError:
        raise
    except Exception as e:
        return ToolResult(tool="http_post", success=False,
                          error=str(e), duration=time.time() - t0)


def tool_curl(
    url:        str,
    method:     str = "GET",
    headers:    Optional[Dict[str, str]] = None,
    data:       Optional[str] = None,
    timeout:    int = 30,
    permission: ToolPermission = ToolPermission.SANDBOX,
) -> ToolResult:
    """
    curl 风格的 HTTP 请求（自动选择 GET / POST）。

    Args:
        url    : 请求 URL
        method : HTTP 方法（GET/POST/PUT/DELETE 等）
        headers: 请求头 dict
        data   : 请求体字符串
        timeout: 超时秒数
    """
    t0 = time.time()
    try:
        _check_url(url, permission)
    except ToolError as e:
        return ToolResult(tool="curl", success=False,
                          error=str(e), duration=time.time() - t0)

    try:
        import urllib.request
        body = data.encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, method=method.upper())
        req.add_header("User-Agent", "GeoClaw-claude/3.1 (+https://urbancomp.net)")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        if body and "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read(_MAX_RESPONSE_BYTES)

        text = raw.decode("utf-8", errors="replace")
        return ToolResult(
            tool="curl",
            success=(200 <= status < 300),
            output=text,
            error="" if 200 <= status < 300 else f"HTTP {status}",
            duration=time.time() - t0,
            metadata={"status": status, "method": method.upper(), "url": url},
        )
    except ToolError:
        raise
    except Exception as e:
        return ToolResult(tool="curl", success=False,
                          error=str(e), duration=time.time() - t0)


# ── 工具规格（供 LLM）────────────────────────────────────────────────────────

HTTP_TOOL_SPECS = [
    ToolSpec(
        name="http_get",
        description="发起 HTTP GET 请求，返回响应文本",
        parameters={
            "type": "object",
            "properties": {
                "url":     {"type": "string", "description": "请求 URL"},
                "headers": {"type": "object", "description": "额外请求头（可选）"},
                "params":  {"type": "object", "description": "URL 查询参数（可选）"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
            },
            "required": ["url"],
        },
    ),
    ToolSpec(
        name="http_post",
        description="发起 HTTP POST 请求，支持 JSON body 或表单数据",
        parameters={
            "type": "object",
            "properties": {
                "url":       {"type": "string", "description": "请求 URL"},
                "json_data": {"type": "object", "description": "JSON 请求体（优先）"},
                "data":      {"type": "string", "description": "表单或原始字符串 body"},
                "headers":   {"type": "object", "description": "额外请求头"},
                "timeout":   {"type": "integer", "description": "超时秒数，默认 30"},
            },
            "required": ["url"],
        },
    ),
    ToolSpec(
        name="curl",
        description="curl 风格的 HTTP 请求，支持任意方法",
        parameters={
            "type": "object",
            "properties": {
                "url":     {"type": "string", "description": "请求 URL"},
                "method":  {"type": "string", "description": "HTTP 方法，默认 GET"},
                "headers": {"type": "object", "description": "请求头 dict"},
                "data":    {"type": "string", "description": "请求体"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
            },
            "required": ["url"],
        },
    ),
]
