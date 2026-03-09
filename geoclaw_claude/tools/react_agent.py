# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.tools.react_agent
---------------------------------
ReActAgent：LLM 自动工具调用引擎（Reason + Act 循环）。

流程
----
1. 用户自然语言任务 → LLM 分析，决定调用哪个工具
2. 执行工具，将结果作为"观察"返回给 LLM
3. LLM 根据观察决定继续调用工具或给出最终答案
4. 重复直到 LLM 给出 FINAL_ANSWER 或达到最大步数

输出格式约定（LLM 需遵守）
--------------------------
LLM 每步输出 JSON（纯文本，不加代码块）：

  推理步：
  {"thought": "...", "action": "shell", "action_input": {"cmd": "ls ~"}}

  结束步：
  {"thought": "...", "final_answer": "任务完成，结果是 ..."}

如果 LLM 输出不是合法 JSON，ReActAgent 会尝试修复，
多次失败后将原始输出作为 final_answer 返回。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base import ToolResult, ToolPermission
from .toolkit import LocalToolKit


# ── 步骤数据结构 ──────────────────────────────────────────────────────────────

@dataclass
class ReActStep:
    step:         int
    thought:      str
    action:       Optional[str]     = None  # 工具名（None 表示结束）
    action_input: Dict[str, Any]    = field(default_factory=dict)
    observation:  Optional[str]     = None  # 工具执行结果
    final_answer: Optional[str]     = None  # 最终答案
    duration:     float             = 0.0


@dataclass
class ReActResult:
    task:         str
    steps:        List[ReActStep]
    final_answer: str
    success:      bool
    total_duration: float
    max_steps_reached: bool = False

    def summary(self) -> str:
        lines = [f"任务: {self.task[:80]}",
                 f"步骤: {len(self.steps)} | 耗时: {self.total_duration:.2f}s | "
                 f"{'成功' if self.success else '失败'}"]
        for step in self.steps:
            if step.action:
                obs = (step.observation or "")[:100]
                lines.append(f"  步{step.step}: [{step.action}] → {obs}")
        lines.append(f"结论: {self.final_answer[:200]}")
        return "\n".join(lines)


# ── ReActAgent ────────────────────────────────────────────────────────────────

_REACT_SYSTEM = """\
你是 GeoClaw-claude ReAct 智能体。你可以通过调用本地工具来完成任务。

## 工作方式
每步输出一个 JSON 对象（只输出 JSON，不加代码块或解释）：

推理并调用工具：
{"thought": "我的分析...", "action": "工具名", "action_input": {"参数": "值"}}

得到最终答案：
{"thought": "任务完成", "final_answer": "结果说明..."}

## 规则
- 每步只做一件事
- 工具执行结果会作为"观察"反馈给你，用于下一步决策
- 观察到足够信息后立即给出 final_answer，不要继续调用工具
- 如果工具报错，分析原因并尝试修正参数或换其他工具
- final_answer 要对用户友好，用中文，包含关键数字/结果

{tools_section}
"""


class ReActAgent:
    """
    LLM 驱动的本地工具调用循环。

    Args:
        toolkit   : LocalToolKit 实例（包含权限设置）
        llm       : LLMProvider 实例（来自 geoclaw_claude.nl.llm_provider）
        max_steps : 最大推理步数（防止无限循环）
        verbose   : 是否打印每步进度
    """

    def __init__(
        self,
        toolkit:   LocalToolKit,
        llm:       Any,  # LLMProvider，避免循环导入
        max_steps: int = 12,
        verbose:   bool = False,
    ):
        self.toolkit   = toolkit
        self.llm       = llm
        self.max_steps = max_steps
        self.verbose   = verbose

    def run(self, task: str) -> ReActResult:
        """
        执行一个自然语言任务，自动调用工具直到完成。

        Args:
            task: 自然语言任务描述

        Returns:
            ReActResult
        """
        t0 = time.time()
        steps: List[ReActStep] = []

        system = _REACT_SYSTEM.format(tools_section=self.toolkit.specs_text())
        messages: List[Dict[str, str]] = [
            {"role": "user", "content": task}
        ]

        final_answer = ""
        max_steps_reached = False

        for step_i in range(1, self.max_steps + 1):
            ts = time.time()
            if self.verbose:
                print(f"  [ReAct] 步骤 {step_i}/{self.max_steps} ...")

            # LLM 推理
            try:
                resp = self.llm.chat(messages=messages, system=system)
                if resp is None:
                    raise RuntimeError("LLM 无响应")
                llm_text = resp.content
            except Exception as e:
                step = ReActStep(
                    step=step_i,
                    thought=f"LLM 调用失败: {e}",
                    final_answer=f"任务执行失败：LLM 无法响应（{e}）",
                    duration=time.time() - ts,
                )
                steps.append(step)
                final_answer = step.final_answer
                break

            # 解析 LLM 输出
            thought, action, action_input, fa = self._parse_llm_output(llm_text)
            step = ReActStep(step=step_i, thought=thought, duration=time.time() - ts)

            if fa is not None:
                # 最终答案
                step.final_answer = fa
                steps.append(step)
                final_answer = fa
                if self.verbose:
                    print(f"  [ReAct] 完成: {fa[:80]}")
                break

            if not action:
                # 无法解析，把原始输出当最终答案
                step.final_answer = llm_text
                steps.append(step)
                final_answer = llm_text
                break

            # 执行工具
            step.action       = action
            step.action_input = action_input
            if self.verbose:
                kw_str = ", ".join(f"{k}={str(v)[:40]}" for k, v in action_input.items())
                print(f"  [ReAct] 调用: {action}({kw_str})")

            tool_result = self.toolkit.run(action, **action_input)
            observation = tool_result.to_llm_text()
            step.observation = observation
            step.duration = time.time() - ts
            steps.append(step)

            if self.verbose:
                print(f"  [ReAct] 观察: {observation[:120]}")

            # 把 LLM 输出和工具结果追加到消息历史
            messages.append({"role": "assistant", "content": llm_text})
            messages.append({"role": "user",      "content": f"观察:\n{observation}\n\n继续。"})

        else:
            max_steps_reached = True
            final_answer = f"已执行 {self.max_steps} 步仍未完成，当前中间结论：\n" + \
                           (steps[-1].observation or steps[-1].thought if steps else "无")

        return ReActResult(
            task=task,
            steps=steps,
            final_answer=final_answer or "(无最终答案)",
            success=bool(final_answer) and not max_steps_reached,
            total_duration=time.time() - t0,
            max_steps_reached=max_steps_reached,
        )

    # ── 解析 LLM 输出 ─────────────────────────────────────────────────────────

    def _parse_llm_output(
        self, text: str
    ) -> Tuple[str, Optional[str], Dict, Optional[str]]:
        """
        解析 LLM 输出的 JSON。

        Returns:
            (thought, action, action_input, final_answer)
            final_answer != None 表示任务结束
        """
        # 清理代码块包装
        clean = text.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        clean = clean.strip()

        try:
            data = json.loads(clean)
        except json.JSONDecodeError:
            # 尝试提取第一个 {...} 块
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except Exception:
                    return (clean[:200], None, {}, None)
            else:
                return (clean[:200], None, {}, None)

        thought = data.get("thought", "")
        if "final_answer" in data:
            return (thought, None, {}, data["final_answer"])

        action = data.get("action", "")
        action_input = data.get("action_input", {})
        if not isinstance(action_input, dict):
            action_input = {}

        return (thought, action or None, action_input, None)
