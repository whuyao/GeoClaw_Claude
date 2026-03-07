# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.memory
======================
GeoClaw-claude 记忆系统。

  ShortTermMemory  — 会话内短期记忆（操作日志 + 中间结果缓存）
  LongTermMemory   — 跨会话长期记忆（持久化知识库）
  MemoryManager    — 统一管理入口
  get_memory()     — 获取全局单例
"""

from geoclaw_claude.memory.short_term import ShortTermMemory, MemoryEntry, OperationRecord
from geoclaw_claude.memory.long_term  import LongTermMemory,  LongTermEntry, CATEGORIES
from geoclaw_claude.memory.manager    import MemoryManager,   get_memory, reset_memory

__all__ = [
    "ShortTermMemory", "MemoryEntry", "OperationRecord",
    "LongTermMemory",  "LongTermEntry", "CATEGORIES",
    "MemoryManager",   "get_memory",    "reset_memory",
]
