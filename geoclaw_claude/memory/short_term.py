"""
geoclaw_claude/memory/short_term.py
====================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

短期记忆（Short-Term Memory）模块。

短期记忆存活于单次任务会话（Session）期间，会话结束后自动清除或转入长期记忆。

功能:
  - 记录当前会话的操作序列（OperationLog）
  - 缓存中间分析结果（layer、栅格、统计值）
  - 维护会话上下文（当前项目、活跃图层、参数历史）
  - 支持"回放"（replay）操作序列

设计原则:
  - 轻量内存存储，不写磁盘（除非显式调用 flush_to_long_term）
  - 线程安全（使用 threading.Lock）
  - 自动 TTL 过期（默认 24h）

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import time
import threading
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ── 数据类 ──────────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """单条记忆条目。"""
    key:        str
    value:      Any
    category:   str        = "general"    # operation | result | context | param
    timestamp:  float      = field(default_factory=time.time)
    ttl:        float      = 86400.0      # 秒，默认 24h，0 = 永不过期
    tags:       List[str]  = field(default_factory=list)
    metadata:   Dict       = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return (time.time() - self.timestamp) > self.ttl

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    def to_dict(self) -> dict:
        return {
            "key":       self.key,
            "value":     self.value if _is_serializable(self.value) else str(self.value),
            "category":  self.category,
            "timestamp": self.timestamp,
            "ttl":       self.ttl,
            "tags":      self.tags,
            "metadata":  self.metadata,
        }


@dataclass
class OperationRecord:
    """单次操作记录，构成操作序列。"""
    op_id:      int
    func_name:  str
    args_repr:  str
    result_key: Optional[str]    = None
    duration:   float            = 0.0
    success:    bool             = True
    error:      Optional[str]    = None
    timestamp:  float            = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# ── 短期记忆主类 ────────────────────────────────────────────────────────────

class ShortTermMemory:
    """
    短期记忆：单次任务会话内的操作记录与中间结果缓存。

    Usage::

        stm = ShortTermMemory(session_id="session_20250307")

        # 记录操作
        stm.log_operation("buffer", "hospitals, 1000m", result_key="buf_result")

        # 存储中间结果
        stm.store("buf_result", my_layer, category="result")

        # 读取
        layer = stm.retrieve("buf_result")

        # 获取操作序列
        ops = stm.get_operation_log()

        # 生成会话摘要（供转入长期记忆）
        summary = stm.summarize()
    """

    def __init__(
        self,
        session_id:    Optional[str] = None,
        default_ttl:   float = 86400.0,
        max_entries:   int   = 500,
    ):
        self.session_id   = session_id or f"session_{int(time.time())}"
        self.default_ttl  = default_ttl
        self.max_entries  = max_entries
        self.created_at   = time.time()

        self._store:     Dict[str, MemoryEntry]  = {}
        self._ops:       List[OperationRecord]   = []
        self._op_counter = 0
        self._lock       = threading.RLock()   # RLock 支持同一线程重入，避免死锁

    # ── 存储 / 读取 ─────────────────────────────────────────────────────────

    def store(
        self,
        key:      str,
        value:    Any,
        category: str       = "general",
        ttl:      float     = -1,
        tags:     List[str] = None,
        metadata: dict      = None,
    ) -> None:
        """存储一条记忆。"""
        with self._lock:
            if len(self._store) >= self.max_entries:
                self._evict_oldest()
            self._store[key] = MemoryEntry(
                key=key,
                value=value,
                category=category,
                ttl=ttl if ttl >= 0 else self.default_ttl,
                tags=tags or [],
                metadata=metadata or {},
            )

    def retrieve(self, key: str, default: Any = None) -> Any:
        """读取一条记忆，过期则返回 default。"""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            if entry.is_expired:
                del self._store[key]
                return default
            return entry.value

    def get_entry(self, key: str) -> Optional[MemoryEntry]:
        """获取完整的 MemoryEntry（含元数据）。"""
        with self._lock:
            entry = self._store.get(key)
            if entry and not entry.is_expired:
                return entry
            return None

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def has(self, key: str) -> bool:
        entry = self._store.get(key)
        return entry is not None and not entry.is_expired

    # ── 操作日志 ─────────────────────────────────────────────────────────────

    def log_operation(
        self,
        func_name:  str,
        args_repr:  str,
        result_key: Optional[str] = None,
        duration:   float = 0.0,
        success:    bool  = True,
        error:      Optional[str] = None,
    ) -> int:
        """记录一次函数调用。返回 op_id。"""
        with self._lock:
            self._op_counter += 1
            op = OperationRecord(
                op_id=self._op_counter,
                func_name=func_name,
                args_repr=args_repr,
                result_key=result_key,
                duration=duration,
                success=success,
                error=error,
            )
            self._ops.append(op)
            return self._op_counter

    def get_operation_log(self, only_success: bool = False) -> List[OperationRecord]:
        """返回操作序列。"""
        with self._lock:
            if only_success:
                return [op for op in self._ops if op.success]
            return list(self._ops)

    def get_last_operation(self) -> Optional[OperationRecord]:
        with self._lock:
            return self._ops[-1] if self._ops else None

    # ── 上下文快捷方式 ────────────────────────────────────────────────────────

    def set_context(self, key: str, value: Any) -> None:
        """设置会话上下文（TTL=0，会话期间永不过期）。"""
        self.store(key, value, category="context", ttl=0)

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.retrieve(key, default)

    def set_active_layer(self, name: str, layer: Any) -> None:
        self.set_context(f"_active_layer_{name}", layer)

    def get_active_layer(self, name: str) -> Any:
        return self.get_context(f"_active_layer_{name}")

    # ── 按类别查询 ────────────────────────────────────────────────────────────

    def list_keys(self, category: Optional[str] = None) -> List[str]:
        with self._lock:
            if category:
                return [k for k, v in self._store.items()
                        if v.category == category and not v.is_expired]
            return [k for k, v in self._store.items() if not v.is_expired]

    def list_by_tag(self, tag: str) -> List[MemoryEntry]:
        with self._lock:
            return [v for v in self._store.values()
                    if tag in v.tags and not v.is_expired]

    # ── 摘要生成（供转入长期记忆） ────────────────────────────────────────────

    def summarize(self) -> dict:
        """
        生成本次会话的摘要，用于转入长期记忆。

        Returns:
            dict: 包含会话元信息、操作序列摘要、存储的 key 列表。
        """
        with self._lock:
            ops_success = [op for op in self._ops if op.success]
            ops_failed  = [op for op in self._ops if not op.success]

            # 操作频率统计
            op_freq: Dict[str, int] = {}
            for op in self._ops:
                op_freq[op.func_name] = op_freq.get(op.func_name, 0) + 1

            # 耗时统计
            total_duration = sum(op.duration for op in self._ops)

            # 分类统计
            categories: Dict[str, int] = {}
            for entry in self._store.values():
                if not entry.is_expired:
                    categories[entry.category] = categories.get(entry.category, 0) + 1

            return {
                "session_id":     self.session_id,
                "created_at":     self.created_at,
                "summarized_at":  time.time(),
                "duration_sec":   time.time() - self.created_at,
                "operations": {
                    "total":         len(self._ops),
                    "success":       len(ops_success),
                    "failed":        len(ops_failed),
                    "total_duration": round(total_duration, 3),
                    "frequency":     op_freq,
                    "sequence":      [op.to_dict() for op in self._ops],
                },
                "memory_store": {
                    "total_entries": len([v for v in self._store.values() if not v.is_expired]),
                    "categories":    categories,
                    "keys":          self.list_keys(),
                },
                "errors": [
                    {"op_id": op.op_id, "func": op.func_name, "error": op.error}
                    for op in ops_failed
                ],
            }

    # ── 清理 ─────────────────────────────────────────────────────────────────

    def purge_expired(self) -> int:
        """清除所有过期条目，返回清除数量。"""
        with self._lock:
            expired = [k for k, v in self._store.items() if v.is_expired]
            for k in expired:
                del self._store[k]
            return len(expired)

    def clear(self) -> None:
        """清空短期记忆（保留操作日志）。"""
        with self._lock:
            self._store.clear()

    def reset(self) -> None:
        """完全重置（清空所有内容）。"""
        with self._lock:
            self._store.clear()
            self._ops.clear()
            self._op_counter = 0

    def _evict_oldest(self) -> None:
        """LRU 淘汰：删除最旧的 10% 条目。"""
        sorted_keys = sorted(
            self._store.keys(),
            key=lambda k: self._store[k].timestamp,
        )
        evict_n = max(1, len(sorted_keys) // 10)
        for k in sorted_keys[:evict_n]:
            del self._store[k]

    # ── 序列化（用于调试/导出） ───────────────────────────────────────────────

    def to_json(self) -> str:
        summary = self.summarize()
        return json.dumps(summary, ensure_ascii=False, indent=2)

    def __repr__(self) -> str:
        return (
            f"ShortTermMemory(session={self.session_id!r}, "
            f"entries={len(self._store)}, ops={len(self._ops)})"
        )

    def __len__(self) -> int:
        return len(self._store)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _is_serializable(value: Any) -> bool:
    """判断值是否 JSON 可序列化。"""
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False
