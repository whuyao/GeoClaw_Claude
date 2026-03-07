"""
geoclaw_claude/memory/archive.py
==================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

记忆存档系统 (MemoryArchive)

将完整会话快照持久化到磁盘，支持：
  - 会话级存档：保存操作序列 + 上下文 + 结果摘要
  - 全量导出/导入：JSON 格式，可跨机器迁移
  - 存档浏览/搜索：按时间、标签、关键词检索历史存档
  - 自动归档：超过 N 天未访问的长期记忆自动存档冷存储

存档目录结构:
  ~/.geoclaw_claude/archives/
    ├── index.json              ← 全局索引（id, title, date, tags, size）
    ├── 2025-03/                ← 按年月分目录
    │   ├── arc_20250307_001.json
    │   └── arc_20250307_002.json
    └── ...

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── 存档条目 ─────────────────────────────────────────────────────────────────

@dataclass
class ArchiveEntry:
    """单条存档记录。"""
    archive_id:  str               # 唯一 ID
    title:       str               # 会话/存档标题
    created_at:  float             # Unix 时间戳
    source:      str               # 来源类型: session / export / manual
    tags:        List[str]         = field(default_factory=list)
    summary:     str               = ""          # 摘要（100~300 字）
    ops_count:   int               = 0           # 操作数
    size_bytes:  int               = 0           # 存档文件大小
    extra:       Dict[str, Any]    = field(default_factory=dict)

    # 完整内容（存档时写入文件，索引中只保存元数据）
    content:     Dict[str, Any]    = field(default_factory=dict)

    @property
    def date_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.created_at))

    @property
    def month_dir(self) -> str:
        return time.strftime("%Y-%m", time.localtime(self.created_at))

    def to_index_dict(self) -> dict:
        """仅返回索引所需元数据（不含完整 content）。"""
        return {
            "archive_id": self.archive_id,
            "title":      self.title,
            "created_at": self.created_at,
            "source":     self.source,
            "tags":       self.tags,
            "summary":    self.summary,
            "ops_count":  self.ops_count,
            "size_bytes": self.size_bytes,
            "extra":      self.extra,
        }

    def to_full_dict(self) -> dict:
        d = self.to_index_dict()
        d["content"] = self.content
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ArchiveEntry":
        return cls(
            archive_id = d.get("archive_id", ""),
            title      = d.get("title", ""),
            created_at = d.get("created_at", time.time()),
            source     = d.get("source", "manual"),
            tags       = d.get("tags", []),
            summary    = d.get("summary", ""),
            ops_count  = d.get("ops_count", 0),
            size_bytes = d.get("size_bytes", 0),
            extra      = d.get("extra", {}),
            content    = d.get("content", {}),
        )


# ── 记忆存档主类 ──────────────────────────────────────────────────────────────

class MemoryArchive:
    """
    会话记忆存档管理器。

    Usage::

        arc = MemoryArchive()

        # 存档一次会话
        entry = arc.save_session(
            title="武汉医院分析 2025-03",
            ops_log=[...],
            context={"city": "wuhan"},
            summary="完成了医院缓冲区和核密度分析",
            tags=["wuhan", "hospital"],
        )

        # 搜索存档
        results = arc.search("武汉 医院")

        # 加载完整存档
        entry = arc.load(archive_id)

        # 列出所有存档
        entries = arc.list_archives(limit=20)

        # 导出全量 JSON
        arc.export("backup.json")

        # 从 JSON 导入
        arc.import_json("backup.json")
    """

    def __init__(self, archive_dir: Optional[Path] = None):
        from pathlib import Path as _Path
        base = _Path.home() / ".geoclaw_claude"
        self.archive_dir = archive_dir or (base / "archives")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, dict] = {}
        self._load_index()

    # ── 索引 ─────────────────────────────────────────────────────────────────

    @property
    def _index_path(self) -> Path:
        return self.archive_dir / "index.json"

    def _load_index(self) -> None:
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                self._index = {e["archive_id"]: e for e in data if "archive_id" in e}
            except Exception:
                self._index = {}

    def _save_index(self) -> None:
        entries = sorted(self._index.values(), key=lambda e: e.get("created_at", 0), reverse=True)
        self._index_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 存档路径 ──────────────────────────────────────────────────────────────

    def _entry_path(self, entry: ArchiveEntry) -> Path:
        month_dir = self.archive_dir / entry.month_dir
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / f"arc_{entry.archive_id}.json"

    # ── 保存会话存档 ──────────────────────────────────────────────────────────

    def save_session(
        self,
        title: str,
        ops_log: Optional[List[dict]] = None,
        context: Optional[dict] = None,
        summary: str = "",
        tags: Optional[List[str]] = None,
        extra: Optional[dict] = None,
    ) -> ArchiveEntry:
        """
        存档一次完整会话。

        Args:
            title   : 存档标题
            ops_log : 操作日志列表 [{action, detail, timestamp}, ...]
            context : 会话上下文键值对
            summary : 会话摘要文本
            tags    : 标签列表
            extra   : 额外元数据

        Returns:
            ArchiveEntry — 已保存的存档条目
        """
        arc_id = str(uuid.uuid4()).replace("-", "")[:16]
        now    = time.time()

        content = {
            "ops_log":  ops_log  or [],
            "context":  context  or {},
            "summary":  summary,
            "metadata": {
                "title":      title,
                "created_at": now,
                "tags":       tags or [],
            },
        }

        # 自动生成摘要（若未提供）
        if not summary and ops_log:
            summary = self._auto_summary(ops_log)

        entry = ArchiveEntry(
            archive_id = arc_id,
            title      = title,
            created_at = now,
            source     = "session",
            tags       = tags or [],
            summary    = summary,
            ops_count  = len(ops_log or []),
            content    = content,
            extra      = extra or {},
        )

        # 写文件
        path = self._entry_path(entry)
        text = json.dumps(entry.to_full_dict(), ensure_ascii=False, indent=2)
        path.write_text(text, encoding="utf-8")
        entry.size_bytes = len(text.encode("utf-8"))

        # 更新索引
        self._index[arc_id] = entry.to_index_dict()
        self._save_index()

        return entry

    def _auto_summary(self, ops_log: List[dict]) -> str:
        """从操作日志自动生成摘要。"""
        if not ops_log:
            return ""
        actions = [op.get("action", op.get("op", "")) for op in ops_log[-10:]]
        actions = [a for a in actions if a]
        if actions:
            return f"共 {len(ops_log)} 个操作：" + "→".join(actions[:6]) + (
                "…" if len(actions) > 6 else ""
            )
        return f"共 {len(ops_log)} 个操作"

    # ── 加载 ─────────────────────────────────────────────────────────────────

    def load(self, archive_id: str) -> Optional[ArchiveEntry]:
        """加载完整存档内容。"""
        meta = self._index.get(archive_id)
        if not meta:
            return None
        # 查找文件
        entry_stub = ArchiveEntry.from_dict(meta)
        path = self._entry_path(entry_stub)
        if not path.exists():
            # 兼容：遍历子目录查找
            found = list(self.archive_dir.rglob(f"arc_{archive_id}.json"))
            if not found:
                return None
            path = found[0]
        try:
            data  = json.loads(path.read_text(encoding="utf-8"))
            return ArchiveEntry.from_dict(data)
        except Exception:
            return None

    # ── 删除 ─────────────────────────────────────────────────────────────────

    def delete(self, archive_id: str) -> bool:
        """删除存档。"""
        meta = self._index.pop(archive_id, None)
        if not meta:
            return False
        entry_stub = ArchiveEntry.from_dict(meta)
        path = self._entry_path(entry_stub)
        if path.exists():
            path.unlink()
        self._save_index()
        return True

    # ── 列表与搜索 ────────────────────────────────────────────────────────────

    def list_archives(
        self,
        limit: int = 20,
        source: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[ArchiveEntry]:
        """列出存档（仅元数据，不加载 content）。"""
        entries = list(self._index.values())
        if source:
            entries = [e for e in entries if e.get("source") == source]
        if tag:
            entries = [e for e in entries if tag in e.get("tags", [])]
        entries.sort(key=lambda e: e.get("created_at", 0), reverse=True)
        return [ArchiveEntry.from_dict(e) for e in entries[:limit]]

    def search(self, query: str, limit: int = 10) -> List[ArchiveEntry]:
        """
        按关键词搜索存档（标题 + 摘要 + 标签全文检索）。

        Args:
            query : 空格分隔的关键词
            limit : 最大返回数量

        Returns:
            按相关度排序的 ArchiveEntry 列表（仅元数据）
        """
        keywords = query.lower().split()
        if not keywords:
            return self.list_archives(limit)

        scored: List[tuple] = []
        for arc_id, meta in self._index.items():
            text = " ".join([
                meta.get("title", ""),
                meta.get("summary", ""),
                " ".join(meta.get("tags", [])),
            ]).lower()
            score = sum(text.count(kw) for kw in keywords)
            if score > 0:
                scored.append((score, meta))

        scored.sort(key=lambda x: (-x[0], -x[1].get("created_at", 0)))
        return [ArchiveEntry.from_dict(m) for _, m in scored[:limit]]

    # ── 导出 / 导入 ───────────────────────────────────────────────────────────

    def export(self, path: Optional[str] = None) -> str:
        """
        导出全量存档为 JSON 字符串（含完整 content）。

        Args:
            path : 若提供则写入文件

        Returns:
            JSON 字符串
        """
        full_entries = []
        for arc_id in self._index:
            entry = self.load(arc_id)
            if entry:
                full_entries.append(entry.to_full_dict())

        data = {
            "exported_at": time.time(),
            "version":     "2.3.0",
            "count":       len(full_entries),
            "archives":    full_entries,
        }
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if path:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def import_json(self, path: str, overwrite: bool = False) -> int:
        """
        从 JSON 文件导入存档。

        Args:
            path      : JSON 文件路径
            overwrite : 若 ID 冲突是否覆盖

        Returns:
            成功导入的条目数
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        archives = data.get("archives", [])
        imported = 0
        for arc_data in archives:
            arc_id = arc_data.get("archive_id", "")
            if not arc_id:
                continue
            if arc_id in self._index and not overwrite:
                continue
            entry = ArchiveEntry.from_dict(arc_data)
            file_path = self._entry_path(entry)
            text = json.dumps(entry.to_full_dict(), ensure_ascii=False, indent=2)
            file_path.write_text(text, encoding="utf-8")
            entry.size_bytes = len(text.encode("utf-8"))
            self._index[arc_id] = entry.to_index_dict()
            imported += 1
        if imported:
            self._save_index()
        return imported

    # ── 统计 ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """返回存档统计信息。"""
        entries = list(self._index.values())
        total_size = sum(e.get("size_bytes", 0) for e in entries)
        return {
            "total":      len(entries),
            "total_size": total_size,
            "size_human": f"{total_size / 1024:.1f} KB" if total_size < 1024*1024
                          else f"{total_size / 1024 / 1024:.2f} MB",
            "sources":    {s: sum(1 for e in entries if e.get("source") == s)
                           for s in {"session", "export", "manual"}},
        }

    def __len__(self) -> int:
        return len(self._index)

    def __repr__(self) -> str:
        return f"MemoryArchive(dir={self.archive_dir}, count={len(self)})"


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_default_archive: Optional[MemoryArchive] = None


def get_archive(archive_dir: Optional[Path] = None) -> MemoryArchive:
    """获取全局默认存档管理器（单例）。"""
    global _default_archive
    if _default_archive is None or archive_dir is not None:
        _default_archive = MemoryArchive(archive_dir)
    return _default_archive
