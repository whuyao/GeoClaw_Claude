"""
geoclaw_claude/memory/long_term.py
====================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

长期记忆（Long-Term Memory）模块。

长期记忆持久化存储于磁盘（~/.geoclaw_claude/memory/），跨会话保留。
短期记忆通过 flush() 转入长期记忆后，由 LongTermMemory 负责索引与检索。

功能:
  - 持久化存储 JSON 格式记忆条目
  - 按类别（知识库 / 任务复盘 / 数据档案 / 用户偏好）分区管理
  - 全文关键词检索 + 标签检索
  - 定期压缩（合并同类旧记忆，防止无限增长）
  - 重要性评分（importance score）自动排序

存储结构::

    ~/.geoclaw_claude/memory/
    ├── index.json          # 记忆索引（快速检索）
    ├── knowledge/          # 分析知识与规律
    │   └── *.json
    ├── sessions/           # 任务复盘（每次会话摘要）
    │   └── *.json
    ├── datasets/           # 数据档案（数据集特征、质量记录）
    │   └── *.json
    └── preferences/        # 用户偏好与习惯
        └── *.json

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import json
import time
import uuid
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


# ── 记忆类别 ─────────────────────────────────────────────────────────────────

CATEGORIES = {
    "knowledge":   "分析知识与规律",
    "session":     "任务复盘摘要",
    "dataset":     "数据档案",
    "preference":  "用户偏好",
    "error":       "错误与修复记录",
}


# ── 数据类 ───────────────────────────────────────────────────────────────────

@dataclass
class LongTermEntry:
    """长期记忆条目。"""
    id:          str
    title:       str
    content:     Any
    category:    str           = "knowledge"
    tags:        List[str]     = field(default_factory=list)
    importance:  float         = 0.5        # 0~1，越高越重要
    created_at:  float         = field(default_factory=time.time)
    updated_at:  float         = field(default_factory=time.time)
    access_count: int          = 0
    source:      str           = ""         # 来源（session_id / 手动输入等）
    metadata:    Dict          = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LongTermEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def age_days(self) -> float:
        return (time.time() - self.created_at) / 86400

    def touch(self) -> None:
        """更新访问时间与计数。"""
        self.updated_at   = time.time()
        self.access_count += 1


# ── 长期记忆主类 ─────────────────────────────────────────────────────────────

class LongTermMemory:
    """
    长期记忆：跨会话的持久化知识存储。

    Usage::

        ltm = LongTermMemory()

        # 直接存入知识
        ltm.store(
            title="武汉医院空间分布规律",
            content={"finding": "医院主要集中在三环内..."},
            category="knowledge",
            tags=["wuhan", "hospital", "spatial"],
            importance=0.8,
        )

        # 从短期记忆摘要转入
        stm_summary = stm.summarize()
        ltm.flush_from_session(stm_summary, title="2025-03-07 医院缓冲区分析")

        # 检索
        results = ltm.search("武汉 医院")
        recent  = ltm.get_recent(n=5)
        by_tag  = ltm.get_by_tag("hospital")
    """

    DEFAULT_DIR = Path.home() / ".geoclaw_claude" / "memory"

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = Path(memory_dir) if memory_dir else self.DEFAULT_DIR
        self._lock      = threading.RLock()
        self._index:    Dict[str, dict] = {}   # id -> 轻量索引条目
        self._setup_dirs()
        self._load_index()

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def _setup_dirs(self) -> None:
        for cat in list(CATEGORIES.keys()) + [""]:
            (self.memory_dir / cat if cat else self.memory_dir).mkdir(
                parents=True, exist_ok=True
            )

    def _index_path(self) -> Path:
        return self.memory_dir / "index.json"

    def _entry_path(self, entry: LongTermEntry) -> Path:
        return self.memory_dir / entry.category / f"{entry.id}.json"

    # ── 索引加载/保存 ─────────────────────────────────────────────────────────

    def _load_index(self) -> None:
        idx_path = self._index_path()
        if idx_path.exists():
            try:
                self._index = json.loads(idx_path.read_text(encoding="utf-8"))
            except Exception:
                self._index = {}
        else:
            self._index = {}

    def _save_index(self) -> None:
        self._index_path().write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _add_to_index(self, entry: LongTermEntry) -> None:
        self._index[entry.id] = {
            "id":         entry.id,
            "title":      entry.title,
            "category":   entry.category,
            "tags":       entry.tags,
            "importance": entry.importance,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "source":     entry.source,
        }

    # ── 核心 CRUD ─────────────────────────────────────────────────────────────

    def store(
        self,
        title:      str,
        content:    Any,
        category:   str        = "knowledge",
        tags:       List[str]  = None,
        importance: float      = 0.5,
        source:     str        = "",
        metadata:   dict       = None,
        entry_id:   str        = None,
    ) -> str:
        """
        存入一条长期记忆。返回 entry_id。
        如果 entry_id 已存在则更新（upsert）。
        """
        with self._lock:
            if entry_id and entry_id in self._index:
                return self._update(entry_id, title, content, tags, importance, metadata)

            eid = entry_id or str(uuid.uuid4())[:8]
            # 确保类别目录存在
            cat_dir = self.memory_dir / category
            cat_dir.mkdir(parents=True, exist_ok=True)

            entry = LongTermEntry(
                id=eid,
                title=title,
                content=content if _is_json_serializable(content) else str(content),
                category=category,
                tags=tags or [],
                importance=float(importance),
                source=source,
                metadata=metadata or {},
            )
            # 写磁盘
            self._entry_path(entry).write_text(
                json.dumps(entry.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._add_to_index(entry)
            self._save_index()
            return eid

    def _update(
        self,
        entry_id:   str,
        title:      str,
        content:    Any,
        tags:       Optional[List[str]],
        importance: float,
        metadata:   Optional[dict],
    ) -> str:
        entry = self.get(entry_id)
        if entry is None:
            return entry_id
        entry.title      = title
        entry.content    = content if _is_json_serializable(content) else str(content)
        entry.updated_at = time.time()
        if tags is not None:
            entry.tags = tags
        if importance != 0.5:
            entry.importance = importance
        if metadata:
            entry.metadata.update(metadata)
        self._entry_path(entry).write_text(
            json.dumps(entry.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._add_to_index(entry)
        self._save_index()
        return entry_id

    def get(self, entry_id: str) -> Optional[LongTermEntry]:
        """根据 ID 读取完整条目。"""
        idx = self._index.get(entry_id)
        if not idx:
            return None
        path = self.memory_dir / idx["category"] / f"{entry_id}.json"
        if not path.exists():
            return None
        try:
            data  = json.loads(path.read_text(encoding="utf-8"))
            entry = LongTermEntry.from_dict(data)
            entry.touch()
            path.write_text(
                json.dumps(entry.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return entry
        except Exception:
            return None

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            idx = self._index.get(entry_id)
            if not idx:
                return False
            path = self.memory_dir / idx["category"] / f"{entry_id}.json"
            if path.exists():
                path.unlink()
            self._index.pop(entry_id, None)
            self._save_index()
            return True

    # ── 从短期记忆转入 ────────────────────────────────────────────────────────

    def flush_from_session(
        self,
        session_summary: dict,
        title:           str       = "",
        tags:            List[str] = None,
        importance:      float     = 0.5,
    ) -> str:
        """
        将短期记忆（ShortTermMemory.summarize()）的摘要转入长期记忆。

        Args:
            session_summary: ShortTermMemory.summarize() 返回的字典
            title          : 记忆标题（默认用 session_id）
            tags           : 标签列表
            importance     : 重要性评分 0~1

        Returns:
            entry_id (str)
        """
        sid   = session_summary.get("session_id", "unknown")
        ops   = session_summary.get("operations", {})
        errs  = session_summary.get("errors", [])

        # 自动计算重要性：操作多 + 无错误 → 更重要
        if importance == 0.5:
            op_count = ops.get("total", 0)
            err_rate = len(errs) / max(op_count, 1)
            importance = min(0.9, 0.3 + op_count * 0.05 - err_rate * 0.3)

        # 提炼核心内容（去掉大体积原始数据）
        condensed = {
            "session_id":    sid,
            "date":          time.strftime("%Y-%m-%d %H:%M", time.localtime(
                session_summary.get("created_at", time.time())
            )),
            "duration_sec":  session_summary.get("duration_sec", 0),
            "operations":    {
                "total":     ops.get("total", 0),
                "success":   ops.get("success", 0),
                "failed":    ops.get("failed", 0),
                "duration":  ops.get("total_duration", 0),
                "frequency": ops.get("frequency", {}),
            },
            "stored_keys":   session_summary.get("memory_store", {}).get("keys", []),
            "errors":        errs,
        }

        entry_title = title or f"会话复盘 — {sid}"
        auto_tags   = list(tags or []) + ["session", "auto"]
        # 从操作频率中提取功能标签
        for fn in ops.get("frequency", {}).keys():
            auto_tags.append(fn.split(".")[-1])

        return self.store(
            title=entry_title,
            content=condensed,
            category="session",
            tags=list(set(auto_tags)),
            importance=importance,
            source=sid,
        )

    # ── 检索 ──────────────────────────────────────────────────────────────────

    def search(
        self,
        query:      str,
        category:   Optional[str] = None,
        top_k:      int           = 10,
    ) -> List[LongTermEntry]:
        """
        关键词全文检索（在标题、标签、source 中搜索）。

        Args:
            query   : 空格分隔的关键词（AND 逻辑）
            category: 限定类别（None 则全类别）
            top_k   : 最多返回条数

        Returns:
            List[LongTermEntry]，按相关性降序排列
        """
        keywords = query.lower().split()
        results  = []

        for eid, idx in self._index.items():
            if category and idx["category"] != category:
                continue
            # 索引层快速搜索（标题 + 标签 + source）
            searchable = (
                idx["title"].lower() + " " +
                " ".join(idx["tags"]).lower() + " " +
                idx.get("source", "").lower()
            )
            score = sum(1 for kw in keywords if kw in searchable)
            # 若索引层未命中，读取完整 content 深度搜索
            if score == 0:
                entry = self.get(eid)
                if entry:
                    score = sum(1 for kw in keywords if kw in str(entry.content).lower())
            if score > 0:
                weight = score + idx["importance"] * 0.5
                results.append((weight, eid))

        results.sort(key=lambda x: -x[0])
        entries = []
        for _, eid in results[:top_k]:
            entry = self.get(eid)
            if entry:
                entries.append(entry)
        return entries

    def get_by_category(
        self,
        category: str,
        sort_by:  str = "updated_at",
        top_k:    int = 20,
    ) -> List[LongTermEntry]:
        """获取指定类别的所有记忆，按指定字段排序。"""
        items = [
            (self._index[eid][sort_by], eid)
            for eid, idx in self._index.items()
            if idx["category"] == category
        ]
        items.sort(key=lambda x: -x[0])
        return [e for _, eid in items[:top_k] if (e := self.get(eid))]

    def get_by_tag(self, tag: str, top_k: int = 20) -> List[LongTermEntry]:
        """按标签检索。"""
        matched = [
            (self._index[eid]["importance"], eid)
            for eid, idx in self._index.items()
            if tag in idx["tags"]
        ]
        matched.sort(key=lambda x: -x[0])
        return [e for _, eid in matched[:top_k] if (e := self.get(eid))]

    def get_recent(self, n: int = 10, category: Optional[str] = None) -> List[LongTermEntry]:
        """获取最近更新的 n 条记忆。"""
        items = [
            (self._index[eid]["updated_at"], eid)
            for eid, idx in self._index.items()
            if (category is None or idx["category"] == category)
        ]
        items.sort(key=lambda x: -x[0])
        return [e for _, eid in items[:n] if (e := self.get(eid))]

    def get_important(self, n: int = 10, threshold: float = 0.6) -> List[LongTermEntry]:
        """获取重要性高于阈值的记忆。"""
        items = [
            (self._index[eid]["importance"], eid)
            for eid, idx in self._index.items()
            if idx["importance"] >= threshold
        ]
        items.sort(key=lambda x: -x[0])
        return [e for _, eid in items[:n] if (e := self.get(eid))]

    # ── 统计与管理 ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """返回长期记忆统计信息。"""
        by_category: Dict[str, int] = {}
        for idx in self._index.values():
            cat = idx["category"]
            by_category[cat] = by_category.get(cat, 0) + 1

        importances = [idx["importance"] for idx in self._index.values()]
        avg_imp = sum(importances) / max(len(importances), 1)

        return {
            "total_entries":   len(self._index),
            "by_category":     by_category,
            "avg_importance":  round(avg_imp, 3),
            "memory_dir":      str(self.memory_dir),
            "index_size":      len(self._index),
        }

    def compact(self, keep_top_n: int = 200, min_importance: float = 0.2) -> int:
        """
        压缩长期记忆：删除重要性低且较旧的条目。
        保留最新 keep_top_n 条 + 重要性高于 min_importance 的所有条目。

        Returns:
            删除条数
        """
        with self._lock:
            # 按重要性×近期度打分
            scored = []
            for eid, idx in self._index.items():
                age_days  = (time.time() - idx["updated_at"]) / 86400
                score     = idx["importance"] - age_days * 0.01
                scored.append((score, eid))
            scored.sort(key=lambda x: -x[0])

            keep_ids = set()
            for _, eid in scored[:keep_top_n]:
                keep_ids.add(eid)
            # 始终保留高重要性条目
            for eid, idx in self._index.items():
                if idx["importance"] >= min_importance:
                    keep_ids.add(eid)

            remove_ids = [eid for eid in self._index if eid not in keep_ids]
            for eid in remove_ids:
                self.delete(eid)

            return len(remove_ids)

    def clear_all(self) -> None:
        """清空所有长期记忆（危险操作，会删除磁盘文件）。"""
        with self._lock:
            if self.memory_dir.exists():
                shutil.rmtree(self.memory_dir)
            self._index = {}
            self._setup_dirs()

    def export_json(self) -> str:
        """导出所有记忆为 JSON 字符串。"""
        all_entries = []
        for eid in list(self._index.keys()):
            entry = self.get(eid)
            if entry:
                all_entries.append(entry.to_dict())
        return json.dumps({
            "exported_at": time.time(),
            "total":       len(all_entries),
            "entries":     all_entries,
        }, ensure_ascii=False, indent=2)

    def __len__(self) -> int:
        return len(self._index)

    def __repr__(self) -> str:
        return f"LongTermMemory(dir={self.memory_dir}, entries={len(self)})"


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False
