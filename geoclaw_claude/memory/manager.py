"""
geoclaw_claude/memory/manager.py
===================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

MemoryManager — 统一记忆管理入口。

将短期记忆（ShortTermMemory）和长期记忆（LongTermMemory）整合为一个
统一接口，供 GeoLayer、SkillContext、CLI 等模块直接调用。

核心流程::

    1. 任务开始 → manager.start_session()   创建/恢复短期记忆
    2. 任务执行 → manager.remember()        记录操作与中间结果
    3. 任务结束 → manager.end_session()     生成摘要 → 转入长期记忆
    4. 跨会话   → manager.recall()          从长期记忆检索知识

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from geoclaw_claude.memory.short_term import ShortTermMemory
from geoclaw_claude.memory.long_term  import LongTermMemory, LongTermEntry


class MemoryManager:
    """
    GeoClaw-claude 统一记忆管理器。

    同时管理短期（会话内）和长期（跨会话）记忆，
    提供简洁的 remember / recall 接口。

    Usage::

        # 通常使用全局单例
        from geoclaw_claude.memory import get_memory
        mem = get_memory()

        # 开始一个新任务会话
        mem.start_session("wuhan_hospital_analysis")

        # 记录操作
        mem.log_op("buffer", "hospitals 1km")

        # 存储中间结果
        mem.remember("buf_hospitals", my_layer)

        # 读取
        layer = mem.recall_short("buf_hospitals")

        # 从长期记忆检索
        results = mem.recall("医院 分布")

        # 结束会话（自动转入长期记忆）
        mem.end_session(title="武汉医院缓冲区分析", tags=["wuhan","hospital"])
    """

    def __init__(
        self,
        memory_dir:     Optional[Path] = None,
        auto_flush:     bool           = True,
        session_ttl:    float          = 86400.0,
    ):
        """
        Args:
            memory_dir  : 长期记忆存储目录（默认 ~/.geoclaw_claude/memory）
            auto_flush  : end_session 时是否自动将摘要转入长期记忆
            session_ttl : 短期记忆条目默认 TTL（秒）
        """
        self.auto_flush  = auto_flush
        self.session_ttl = session_ttl
        self._lock       = threading.RLock()

        self._ltm = LongTermMemory(memory_dir=memory_dir)
        self._stm: Optional[ShortTermMemory] = None
        self._current_session_id: Optional[str] = None

    # ── 会话管理 ──────────────────────────────────────────────────────────────

    def start_session(self, session_id: Optional[str] = None) -> str:
        """
        开始一个新的任务会话，创建短期记忆实例。

        Args:
            session_id: 会话标识（默认自动生成）

        Returns:
            session_id (str)
        """
        with self._lock:
            sid = session_id or f"session_{time.strftime('%Y%m%d_%H%M%S')}"
            self._stm = ShortTermMemory(
                session_id=sid,
                default_ttl=self.session_ttl,
            )
            self._current_session_id = sid
            print(f"  [Memory] 会话开始: {sid}")
            return sid

    def end_session(
        self,
        title:      str        = "",
        tags:       List[str]  = None,
        importance: float      = 0.5,
        flush:      Optional[bool] = None,
    ) -> Optional[str]:
        """
        结束当前会话。

        1. 生成短期记忆摘要
        2. 若 auto_flush=True（或 flush=True），将摘要转入长期记忆
        3. 清空短期记忆

        Args:
            title     : 长期记忆标题
            tags      : 长期记忆标签
            importance: 重要性评分 0~1
            flush     : 覆盖 auto_flush 设置

        Returns:
            长期记忆 entry_id（若已 flush），否则 None
        """
        with self._lock:
            if self._stm is None:
                print("  [Memory] 无活跃会话")
                return None

            summary   = self._stm.summarize()
            should_flush = flush if flush is not None else self.auto_flush

            entry_id = None
            if should_flush:
                entry_id = self._ltm.flush_from_session(
                    session_summary=summary,
                    title=title or f"会话复盘 — {self._current_session_id}",
                    tags=tags,
                    importance=importance,
                )
                print(f"  [Memory] 会话已转入长期记忆: {entry_id}")

            ops_total = summary["operations"]["total"]
            ops_ok    = summary["operations"]["success"]
            print(f"  [Memory] 会话结束: {self._current_session_id} "
                  f"({ops_ok}/{ops_total} 操作成功)")

            self._stm.reset()
            self._current_session_id = None
            return entry_id

    @property
    def current_session(self) -> Optional[str]:
        return self._current_session_id

    @property
    def stm(self) -> Optional[ShortTermMemory]:
        return self._stm

    @property
    def ltm(self) -> LongTermMemory:
        return self._ltm

    # ── 短期记忆操作 ─────────────────────────────────────────────────────────

    def _ensure_session(self) -> ShortTermMemory:
        """确保有活跃会话，没有则自动创建。"""
        if self._stm is None:
            self.start_session()
        return self._stm

    def remember(
        self,
        key:      str,
        value:    Any,
        category: str       = "result",
        tags:     List[str] = None,
        ttl:      float     = -1,
    ) -> None:
        """
        将值存入短期记忆。

        Args:
            key     : 记忆键名
            value   : 任意值（GeoLayer / ndarray / dict / ...）
            category: 分类（result / context / param / general）
            tags    : 标签
            ttl     : 生存时间（秒），-1 使用默认
        """
        self._ensure_session().store(
            key=key, value=value, category=category,
            tags=tags, ttl=ttl,
        )

    def recall_short(self, key: str, default: Any = None) -> Any:
        """从短期记忆读取。"""
        if self._stm is None:
            return default
        return self._stm.retrieve(key, default)

    def log_op(
        self,
        func_name:  str,
        args_repr:  str,
        result_key: Optional[str] = None,
        duration:   float         = 0.0,
        success:    bool          = True,
        error:      Optional[str] = None,
    ) -> int:
        """记录一次操作到短期记忆操作日志。"""
        return self._ensure_session().log_operation(
            func_name=func_name,
            args_repr=args_repr,
            result_key=result_key,
            duration=duration,
            success=success,
            error=error,
        )

    def set_context(self, key: str, value: Any) -> None:
        """设置会话上下文（持续整个会话，不过期）。"""
        self._ensure_session().set_context(key, value)

    def get_context(self, key: str, default: Any = None) -> Any:
        if self._stm is None:
            return default
        return self._stm.get_context(key, default)

    def get_ops(self, only_success: bool = False):
        if self._stm is None:
            return []
        return self._stm.get_operation_log(only_success=only_success)

    # ── 长期记忆操作 ─────────────────────────────────────────────────────────

    def learn(
        self,
        title:      str,
        content:    Any,
        category:   str        = "knowledge",
        tags:       List[str]  = None,
        importance: float      = 0.7,
        source:     str        = "",
    ) -> str:
        """
        直接向长期记忆存入知识条目。

        Args:
            title     : 知识标题
            content   : 知识内容（dict / str / list）
            category  : 类别（knowledge / dataset / preference / error）
            tags      : 标签
            importance: 重要性 0~1
            source    : 来源说明

        Returns:
            entry_id
        """
        eid = self._ltm.store(
            title=title,
            content=content,
            category=category,
            tags=tags,
            importance=importance,
            source=source or self._current_session_id or "",
        )
        print(f"  [Memory] 已学习: [{eid}] {title}")
        return eid

    def recall(
        self,
        query:    str,
        category: Optional[str] = None,
        top_k:    int           = 5,
    ) -> List[LongTermEntry]:
        """
        从长期记忆检索。

        Args:
            query   : 关键词（空格分隔，AND 逻辑）
            category: 限定类别（None 则全类别）
            top_k   : 最多返回条数

        Returns:
            List[LongTermEntry]
        """
        return self._ltm.search(query, category=category, top_k=top_k)

    def recall_recent(self, n: int = 5, category: Optional[str] = None) -> List[LongTermEntry]:
        """获取最近的 n 条长期记忆。"""
        return self._ltm.get_recent(n=n, category=category)

    def recall_important(self, n: int = 5, threshold: float = 0.6) -> List[LongTermEntry]:
        """获取最重要的 n 条长期记忆。"""
        return self._ltm.get_important(n=n, threshold=threshold)

    def forget(self, entry_id: str) -> bool:
        """从长期记忆删除一条记忆。"""
        return self._ltm.delete(entry_id)

    # ── 统计与摘要 ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """返回记忆系统当前状态。"""
        stm_info = {}
        if self._stm:
            stm_info = {
                "session_id":  self._stm.session_id,
                "entries":     len(self._stm),
                "ops":         len(self._stm.get_operation_log()),
                "age_sec":     round(time.time() - self._stm.created_at, 1),
            }
        return {
            "short_term": stm_info or "无活跃会话",
            "long_term":  self._ltm.stats(),
        }

    def print_status(self) -> None:
        """打印记忆系统状态（友好格式）。"""
        s = self.status()
        print("\n  ╔══ GeoClaw Memory Status ══════════════════╗")
        stm = s["short_term"]
        if isinstance(stm, dict):
            print(f"  ║ 短期记忆  会话: {stm['session_id']}")
            print(f"  ║           条目: {stm['entries']}  操作: {stm['ops']}  "
                  f"已运行 {stm['age_sec']}s")
        else:
            print(f"  ║ 短期记忆  {stm}")
        ltm = s["long_term"]
        print(f"  ║ 长期记忆  总计: {ltm['total_entries']} 条")
        for cat, cnt in ltm["by_category"].items():
            print(f"  ║           {cat}: {cnt}")
        print(f"  ║           均重要性: {ltm['avg_importance']}")
        print(f"  ╚═══════════════════════════════════════════╝\n")

    def __repr__(self) -> str:
        return (
            f"MemoryManager(session={self._current_session_id!r}, "
            f"ltm={len(self._ltm)})"
        )


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_global_memory: Optional[MemoryManager] = None
_global_lock   = threading.RLock()


def get_memory(memory_dir: Optional[Path] = None) -> MemoryManager:
    """
    获取全局 MemoryManager 单例。

    Usage::

        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        mem.start_session("my_task")
    """
    global _global_memory
    with _global_lock:
        if _global_memory is None:
            _global_memory = MemoryManager(memory_dir=memory_dir)
        return _global_memory


def reset_memory() -> None:
    """重置全局单例（主要用于测试）。"""
    global _global_memory
    with _global_lock:
        _global_memory = None
