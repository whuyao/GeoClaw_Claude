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
  - qwen      : 通义千问（qwen-max / qwen-plus / qwen-turbo），OpenAI 兼容接口
  - gemini    : Google Gemini（gemini-2.0-flash / gemini-1.5-pro 等）
  - ollama    : 本地大模型（llama3 / qwen2.5 / deepseek-r1 等），无需 API Key

Provider 选择优先级（自动模式）:
  1. 已设置 anthropic_api_key → anthropic
  2. 已设置 gemini_api_key    → gemini
  3. 已设置 openai_api_key    → openai
  4. 已设置 qwen_api_key      → qwen
  5. ollama_base_url 可达      → ollama（本地离线优先）
  6. 均不可用                 → 降级规则模式（返回 None）

Ollama 快速上手:
  # 安装并启动 Ollama 服务（默认端口 11434）
  # 拉取模型: ollama pull llama3 / qwen2.5 / deepseek-r1 等
  # 在 geoclaw config 中设置:
  #   ollama_base_url = "http://localhost:11434"
  #   ollama_model    = "llama3"          # 或 qwen2.5, deepseek-r1:7b ...
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
    PROVIDER_QWEN:      "qwen-plus",
    PROVIDER_GEMINI:    "gemini-2.0-flash",
    PROVIDER_OLLAMA:    "llama3",
}

# Gemini 可用模型列表（供 onboard 提示）
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.5-pro-preview-03-25",
]

# Ollama 常用模型列表（供 onboard 提示）
OLLAMA_MODELS = [
    "llama3",
    "llama3.1",
    "llama3.2",
    "qwen2.5",
    "qwen2.5:7b",
    "qwen2.5:14b",
    "deepseek-r1",
    "deepseek-r1:7b",
    "deepseek-r1:14b",
    "mistral",
    "gemma3",
    "phi4",
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
        forced = getattr(cfg, "llm_provider", "") or provider
        candidates = [
            ProviderConfig(
                provider=PROVIDER_ANTHROPIC,
                api_key=getattr(cfg, "anthropic_api_key", ""),
                model=getattr(cfg, "anthropic_model", DEFAULT_MODELS[PROVIDER_ANTHROPIC]),
            ),
            ProviderConfig(
                provider=PROVIDER_GEMINI,
                api_key=getattr(cfg, "gemini_api_key", ""),
                model=getattr(cfg, "gemini_model", DEFAULT_MODELS[PROVIDER_GEMINI]),
            ),
            ProviderConfig(
                provider=PROVIDER_OPENAI,
                api_key=getattr(cfg, "openai_api_key", ""),
                model=getattr(cfg, "openai_model", DEFAULT_MODELS[PROVIDER_OPENAI]),
                base_url=getattr(cfg, "openai_base_url", ""),
            ),
            ProviderConfig(
                provider=PROVIDER_QWEN,
                api_key=getattr(cfg, "qwen_api_key", ""),
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
            provider=self.config.provider,
            model=self.config.model,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            raw=resp,
        )

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
