"""
geoclaw_claude/config.py
========================
配置管理器 — 统一管理用户配置、API Key、数据目录等。

配置文件位置: ~/.geoclaw_claude/config.json
环境变量可覆盖任意配置项:  GEOCLAW_<KEY>=value

使用示例:
    from geoclaw_claude.config import Config

    cfg = Config.load()
    print(cfg.anthropic_api_key)
    cfg.data_dir = "/data/gis"
    cfg.save()

────────────────────────────────────────────────────────
TODO:
  - [ ] 支持多 profile (dev/prod/lab)
  - [ ] 配置加密存储 (API Key 不明文)
  - [ ] 支持从 .env 文件加载
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# 默认配置目录
CONFIG_DIR  = Path.home() / ".geoclaw_claude"
CONFIG_FILE = CONFIG_DIR / "config.json"

# 环境变量前缀
ENV_PREFIX = "GEOCLAW_"


@dataclass
class Config:
    """GeoClaw-claude 全局配置。"""

    # ── AI API ────────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""          # Anthropic Claude API Key
    anthropic_model:   str = "claude-sonnet-4-20250514"  # Claude 默认模型

    openai_api_key:    str = ""          # OpenAI API Key
    openai_model:      str = "gpt-5.1-chat-latest"  # OpenAI 默认模型
    openai_base_url:   str = ""          # 自定义 base_url（兼容 API 代理）

    gemini_api_key:    str = ""                  # Google Gemini API Key
    gemini_model:      str = "gemini-2.0-flash"  # Gemini 默认模型

    qwen_api_key:      str = ""          # 通义千问 API Key（DashScope）
    qwen_model:        str = "qwen-plus" # Qwen 默认模型

    ollama_base_url:   str = "http://localhost:11434/v1"  # Ollama 本地服务地址
    ollama_model:      str = "qwen3:8b"    # Ollama 推荐默认（中文友好，推理强）    # Ollama 默认模型（需已 ollama pull）

    llm_provider:      str = ""          # 强制指定 provider（空=自动选择）
                                         # 可选: anthropic / gemini / openai / qwen / ollama

    # ── 上下文压缩 ────────────────────────────────────────────────────────────
    ctx_max_tokens:    int  = 6000   # 触发压缩的 token 阈值
    ctx_target_tokens: int  = 4000   # 压缩目标 token 数
    ctx_keep_recent:   int  = 6      # 保留最近 N 条消息不压缩
    ctx_compress_verbose: bool = False  # 是否打印压缩日志

    # ── 安全机制 ──────────────────────────────────────────────────────────────
    security_enabled:       bool = True   # 是否启用安全保护
    security_strict_output: bool = True   # 严格模式：所有输出必须在 output_dir 下
    tool_permission: str = "sandbox"       # 本地工具权限: full / sandbox / whitelist
    security_verbose:       bool = False  # 是否打印安全审计日志

    # ── 数据目录 ──────────────────────────────────────────────────────────────
    data_dir:    str = str(Path.home() / "geoclaw_data")   # 本地数据根目录
    cache_dir:   str = str(CONFIG_DIR / "cache")           # 网络下载缓存
    output_dir:  str = str(Path.home() / "geoclaw_output") # 分析结果输出目录
    skill_dir:   str = str(CONFIG_DIR / "skills")          # 用户 skill 目录

    # ── 网络设置 ──────────────────────────────────────────────────────────────
    proxy:            str  = ""    # HTTP 代理, 如 http://127.0.0.1:7890
    overpass_url:     str  = "https://overpass-api.de/api/interpreter"
    nominatim_url:    str  = "https://nominatim.openstreetmap.org"
    request_timeout:  int  = 60    # 网络请求超时(秒)
    enable_cache:     bool = True  # 是否缓存网络请求结果
    cache_ttl_hours:  int  = 24    # 缓存有效期(小时)

    # ── 制图设置 ──────────────────────────────────────────────────────────────
    default_crs:    str = "EPSG:4326"  # 默认坐标系
    default_dpi:    int = 150          # 默认输出分辨率
    font_cjk:       str = ""           # CJK 字体路径（空=自动检测）

    # ── Skill 系统 ────────────────────────────────────────────────────────────
    skill_auto_load: bool = True   # 启动时自动加载 skill_dir 中的 skill

    # ── 日志 ─────────────────────────────────────────────────────────────────
    log_level: str = "INFO"   # DEBUG / INFO / WARNING / ERROR
    log_file:  str = ""       # 空=只输出到终端

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "Config":
        """
        加载配置，优先级: 环境变量 > config.json > 默认值。
        若配置文件不存在则使用默认值（不自动创建）。
        """
        cfg = cls()

        # 1. 从文件加载
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception as e:
                print(f"  ⚠ 读取配置文件失败: {e}，使用默认值")

        # 2. 环境变量覆盖（GEOCLAW_ANTHROPIC_API_KEY → anthropic_api_key）
        for key in asdict(cfg).keys():
            env_key = ENV_PREFIX + key.upper()
            env_val = os.environ.get(env_key)
            if env_val is not None:
                # 类型推断
                cur = getattr(cfg, key)
                if isinstance(cur, bool):
                    setattr(cfg, key, env_val.lower() in ("1", "true", "yes"))
                elif isinstance(cur, int):
                    try:
                        setattr(cfg, key, int(env_val))
                    except ValueError:
                        pass
                else:
                    setattr(cfg, key, env_val)

        return cfg

    def save(self) -> None:
        """保存配置到 ~/.geoclaw_claude/config.json。"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def ensure_dirs(self) -> None:
        """确保所有配置目录存在。"""
        for d in [self.data_dir, self.cache_dir, self.output_dir, self.skill_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)

    def summary(self) -> str:
        """返回配置摘要（隐藏敏感信息）。"""
        def mask(v: str) -> str:
            if not v: return "(未设置)"
            v = v.strip()
            show = 4
            if len(v) <= show * 2: return v[:2] + "***"
            return f"{v[:show]}...{v[-show:]}"

        def provider_label() -> str:
            if self.llm_provider:
                return self.llm_provider
            if self.anthropic_api_key:
                return "anthropic (auto)"
            if self.gemini_api_key:
                return "gemini (auto)"
            if self.openai_api_key:
                return "openai (auto)"
            if self.qwen_api_key:
                return "qwen (auto)"
            return "(未配置)"

        lines = [
            "╔══ GeoClaw-claude 配置 ══╗",
            f"  LLM Provider      : {provider_label()}",
            f"  Anthropic API Key : {mask(self.anthropic_api_key)} / {self.anthropic_model}",
            f"  Gemini API Key    : {mask(self.gemini_api_key)} / {self.gemini_model}",
            f"  OpenAI API Key    : {mask(self.openai_api_key)} / {self.openai_model}",
            f"  Qwen API Key      : {mask(self.qwen_api_key)} / {self.qwen_model}",
            f"  上下文压缩        : 阈值 {self.ctx_max_tokens} tokens → 压至 {self.ctx_target_tokens}",
            f"  安全机制          : {'启用' if self.security_enabled else '关闭'}"
            + (" [严格模式]" if self.security_strict_output else ""),
            f"  数据目录          : {self.data_dir}",
            f"  缓存目录          : {self.cache_dir}",
            f"  输出目录          : {self.output_dir}",
            f"  Skill 目录        : {self.skill_dir}",
            f"  Overpass URL      : {self.overpass_url}",
            f"  代理              : {self.proxy or '(无)'}",
            f"  缓存启用          : {self.enable_cache} (TTL {self.cache_ttl_hours}h)",
            f"  默认坐标系        : {self.default_crs}",
            f"  配置文件          : {CONFIG_FILE}",
        ]
        return "\n".join(lines)

    def set(self, key: str, value: str) -> None:
        """
        设置单个配置项（从字符串自动推断类型）。

        Raises:
            KeyError: 配置项不存在
        """
        if not hasattr(self, key):
            raise KeyError(f"未知配置项: {key}。可用项: {list(asdict(self).keys())}")
        cur = getattr(self, key)
        if isinstance(cur, bool):
            setattr(self, key, value.lower() in ("1", "true", "yes"))
        elif isinstance(cur, int):
            setattr(self, key, int(value))
        else:
            setattr(self, key, value)
