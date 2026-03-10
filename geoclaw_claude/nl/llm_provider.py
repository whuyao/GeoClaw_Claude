"""
geoclaw_claude/nl/llm_provider.py
===================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

多 LLM Provider 适配层

统一封装 Anthropic Claude / OpenAI / Qwen（通义千问）/ Google Gemini /
Ollama（本地大模型）的 API 调用，对外暴露统一接口 LLMProvider.chat()，
上层代码无需感知具体 Provider。

支持的 Provider:
  - anthropic : Claude 系列（claude-sonnet-4-20250514 等）
  - openai    : GPT-4o / GPT-4o-mini 等，以及任意 OpenAI 兼容 API
  - qwen      : 通义千问 Qwen3/Qwen3.5 系列（qwen3-235b-a22b / qwen3-8b 等），OpenAI 兼容接口
  - gemini    : Google Gemini（gemini-2.0-flash / gemini-1.5-pro 等）
  - ollama    : 本地大模型（qwen3 / llama4 / deepseek-r1 / gemma3 等），无需 API Key

Provider 选择优先级（自动模式）:
  1. 已设置 anthropic_api_key → anthropic
  2. 已设置 gemini_api_key    → gemini
  3. 已设置 openai_api_key    → openai
  4. 已设置 qwen_api_key      → qwen
  5. ollama_base_url 可达      → ollama（本地离线优先）
  6. 均不可用                 → 降级规则模式（返回 None）

Ollama 快速上手:
  # 安装并启动 Ollama 服务（默认端口 11434）
  # 拉取模型: ollama pull qwen3:8b / qwen3.5:35b-a3b / deepseek-r1:7b 等
  # 在 geoclaw config 中设置:
  #   ollama_base_url = "http://localhost:11434"
  #   ollama_model    = "qwen3:8b"        # 或 qwen3.5:35b-a3b, deepseek-r1:7b ...
  #   llm_provider    = "ollama"          # 可选: 强制使用 ollama
  # Ollama 使用 OpenAI 兼容接口，无需 API Key（api_key 自动设为 "ollama"）

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ── Provider 名称常量 ────────────────────────────────────────────────────────

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI    = "openai"
PROVIDER_QWEN      = "qwen"
PROVIDER_GEMINI    = "gemini"
PROVIDER_OLLAMA    = "ollama"

# Qwen 兼容 OpenAI 的 base_url
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Ollama 默认 base_url（本地服务，无需 API Key）
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"

# 各 Provider 默认模型
DEFAULT_MODELS = {
    PROVIDER_ANTHROPIC: "claude-sonnet-4-20250514",
    PROVIDER_OPENAI:    "gpt-4o-mini",
    PROVIDER_QWEN:      "qwen3-235b-a22b",   # Qwen3 旗舰 MoE，2025-04 发布
    PROVIDER_GEMINI:    "gemini-2.0-flash",
    PROVIDER_OLLAMA:    "qwen3:8b",           # Ollama 默认：Qwen3 8B（中文友好，推理强）
}

# Gemini 可用模型列表（供 onboard 提示）
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-preview",
    "gemini-2.5-pro-preview",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

# Qwen API 可用模型列表（供 onboard 提示）
# Qwen3 系列：2025-04 发布，支持思考模式/非思考模式双模、119 种语言
# Qwen3.5 系列：2026-02 发布，原生多模态 MoE
QWEN_MODELS = [
    # ── Qwen3 Dense（轻量部署）──────────────────────────
    "qwen3-0.6b",
    "qwen3-1.7b",
    "qwen3-4b",
    "qwen3-8b",
    "qwen3-14b",
    "qwen3-32b",
    # ── Qwen3 MoE（高性能）──────────────────────────────
    "qwen3-30b-a3b",        # 30B 总参数 / 3B 激活，超越 QwQ-32B
    "qwen3-235b-a22b",      # 旗舰 MoE，对标 DeepSeek-R1 / GPT-o3
    # ── Qwen3 更新版本（2025-07）────────────────────────
    "qwen3-instruct-2507",
    "qwen3-thinking-2507",
    # ── Qwen3.5（2026-02，原生多模态 MoE）──────────────
    "qwen3.5-397b-a17b",    # Qwen3.5 旗舰 MoE（2026-02，原生多模态）
    # ── Qwen3.5 中等系列（2026-02-24，Gated DeltaNet + MoE 混合架构）──
    "qwen3.5-35b-a3b",      # 35B 总 / 3B 激活，性能超越 Qwen3-235B-A22B，8 GB+ VRAM
    "qwen3.5-27b",          # 27B Dense，均衡，22 GB+ VRAM
    "qwen3.5-122b-a10b",    # 122B 总 / 10B 激活，工具调用最强，BFCL-V4 第一
    # ── Qwen3.5 小系列（2026-02，Ollama 原生支持）───────
    "qwen3.5-9b",
    "qwen3.5-4b",
    "qwen3.5-2b",
    "qwen3.5-0.8b",
    # ── 旧版保留（部分场景兼容）──────────────────────────
    "qwen2.5-72b-instruct",
    "qwen2.5-14b-instruct",
    "qwen-plus",            # DashScope 标准 API 别名
    "qwen-turbo",
    "qwen-max",
]

# Ollama 常用模型列表（供 onboard 提示）
# 截至 2026-03，基于 https://ollama.com/library 整理
OLLAMA_MODELS = [
    # ── Qwen3（推荐，中文支持最佳，推理强）──────────────
    "qwen3:8b",             # 推荐默认，平衡性能/资源
    "qwen3:4b",             # 轻量，可在 4 GB RAM 上运行
    "qwen3:14b",            # 高质量，需 10 GB+ VRAM
    "qwen3:32b",            # 旗舰 Dense，需 24 GB+ VRAM
    "qwen3:30b-a3b",        # MoE，激活参数仅 3B，效率高
    # ── Qwen3.5 中等系列（2026-02，混合架构，性能超越 Qwen3 旗舰）──
    "qwen3.5:35b-a3b",      # 3B 激活，8 GB+ VRAM，性价比旗舰，推荐服务器部署
    "qwen3.5:27b",          # 27B Dense，256K 上下文，22 GB+ VRAM
    "qwen3.5:122b-a10b",    # 122B 总 / 10B 激活，工具调用第一，需 40 GB+ VRAM
    # ── Qwen3.5 小系列（2026-02，Ollama 原生支持，多模态）──
    "qwen3.5:9b",           # 推荐轻量默认，12 GB RAM 即可
    "qwen3.5:4b",
    "qwen3.5:2b",
    "qwen3.5:0.8b",         # 极轻量，边缘设备
    # ── LLaMA 4（Meta，2025，原生多模态）────────────────
    "llama4:scout",         # 17B 激活 / 109B 总参数 MoE，10M 上下文
    "llama4:maverick",      # 17B 激活 / 400B 总参数 MoE
    # ── LLaMA 3.x（稳定，生态成熟）─────────────────────
    "llama3.3:70b",         # 128K 上下文，高质量通用助手
    "llama3.2:3b",          # 超轻量，笔记本可用
    # ── DeepSeek（推理强，代码强）────────────────────────
    "deepseek-r1:7b",       # R1 蒸馏，推理链条，适合 SRE 分析
    "deepseek-r1:14b",
    "deepseek-r1:32b",
    "deepseek-v3.1",        # V3.1（2025-08）：思考/非思考双模，SWE-bench 第一
    # ── Gemma 3（Google，轻量多模态）──────────────────
    "gemma3:4b",            # 支持图文，轻量
    "gemma3:12b",           # 128K 上下文
    "gemma3:27b",           # 旗舰，需 20 GB+ VRAM
    # ── Mistral Small 3.1（高效，128K）────────────────
    "mistral-small3.1:24b",
    # ── Phi-4（微软，14B 高性能小模型）────────────────
    "phi4:14b",
]


# ── LLM 响应 ────────────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """统一 LLM 响应格式。"""
    content:    str            # 模型回复文本
    provider:   str            # 实际使用的 provider
    model:      str            # 实际使用的模型
    tokens_in:  int = 0        # 输入 token（若 API 返回）
    tokens_out: int = 0        # 输出 token（若 API 返回）
    raw:        Any = None     # 原始 API 响应（调试用）

    def __bool__(self) -> bool:
        return bool(self.content)


# ── Provider 配置 ────────────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    """单个 Provider 的配置。"""
    provider:    str
    api_key:     str
    model:       str   = ""
    base_url:    str   = ""    # 仅 openai/qwen 需要
    max_tokens:  int   = 1024
    temperature: float = 0.1   # 低温度，保证解析稳定性

    def __post_init__(self):
        if not self.model:
            self.model = DEFAULT_MODELS.get(self.provider, "")
        if self.provider == PROVIDER_QWEN and not self.base_url:
            self.base_url = QWEN_BASE_URL
        # Ollama: no API key needed, use OpenAI-compat endpoint
        if self.provider == PROVIDER_OLLAMA:
            if not self.base_url:
                self.base_url = OLLAMA_DEFAULT_BASE_URL
            if not self.api_key:
                self.api_key = "ollama"   # openai client requires non-empty key

    @property
    def is_valid(self) -> bool:
        if self.provider == PROVIDER_OLLAMA:
            # Ollama only needs base_url (api_key is dummy "ollama")
            return bool(self.base_url and self.model)
        return bool(self.api_key and self.model)


# ── 主 Provider 类 ───────────────────────────────────────────────────────────

class LLMProvider:
    """
    统一 LLM 调用接口，支持 Anthropic / OpenAI / Qwen / Gemini。

    Usage::

        # 自动选择（按优先级）
        provider = LLMProvider.from_config()

        # 指定 Provider
        provider = LLMProvider(ProviderConfig(
            provider="gemini",
            api_key="AIza...",
            model="gemini-2.0-flash",
        ))

        # 发送消息
        response = provider.chat(
            system="你是 GIS 分析助手",
            messages=[{"role": "user", "content": "分析这个数据"}],
        )
        print(response.content)
    """

    def __init__(self, config: ProviderConfig, verbose: bool = False):
        self.config  = config
        self.verbose = verbose

    # ── 工厂方法 ─────────────────────────────────────────────────────────────

    @classmethod
    def from_config(
        cls,
        provider: Optional[str] = None,
        verbose:  bool = False,
    ) -> Optional["LLMProvider"]:
        """
        从 geoclaw_claude.config.Config 读取 API Key，自动选择或指定 Provider。

        Returns:
            LLMProvider 实例，若无可用 Key 则返回 None
        """
        try:
            from geoclaw_claude.config import Config
            cfg = Config.load()
        except Exception:
            return None

        # 构建候选列表（优先级顺序）
        # 环境变量 fallback：标准 API key 环境变量名 → 对应 provider
        import os as _os
        forced = getattr(cfg, "llm_provider", "") or _os.environ.get("GEOCLAW_LLM_PROVIDER", "") or provider
        env_anthropic = _os.environ.get("ANTHROPIC_API_KEY", "")
        env_gemini    = _os.environ.get("GEMINI_API_KEY", "") or _os.environ.get("GOOGLE_API_KEY", "")
        env_openai    = _os.environ.get("OPENAI_API_KEY", "")
        env_qwen      = _os.environ.get("QWEN_API_KEY", "") or _os.environ.get("DASHSCOPE_API_KEY", "")
        env_openai_model = _os.environ.get("GEOCLAW_OPENAI_MODEL", "")
        candidates = [
            ProviderConfig(
                provider=PROVIDER_ANTHROPIC,
                api_key=getattr(cfg, "anthropic_api_key", "") or env_anthropic,
                model=getattr(cfg, "anthropic_model", DEFAULT_MODELS[PROVIDER_ANTHROPIC]),
            ),
            ProviderConfig(
                provider=PROVIDER_GEMINI,
                api_key=getattr(cfg, "gemini_api_key", "") or env_gemini,
                model=getattr(cfg, "gemini_model", DEFAULT_MODELS[PROVIDER_GEMINI]),
            ),
            ProviderConfig(
                provider=PROVIDER_OPENAI,
                api_key=getattr(cfg, "openai_api_key", "") or env_openai,
                model=getattr(cfg, "openai_model", env_openai_model or DEFAULT_MODELS[PROVIDER_OPENAI]),
                base_url=getattr(cfg, "openai_base_url", ""),
            ),
            ProviderConfig(
                provider=PROVIDER_QWEN,
                api_key=getattr(cfg, "qwen_api_key", "") or env_qwen,
                model=getattr(cfg, "qwen_model", DEFAULT_MODELS[PROVIDER_QWEN]),
            ),
            # Ollama: local model, no API key required
            ProviderConfig(
                provider=PROVIDER_OLLAMA,
                api_key="ollama",
                model=getattr(cfg, "ollama_model", DEFAULT_MODELS[PROVIDER_OLLAMA]),
                base_url=getattr(cfg, "ollama_base_url", OLLAMA_DEFAULT_BASE_URL),
            ),
        ]

        # 若指定/强制 provider，只用该 provider
        if forced:
            for c in candidates:
                if c.provider == forced and c.is_valid:
                    return cls(c, verbose=verbose)
            if verbose:
                print(f"  [LLM] 指定 provider '{forced}' 无有效 Key，降级自动选择")

        # 自动选优先级最高的有效 provider
        for c in candidates:
            if c.is_valid:
                if verbose:
                    print(f"  [LLM] 自动选择 Provider: {c.provider} / {c.model}")
                return cls(c, verbose=verbose)

        return None

    # ── 主调用接口 ────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict[str, str]],
        system:   str = "",
        max_tokens: Optional[int] = None,
    ) -> Optional[LLMResponse]:
        """
        发送消息并获取回复。

        Args:
            messages  : 消息列表 [{"role": "user"/"assistant", "content": "..."}]
            system    : 系统提示
            max_tokens: 最大输出 token（覆盖 config 默认值）

        Returns:
            LLMResponse，失败时返回 None
        """
        mt = max_tokens or self.config.max_tokens

        try:
            if self.config.provider == PROVIDER_ANTHROPIC:
                return self._call_anthropic(messages, system, mt)
            elif self.config.provider == PROVIDER_GEMINI:
                return self._call_gemini(messages, system, mt)
            elif self.config.provider == PROVIDER_OLLAMA:
                return self._call_ollama(messages, system, mt)
            elif self.config.provider in (PROVIDER_OPENAI, PROVIDER_QWEN):
                return self._call_openai_compat(messages, system, mt)
            else:
                if self.verbose:
                    print(f"  [LLM] 未知 provider: {self.config.provider}")
                return None
        except Exception as e:
            if self.verbose:
                print(f"  [LLM] 调用失败 ({self.config.provider}): {e}")
            return None

    @property
    def provider_name(self) -> str:
        return self.config.provider

    @property
    def model_name(self) -> str:
        return self.config.model

    # ── Anthropic 调用 ───────────────────────────────────────────────────────

    def _call_anthropic(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int,
    ) -> Optional[LLMResponse]:
        try:
            import anthropic
        except ImportError:
            if self.verbose:
                print("  [LLM] anthropic 库未安装：pip install anthropic")
            return None

        api_messages = [
            m for m in messages if m.get("role") in ("user", "assistant")
        ]
        extra_system = "\n".join(
            m["content"] for m in messages if m.get("role") == "system"
        )
        full_system = (system + "\n" + extra_system).strip() if extra_system else system

        client = anthropic.Anthropic(api_key=self.config.api_key)
        resp = client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=full_system,
            messages=api_messages,
            temperature=self.config.temperature,
        )
        content = resp.content[0].text if resp.content else ""
        return LLMResponse(
            content=content,
            provider=PROVIDER_ANTHROPIC,
            model=self.config.model,
            tokens_in=resp.usage.input_tokens if resp.usage else 0,
            tokens_out=resp.usage.output_tokens if resp.usage else 0,
            raw=resp,
        )

    # ── Google Gemini 调用 ───────────────────────────────────────────────────

    def _call_gemini(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int,
    ) -> Optional[LLMResponse]:
        """
        调用 Google Gemini API（使用 google-genai SDK）。
        安装: pip install google-genai
        """
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            if self.verbose:
                print("  [LLM] google-genai 库未安装：pip install google-genai")
            return None

        client = genai.Client(api_key=self.config.api_key)

        # 构建 Gemini contents 格式
        # system 消息单独处理，其余 user/assistant 交替
        gemini_contents = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                # system 消息转为 user 消息（Gemini 通过 system_instruction 处理）
                continue
            gemini_role = "user" if role == "user" else "model"
            gemini_contents.append(
                genai_types.Content(
                    role=gemini_role,
                    parts=[genai_types.Part(text=content)]
                )
            )

        # 合并所有 system 消息为 system_instruction
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        full_system = "\n".join(filter(None, [system] + system_parts)).strip()

        config_kwargs = {
            "max_output_tokens": max_tokens,
            "temperature": self.config.temperature,
        }
        if full_system:
            config_kwargs["system_instruction"] = full_system

        try:
            resp = client.models.generate_content(
                model=self.config.model,
                contents=gemini_contents,
                config=genai_types.GenerateContentConfig(**config_kwargs),
            )
            content_text = ""
            if resp.candidates:
                candidate = resp.candidates[0]
                if candidate.content and candidate.content.parts:
                    content_text = "".join(
                        p.text for p in candidate.content.parts if hasattr(p, "text")
                    )

            tokens_in = tokens_out = 0
            if hasattr(resp, "usage_metadata") and resp.usage_metadata:
                tokens_in  = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
                tokens_out = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0

            return LLMResponse(
                content=content_text,
                provider=PROVIDER_GEMINI,
                model=self.config.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                raw=resp,
            )
        except Exception as e:
            if self.verbose:
                print(f"  [LLM] Gemini 调用失败: {e}")
            return None

    # ── OpenAI 兼容调用（含 Qwen）────────────────────────────────────────────

    def _call_openai_compat(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int,
    ) -> Optional[LLMResponse]:
        try:
            from openai import OpenAI
        except ImportError:
            if self.verbose:
                print("  [LLM] openai 库未安装：pip install openai")
            return None

        try:
            api_messages: List[Dict[str, str]] = []
            if system:
                api_messages.append({"role": "system", "content": system})
            for m in messages:
                role = m.get("role", "user")
                if role == "system":
                    api_messages.append({"role": "user", "content": f"[系统信息] {m['content']}"})
                else:
                    api_messages.append({"role": role, "content": m["content"]})

            client_kwargs: Dict[str, Any] = {"api_key": self.config.api_key}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url

            client = OpenAI(**client_kwargs)
            # gpt-5.x / o-series 使用 max_completion_tokens，不支持 temperature
            _new_api_models = ("o1", "o3", "o4", "gpt-5", "gpt-4.5", "gpt-4.1")
            use_completion_tokens = any(self.config.model.startswith(m) for m in _new_api_models)
            create_kwargs: Dict[str, Any] = {
                "model": self.config.model,
                "messages": api_messages,
            }
            if use_completion_tokens:
                create_kwargs["max_completion_tokens"] = max_tokens
            else:
                create_kwargs["max_tokens"] = max_tokens
                create_kwargs["temperature"] = self.config.temperature
            resp = client.chat.completions.create(**create_kwargs)
            content = resp.choices[0].message.content or "" if resp.choices else ""
            usage = resp.usage
            return LLMResponse(
                content=content,
                provider=self.config.provider,
                model=self.config.model,
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                raw=resp,
            )
        except Exception as e:
            print(f"  [LLM] OpenAI 调用失败 ({self.config.model}): {type(e).__name__}: {e}")
            return None

    # ── Ollama 本地模型调用（OpenAI 兼容接口）──────────────────────────────────

    def _call_ollama(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int,
    ) -> Optional[LLMResponse]:
        """
        调用本地 Ollama 服务（兼容 OpenAI /v1/chat/completions 接口）。

        前置条件:
          1. 安装 Ollama: https://ollama.com/download
          2. 启动服务: ollama serve  （默认端口 11434）
          3. 拉取模型: ollama pull llama3  （或 qwen2.5 / deepseek-r1 等）
          4. 设置 config: ollama_model = "llama3", ollama_base_url = "http://localhost:11434/v1"

        不需要 API Key，ollama_base_url 可自定义（支持局域网部署）。
        """
        try:
            from openai import OpenAI
        except ImportError:
            if self.verbose:
                print("  [LLM] openai 库未安装（Ollama 依赖此库）：pip install openai")
            return None

        api_messages: List[Dict[str, str]] = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for m in messages:
            role = m.get("role", "user")
            if role == "system":
                api_messages.append({"role": "system", "content": m["content"]})
            else:
                api_messages.append({"role": role, "content": m["content"]})

        try:
            client = OpenAI(
                api_key=self.config.api_key,   # "ollama"（dummy，Ollama 不校验）
                base_url=self.config.base_url,
            )
            resp = client.chat.completions.create(
                model=self.config.model,
                max_tokens=max_tokens,
                temperature=self.config.temperature,
                messages=api_messages,
            )
            content = resp.choices[0].message.content or "" if resp.choices else ""
            usage = resp.usage
            return LLMResponse(
                content=content,
                provider=PROVIDER_OLLAMA,
                model=self.config.model,
                tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
                tokens_out=getattr(usage, "completion_tokens", 0) or 0,
                raw=resp,
            )
        except Exception as e:
            if self.verbose:
                print(f"  [LLM] Ollama 调用失败: {e}")
                print(f"       请确认 Ollama 服务已启动 (ollama serve) 且模型已拉取 (ollama pull {self.config.model})")
            return None


# ── 辅助：清理 JSON 响应 ────────────────────────────────────────────────────

def clean_json_response(text: str) -> str:
    """清理 LLM 返回的 JSON，去除 Markdown 代码块包装。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_response(text: str) -> Optional[Dict]:
    """解析 LLM 返回的 JSON，失败返回 None。"""
    try:
        return json.loads(clean_json_response(text))
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return None
