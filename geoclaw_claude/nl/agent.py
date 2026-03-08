"""
geoclaw_claude/nl/agent.py
============================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

GeoAgent — 多轮自然语言对话 GIS 代理

将 NLProcessor（解析）+ NLExecutor（执行）组合为完整的对话代理，
支持多轮交互、上下文保持、模糊确认、结果解释。

核心功能:
  - 单入口 chat(text) 完成 解析→确认→执行→反馈 全流程
  - 跨轮对话上下文（图层、上一步结果、操作历史）
  - 低置信度时主动询问确认
  - 每轮自动更新 Memory 短期/长期记忆

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from geoclaw_claude.nl.processor import NLProcessor, ParsedIntent
from geoclaw_claude.nl.executor  import NLExecutor, ExecutionResult
from geoclaw_claude.nl.profile_manager import ProfileManager


# ── 对话消息 ──────────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    role:    str    # "user" | "agent"
    text:    str
    intent:  Optional[ParsedIntent]   = None
    result:  Optional[ExecutionResult] = None
    ts:      float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return f"[{self.role}] {self.text[:80]}"


# ── GeoAgent ──────────────────────────────────────────────────────────────────

class GeoAgent:
    """
    多轮自然语言 GIS 对话代理。

    Usage::

        agent = GeoAgent(api_key="sk-...")

        # 单轮
        print(agent.chat("加载 hospitals.geojson"))
        print(agent.chat("对医院做1公里缓冲区"))
        print(agent.chat("然后可视化"))

        # 批量（脚本模式）
        for text in ["加载...", "缓冲...", "制图..."]:
            result = agent.run(text)

        # 查看历史
        agent.print_history()
    """

    # 低置信度阈值：低于此值则请求确认
    CONFIRM_THRESHOLD = 0.55

    def __init__(
        self,
        api_key:    Optional[str] = None,
        use_ai:     Optional[bool] = None,
        verbose:    bool = False,
        session_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        soul_path:  Optional[str] = None,
        user_path:  Optional[str] = None,
    ):
        """
        Args:
            api_key   : Anthropic API Key
            use_ai    : True=AI模式, False=规则模式, None=自动
            verbose   : 打印调试信息
            session_id: 记忆会话 ID
            output_dir: 覆盖默认输出目录；None 则使用 config.output_dir
            soul_path : soul.md 路径；None 则使用 ~/.geoclaw_claude/soul.md
            user_path : user.md 路径；None 则使用 ~/.geoclaw_claude/user.md
        """
        # ── 加载 soul.md / user.md 个性化配置层 ──────────────────────────────
        self.profile = ProfileManager(
            soul_path=Path(soul_path) if soul_path else None,
            user_path=Path(user_path) if user_path else None,
            auto_create=True,
        ).load()

        self._proc = NLProcessor(api_key=api_key, use_ai=use_ai, verbose=verbose)
        self._exec = NLExecutor(memory_session=session_id, verbose=verbose,
                                output_dir=output_dir)
        self._history: List[ChatMessage] = []
        self._pending_intent: Optional[ParsedIntent] = None   # 等待确认的意图
        self.verbose = verbose

        mode = "AI" if self._proc._use_ai else "规则"
        # 使用 ProfileManager 生成个性化欢迎语
        welcome = self.profile.build_welcome_message(mode=mode)
        self._add_agent_msg(welcome)

    # ── 主对话入口 ────────────────────────────────────────────────────────────

    def chat(self, text: str) -> str:
        """
        输入一条自然语言指令，返回代理回复文本。

        完整流程:
          1. 记录用户消息
          2. 若有等待确认的意图，处理确认/拒绝
          3. 解析新意图
          4. 低置信度 → 返回确认问题
          5. 高置信度 → 执行并返回结果
        """
        text = text.strip()
        self._history.append(ChatMessage(role="user", text=text))

        # ── 处理待确认意图 ────────────────────────────────────────────────────
        if self._pending_intent is not None:
            return self._handle_confirmation(text)

        # ── 解析意图 ──────────────────────────────────────────────────────────
        context = self._build_context()
        intent  = self._proc.parse(text, context=context)

        # ── 置信度过低 → 请求确认 ────────────────────────────────────────────
        if intent.confidence < self.CONFIRM_THRESHOLD and intent.action != "unknown":
            self._pending_intent = intent
            reply = (
                f"我理解你想要：{intent.explanation}\n"
                f"（置信度 {intent.confidence:.0%}，操作：{intent.action}）\n"
                f"是否执行？(是/否)"
            )
            return self._add_agent_msg(reply, intent=intent)

        # ── 无法识别 ──────────────────────────────────────────────────────────
        if intent.action == "unknown":
            reply = (
                f"抱歉，我无法理解：「{text}」\n"
                f"提示：{intent.params.get('reason', '')}\n"
                f"输入「帮助」查看支持的操作。"
            )
            return self._add_agent_msg(reply, intent=intent)

        # ── 执行 ──────────────────────────────────────────────────────────────
        return self._execute_and_reply(intent)

    def run(self, text: str) -> ExecutionResult:
        """
        脚本模式：直接执行，不做确认，返回 ExecutionResult。
        """
        context = self._build_context()
        intent  = self._proc.parse(text, context=context)
        result  = self._exec.execute_intent(intent)
        self._history.append(ChatMessage(
            role="agent", text=result.summary(), intent=intent, result=result
        ))
        return result

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _handle_confirmation(self, text: str) -> str:
        intent = self._pending_intent
        self._pending_intent = None
        YES = {"是", "yes", "y", "确认", "执行", "好", "好的", "对", "ok"}
        NO  = {"否", "no", "n", "取消", "不", "不要", "算了"}
        t   = text.lower().strip()
        if t in YES or any(y in t for y in YES):
            return self._execute_and_reply(intent)
        elif t in NO or any(n in t for n in NO):
            return self._add_agent_msg("已取消操作。请重新描述你想做什么。")
        else:
            # 当做新指令处理
            self._pending_intent = None
            return self.chat(text)

    def _execute_and_reply(self, intent: ParsedIntent) -> str:
        er = self._exec.execute_intent(intent)
        if er.success:
            reply = self._format_success(intent, er)
        else:
            reply = self._format_error(intent, er)
        return self._add_agent_msg(reply, intent=intent, result=er)

    def _format_success(self, intent: ParsedIntent, er: ExecutionResult) -> str:
        lines = [f"✓ {er.message}"]
        # 展示结果摘要
        result = er.result
        if result is not None:
            if hasattr(result, "__len__") and hasattr(result, "data"):
                # GeoLayer
                try:
                    cols = list(result.data.columns)[:5]
                    lines.append(f"  要素数: {len(result)}  字段: {cols}")
                except Exception:
                    pass
            elif isinstance(result, dict):
                for k, v in list(result.items())[:4]:
                    if not callable(v):
                        lines.append(f"  {k}: {v}")
        # 提示当前可用图层
        available = self._exec.list_layers()
        if available:
            lines.append(f"  当前图层: {', '.join(available[-3:])}")
        lines.append(f"  耗时: {er.duration:.2f}s")
        return "\n".join(lines)

    def _format_error(self, intent: ParsedIntent, er: ExecutionResult) -> str:
        lines = [f"✗ 操作失败: {er.error}"]
        available = self._exec.list_layers()
        if available:
            lines.append(f"  可用图层: {', '.join(available)}")
        lines.append("  输入「帮助」查看使用示例。")
        return "\n".join(lines)

    def _build_context(self) -> Dict[str, Any]:
        """构建传给解析器的上下文（含上下文压缩 + soul/user 个性化）。"""
        ctx: Dict[str, Any] = {}
        layers = self._exec.list_layers()
        if layers:
            ctx["available_layers"] = layers
        last = self._exec.last_result
        if last is not None and hasattr(last, "name"):
            ctx["last_layer"] = last.name

        # ── 注入 soul.md 系统提示（行为边界，高优先级）───────────────────────
        soul_prompt = self.profile.build_system_prompt()
        if soul_prompt:
            ctx["soul_system_prompt"] = soul_prompt

        # ── 注入 user.md 偏好提示（软个性化，不覆盖 soul 边界）─────────────
        user_hint = self.profile.build_context_hint()
        if user_hint:
            ctx["user_profile_hint"] = user_hint

        # 构建对话消息列表并压缩
        messages = self._history_to_messages()
        if messages:
            try:
                from geoclaw_claude.nl.context_compress import (
                    compress_if_needed, CompressConfig
                )
                from geoclaw_claude.config import Config
                cfg = Config.load()
                cc = CompressConfig(
                    max_tokens=cfg.ctx_max_tokens,
                    target_tokens=cfg.ctx_target_tokens,
                    keep_recent=cfg.ctx_keep_recent,
                )
                compressed, report = compress_if_needed(
                    messages, verbose=cfg.ctx_compress_verbose, config=cc
                )
                if report.level_applied > 0:
                    ctx["compressed_history"] = compressed
                    ctx["compress_report"] = str(report)
                    if self.verbose:
                        print(f"  [Agent] 上下文已压缩: {report}")
                else:
                    recent = [m["content"] for m in messages[-4:]
                              if m.get("role") == "user"]
                    if recent:
                        ctx["recent_user_inputs"] = recent
            except Exception:
                recent = [m.text for m in self._history[-4:] if m.role == "user"]
                if recent:
                    ctx["recent_user_inputs"] = recent
        return ctx

    def _history_to_messages(self) -> List[Dict[str, str]]:
        """将 _history 转为 LLM messages 格式（供压缩器使用）。"""
        msgs = []
        for m in self._history:
            if m.role == "user":
                msgs.append({"role": "user", "content": m.text})
            elif m.role == "agent":
                msgs.append({"role": "assistant", "content": m.text})
        return msgs

    def context_stats(self) -> dict:
        """返回当前上下文 token 估算统计。"""
        try:
            from geoclaw_claude.nl.context_compress import estimate_messages_tokens
            msgs = self._history_to_messages()
            return {
                "messages": len(msgs),
                "estimated_tokens": estimate_messages_tokens(msgs),
                "provider": (self._proc._llm.provider_name
                             if self._proc._llm else "rule-based"),
            }
        except Exception:
            return {"messages": len(self._history), "estimated_tokens": 0}

    def _add_agent_msg(
        self,
        text:   str,
        intent: Optional[ParsedIntent]    = None,
        result: Optional[ExecutionResult] = None,
    ) -> str:
        self._history.append(ChatMessage(role="agent", text=text,
                                          intent=intent, result=result))
        return text

    # ── 历史 / 状态 ───────────────────────────────────────────────────────────

    def print_history(self) -> None:
        """打印对话历史。"""
        print("\n  ── 对话历史 " + "─" * 38)
        for msg in self._history:
            prefix = "  👤" if msg.role == "user" else "  🤖"
            for i, line in enumerate(msg.text.split("\n")):
                print(f"{prefix if i == 0 else '    '} {line}")
        print("  " + "─" * 48 + "\n")

    def status(self) -> dict:
        """返回代理当前状态。"""
        s = {
            "mode":            "AI" if self._proc._use_ai else "规则",
            "turns":           len([m for m in self._history if m.role == "user"]),
            "layers":          self._exec.list_layers(),
            "ops_success":     sum(1 for r in self._exec.history if r.success),
            "ops_total":       len(self._exec.history),
            "pending_confirm": self._pending_intent is not None,
            "soul_loaded":     bool(self.profile.soul.raw),
            "user_loaded":     bool(self.profile.user.raw),
            "user_role":       self.profile.user.role,
            "user_lang":       self.profile.user.preferred_lang,
        }
        return s

    def end(self, title: str = "") -> None:
        """结束会话，写入长期记忆。"""
        self._exec.end_session(title=title)

    def __repr__(self) -> str:
        s = self.status()
        return (f"GeoAgent(mode={s['mode']}, turns={s['turns']}, "
                f"layers={s['layers']})")
