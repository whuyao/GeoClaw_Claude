"""
geoclaw_claude/nl/context_compress.py
=======================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

上下文压缩器 (ContextCompressor)

当多轮对话的历史记录过长时，自动压缩上下文以避免超出 token 限制。

压缩策略（三级，按严重程度递进）:
  Level 1 — 摘要旧轮次 : 保留最近 N 轮原文，将更早的轮次摘要为一句话
  Level 2 — 语义去重   : 删除重复操作（连续相同 action 只保留最后一次）
  Level 3 — 强制截断   : 仅保留最近 K 轮，加上系统摘要

Token 估算: 按中文字符 × 2 + 英文词 × 1.3 粗估，保守估算（偏高）。

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Token 估算 ───────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """保守估算文本 token 数（适用于中英混合文本）。"""
    if not text:
        return 0
    # 中文字符（每字 ~2 token）
    zh_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    # 剩余英文/数字按空格分词后 ×1.3
    rest = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]', ' ', text)
    en_words = len(rest.split())
    return int(zh_chars * 2 + en_words * 1.3) + 4  # +4 for message overhead


def estimate_messages_tokens(messages: List[Dict[str, str]]) -> int:
    """估算消息列表的总 token 数。"""
    total = 0
    for m in messages:
        total += estimate_tokens(m.get("content", ""))
        total += estimate_tokens(m.get("role", ""))
        total += 4  # 消息元数据开销
    return total + 3  # 对话整体开销


# ── 压缩配置 ─────────────────────────────────────────────────────────────────

@dataclass
class CompressConfig:
    """上下文压缩配置。"""
    max_tokens:       int  = 6000    # 触发压缩的阈值（估算 token 数）
    target_tokens:    int  = 4000    # 压缩目标 token 数
    keep_recent:      int  = 6       # Level 1: 始终保留最近 N 条消息原文
    keep_hard_limit:  int  = 4       # Level 3: 强制截断只保留最近 K 条
    summary_max_len:  int  = 200     # 早期历史摘要最大字符数
    enable_level1:    bool = True    # 摘要旧轮次
    enable_level2:    bool = True    # 语义去重
    enable_level3:    bool = True    # 强制截断（最后手段）


# ── 压缩结果 ─────────────────────────────────────────────────────────────────

@dataclass
class CompressResult:
    """压缩操作的结果报告。"""
    original_tokens:   int
    compressed_tokens: int
    level_applied:     int   # 0=无需压缩, 1/2/3=应用了第N级
    messages_before:   int
    messages_after:    int
    summary_injected:  bool = False

    @property
    def ratio(self) -> float:
        if self.original_tokens == 0:
            return 1.0
        return self.compressed_tokens / self.original_tokens

    def __str__(self) -> str:
        if self.level_applied == 0:
            return f"[压缩] 无需压缩 ({self.original_tokens} tokens)"
        return (
            f"[压缩] Level {self.level_applied} | "
            f"{self.original_tokens} → {self.compressed_tokens} tokens "
            f"({self.ratio:.0%}) | "
            f"{self.messages_before} → {self.messages_after} 条消息"
        )


# ── 上下文压缩器 ─────────────────────────────────────────────────────────────

class ContextCompressor:
    """
    对话上下文压缩器。

    Usage::

        compressor = ContextCompressor()

        # 每轮对话前调用
        compressed_messages, report = compressor.compress(messages)
        print(report)  # [压缩] Level 1 | 8200 → 3900 tokens ...

        # 仅检查是否需要压缩
        if compressor.needs_compression(messages):
            messages, _ = compressor.compress(messages)
    """

    def __init__(self, config: Optional[CompressConfig] = None, verbose: bool = False):
        self.config  = config or CompressConfig()
        self.verbose = verbose

    # ── 公共接口 ─────────────────────────────────────────────────────────────

    def needs_compression(self, messages: List[Dict[str, str]]) -> bool:
        """检查是否需要压缩。"""
        return estimate_messages_tokens(messages) > self.config.max_tokens

    def compress(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
    ) -> Tuple[List[Dict[str, str]], CompressResult]:
        """
        压缩消息列表。

        Args:
            messages     : 消息列表，格式 [{"role": "user"/"assistant", "content": "..."}]
            system_prompt: 系统提示（用于计算剩余 token 预算）

        Returns:
            (compressed_messages, CompressResult)
        """
        system_tokens = estimate_tokens(system_prompt)
        original_tokens = estimate_messages_tokens(messages) + system_tokens
        n_before = len(messages)

        # 不需要压缩
        if original_tokens <= self.config.max_tokens:
            return messages, CompressResult(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                level_applied=0,
                messages_before=n_before,
                messages_after=n_before,
            )

        result_msgs = messages
        level_applied = 0
        summary_injected = False

        # ── Level 1: 摘要旧轮次 ──────────────────────────────────────────────
        if self.config.enable_level1:
            result_msgs, injected = self._level1_summarize(result_msgs)
            summary_injected = injected
            level_applied = 1
            cur_tokens = estimate_messages_tokens(result_msgs) + system_tokens
            if self.verbose:
                print(f"  [压缩L1] {cur_tokens} tokens after summarize")
            if cur_tokens <= self.config.target_tokens:
                return self._build_result(
                    messages, result_msgs, original_tokens, level_applied,
                    system_tokens, summary_injected
                )

        # ── Level 2: 语义去重 ────────────────────────────────────────────────
        if self.config.enable_level2:
            result_msgs = self._level2_dedup(result_msgs)
            level_applied = 2
            cur_tokens = estimate_messages_tokens(result_msgs) + system_tokens
            if self.verbose:
                print(f"  [压缩L2] {cur_tokens} tokens after dedup")
            if cur_tokens <= self.config.target_tokens:
                return self._build_result(
                    messages, result_msgs, original_tokens, level_applied,
                    system_tokens, summary_injected
                )

        # ── Level 3: 强制截断 ────────────────────────────────────────────────
        if self.config.enable_level3:
            result_msgs = self._level3_hard_truncate(result_msgs)
            level_applied = 3
            if self.verbose:
                cur_tokens = estimate_messages_tokens(result_msgs) + system_tokens
                print(f"  [压缩L3] {cur_tokens} tokens after hard truncate")

        return self._build_result(
            messages, result_msgs, original_tokens, level_applied,
            system_tokens, summary_injected
        )

    # ── Level 1: 摘要旧轮次 ──────────────────────────────────────────────────

    def _level1_summarize(
        self, messages: List[Dict[str, str]]
    ) -> Tuple[List[Dict[str, str]], bool]:
        """将早期消息压缩为一条摘要，保留最近 keep_recent 条原文。"""
        keep = self.config.keep_recent
        if len(messages) <= keep:
            return messages, False

        old_msgs = messages[:-keep]
        recent   = messages[-keep:]

        # 生成文字摘要（本地，无需 API）
        summary = self._make_local_summary(old_msgs)
        summary_msg = {
            "role": "system",
            "content": f"[早期对话摘要]\n{summary}\n[以上为之前操作的摘要，后续对话继续]"
        }

        return [summary_msg] + recent, True

    def _make_local_summary(self, messages: List[Dict[str, str]]) -> str:
        """本地生成摘要（不调用 API，基于关键词提取）。"""
        lines = []
        ops_seen = []

        for m in messages:
            content = m.get("content", "")
            role    = m.get("role", "user")
            if role == "user":
                # 提取操作关键词
                short = content[:100].replace("\n", " ")
                ops_seen.append(f"用户: {short}")
            elif role in ("assistant", "agent"):
                # 提取成功/失败信息
                if "✓" in content or "成功" in content or "完成" in content:
                    short = content[:80].replace("\n", " ")
                    lines.append(f"完成: {short}")
                elif "✗" in content or "失败" in content or "错误" in content:
                    short = content[:60].replace("\n", " ")
                    lines.append(f"失败: {short}")

        # 合并操作序列
        all_lines = ops_seen[-8:] + lines[-4:]  # 最多保留最近8条操作+4条结果
        summary = "\n".join(all_lines)

        # 截断到最大长度
        if len(summary) > self.config.summary_max_len:
            summary = summary[:self.config.summary_max_len] + "…（已截断）"
        return summary or "（早期对话内容已压缩）"

    # ── Level 2: 语义去重 ────────────────────────────────────────────────────

    def _level2_dedup(
        self, messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """删除连续的重复/相似操作（用户消息内容重复超过 80%）。"""
        if len(messages) <= 2:
            return messages

        result = [messages[0]]
        for i in range(1, len(messages)):
            cur  = messages[i]
            prev = messages[i - 1]
            # 只对 user 消息做去重
            if (cur.get("role") == "user"
                    and prev.get("role") == "user"
                    and self._similarity(cur["content"], prev["content"]) > 0.8):
                # 用新的替换旧的
                result[-1] = cur
            else:
                result.append(cur)
        return result

    def _similarity(self, a: str, b: str) -> float:
        """简单字符重叠率相似度。"""
        if not a or not b:
            return 0.0
        set_a = set(a.lower().split())
        set_b = set(b.lower().split())
        if not set_a or not set_b:
            # 字符级
            set_a = set(a[:50])
            set_b = set(b[:50])
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    # ── Level 3: 强制截断 ────────────────────────────────────────────────────

    def _level3_hard_truncate(
        self, messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """仅保留最近 K 条消息，加上一条截断提示。"""
        keep = self.config.keep_hard_limit
        if len(messages) <= keep:
            return messages

        truncated_count = len(messages) - keep
        notice = {
            "role": "system",
            "content": f"[注意：早期 {truncated_count} 条对话记录已被截断以控制上下文长度]"
        }
        return [notice] + messages[-keep:]

    # ── 辅助 ────────────────────────────────────────────────────────────────

    def _build_result(
        self,
        original: List[Dict[str, str]],
        compressed: List[Dict[str, str]],
        orig_tokens: int,
        level: int,
        system_tokens: int,
        summary_injected: bool,
    ) -> Tuple[List[Dict[str, str]], CompressResult]:
        comp_tokens = estimate_messages_tokens(compressed) + system_tokens
        return compressed, CompressResult(
            original_tokens=orig_tokens,
            compressed_tokens=comp_tokens,
            level_applied=level,
            messages_before=len(original),
            messages_after=len(compressed),
            summary_injected=summary_injected,
        )


# ── 便捷函数 ─────────────────────────────────────────────────────────────────

_default_compressor: Optional[ContextCompressor] = None


def get_compressor(config: Optional[CompressConfig] = None) -> ContextCompressor:
    """获取全局默认压缩器（单例）。"""
    global _default_compressor
    if _default_compressor is None or config is not None:
        _default_compressor = ContextCompressor(config)
    return _default_compressor


def compress_if_needed(
    messages: List[Dict[str, str]],
    system_prompt: str = "",
    config: Optional[CompressConfig] = None,
    verbose: bool = False,
) -> Tuple[List[Dict[str, str]], CompressResult]:
    """
    便捷函数：检查并按需压缩消息列表。

    Usage::
        messages, report = compress_if_needed(messages, system_prompt)
        if report.level_applied > 0:
            print(report)
    """
    compressor = ContextCompressor(config or CompressConfig(), verbose=verbose)
    return compressor.compress(messages, system_prompt)
