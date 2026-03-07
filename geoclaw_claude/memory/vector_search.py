"""
geoclaw_claude/memory/vector_search.py
=========================================
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

向量语义检索引擎 (VectorSearch)

基于 TF-IDF 近似向量实现零依赖语义搜索，支持：
  - 文档向量化与持久化索引
  - 余弦相似度语义检索
  - 增量更新（新增/删除不需要重建全量索引）
  - 可选：若环境中有 sentence-transformers，自动升级为真正的向量嵌入

设计哲学:
  - 零外部依赖：仅使用 Python 标准库 + 内置 math
  - 可选增强：检测到 sentence-transformers 时自动使用高质量嵌入
  - 持久化：索引保存到 ~/.geoclaw_claude/vector_index/

索引格式:
  ~/.geoclaw_claude/vector_index/
    ├── vocab.json          ← 词汇表 {word: index}
    ├── vectors.json        ← 文档向量 {doc_id: [tfidf...]}
    └── meta.json           ← 文档元数据 {doc_id: {text, source, tags, ...}}

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── 文本预处理 ───────────────────────────────────────────────────────────────

def tokenize(text: str) -> List[str]:
    """
    中英文混合分词（零依赖版本）。
    中文：字符级切分（每个汉字为独立 token）
    英文：按空格/标点切分后小写化
    """
    if not text:
        return []
    tokens = []
    # 提取中文字符
    tokens.extend(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf\u20000-\u2a6df]", text))
    # 提取英文单词和数字
    tokens.extend(t.lower() for t in re.findall(r"[a-zA-Z0-9_\-\.]+", text))
    # 过滤停用词和短词
    stop_words = {
        "的", "了", "是", "在", "和", "有", "我", "你", "他", "她", "它",
        "这", "那", "一", "不", "也", "都", "但", "而", "与", "或",
        "the", "a", "an", "in", "on", "at", "to", "of", "for", "is",
        "was", "are", "were", "be", "been", "has", "have", "had",
        "do", "does", "did", "and", "or", "but", "with", "by",
    }
    tokens = [t for t in tokens if t and t not in stop_words and len(t) >= 1]
    return tokens


# ── 向量操作 ─────────────────────────────────────────────────────────────────

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """计算两个稠密向量的余弦相似度。"""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def sparse_cosine_similarity(
    v1: Dict[int, float], v2: Dict[int, float]
) -> float:
    """计算两个稀疏向量的余弦相似度（节省内存）。"""
    if not v1 or not v2:
        return 0.0
    # 只计算共同维度的内积
    common = set(v1.keys()) & set(v2.keys())
    dot = sum(v1[k] * v2[k] for k in common)
    norm1 = math.sqrt(sum(x * x for x in v1.values()))
    norm2 = math.sqrt(sum(x * x for x in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


# ── 检索结果 ─────────────────────────────────────────────────────────────────

class SearchResult:
    """单条检索结果。"""
    __slots__ = ("doc_id", "score", "meta", "snippet")

    def __init__(self, doc_id: str, score: float, meta: dict, snippet: str = ""):
        self.doc_id  = doc_id
        self.score   = score
        self.meta    = meta
        self.snippet = snippet

    def __repr__(self) -> str:
        return f"SearchResult(id={self.doc_id!r}, score={self.score:.3f}, title={self.meta.get('title', '')!r})"


# ── TF-IDF 向量搜索引擎 ───────────────────────────────────────────────────────

class VectorSearch:
    """
    TF-IDF 近似向量语义检索引擎。

    可选增强：若安装了 sentence-transformers，自动切换为神经网络嵌入：
        pip install sentence-transformers

    Usage::

        vs = VectorSearch()

        # 添加文档
        vs.add("doc1", "武汉市医院空间分布分析", tags=["wuhan", "hospital"])
        vs.add("doc2", "武汉三环内公园绿地核密度", tags=["wuhan", "park"])

        # 搜索
        results = vs.search("武汉医院分析", top_k=5)
        for r in results:
            print(r.score, r.meta["title"])

        # 保存索引
        vs.save()

        # 加载索引
        vs2 = VectorSearch()
        vs2.load()
    """

    def __init__(self, index_dir: Optional[Path] = None, use_neural: bool = True):
        base = Path.home() / ".geoclaw_claude"
        self.index_dir = index_dir or (base / "vector_index")
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # 词汇表
        self._vocab:   Dict[str, int]            = {}   # word → index
        self._idf:     Dict[int, float]           = {}   # index → idf
        # 稀疏向量存储
        self._vectors: Dict[str, Dict[int, float]] = {}  # doc_id → sparse_tfidf
        # 文档元数据
        self._meta:    Dict[str, dict]            = {}   # doc_id → meta
        # 原始词频（用于增量 IDF 更新）
        self._tf_raw:  Dict[str, Counter]         = {}   # doc_id → Counter

        self._neural_encoder = None
        self._neural_vectors: Dict[str, List[float]] = {}

        if use_neural:
            self._try_load_neural()

        # 尝试从磁盘加载
        self._dirty = False

    # ── 神经网络嵌入（可选）────────────────────────────────────────────────────

    def _try_load_neural(self) -> None:
        """尝试加载 sentence-transformers（失败则静默降级）。"""
        try:
            from sentence_transformers import SentenceTransformer
            self._neural_encoder = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2"
            )
        except Exception:
            self._neural_encoder = None

    @property
    def backend(self) -> str:
        """返回当前使用的后端名称。"""
        return "neural (sentence-transformers)" if self._neural_encoder else "tfidf (zero-dependency)"

    # ── 添加文档 ─────────────────────────────────────────────────────────────

    def add(
        self,
        doc_id: str,
        text: str,
        title: str = "",
        tags: Optional[List[str]] = None,
        source: str = "",
        importance: float = 0.5,
        extra: Optional[dict] = None,
    ) -> None:
        """
        添加或更新文档到索引。

        Args:
            doc_id     : 文档唯一 ID（通常是 LongTermEntry.id）
            text       : 文档文本内容
            title      : 文档标题
            tags       : 标签列表
            source     : 来源（memory / archive / ...）
            importance : 重要度（0~1），影响检索排序
            extra      : 额外元数据
        """
        tokens = tokenize(text + " " + title + " " + " ".join(tags or []))

        # TF-IDF 路径
        tf = Counter(tokens)
        self._tf_raw[doc_id] = tf
        # 更新词汇表
        for w in tf:
            if w not in self._vocab:
                self._vocab[w] = len(self._vocab)

        # 元数据
        self._meta[doc_id] = {
            "title":      title or text[:60],
            "text":       text[:500],
            "tags":       tags or [],
            "source":     source,
            "importance": importance,
            "added_at":   time.time(),
            **(extra or {}),
        }

        # 神经网络嵌入路径
        if self._neural_encoder is not None:
            try:
                vec = self._neural_encoder.encode(
                    text[:512], normalize_embeddings=True
                ).tolist()
                self._neural_vectors[doc_id] = vec
            except Exception:
                pass

        # 重建受影响文档的 TF-IDF 向量
        self._rebuild_tfidf()
        self._dirty = True

    def remove(self, doc_id: str) -> bool:
        """从索引中删除文档。"""
        removed = False
        for d in [self._tf_raw, self._vectors, self._meta, self._neural_vectors]:
            if doc_id in d:
                del d[doc_id]
                removed = True
        if removed:
            self._rebuild_tfidf()
            self._dirty = True
        return removed

    # ── TF-IDF 重建 ───────────────────────────────────────────────────────────

    def _rebuild_tfidf(self) -> None:
        """重新计算所有文档的 TF-IDF 向量。"""
        N = len(self._tf_raw)
        if N == 0:
            self._idf = {}
            self._vectors = {}
            return

        # 计算 IDF
        df: Dict[int, int] = defaultdict(int)
        for tf in self._tf_raw.values():
            for w in tf:
                idx = self._vocab.get(w)
                if idx is not None:
                    df[idx] += 1

        self._idf = {
            idx: math.log((N + 1) / (count + 1)) + 1.0
            for idx, count in df.items()
        }

        # 计算每个文档的 TF-IDF 稀疏向量
        for doc_id, tf in self._tf_raw.items():
            total = sum(tf.values()) or 1
            vec: Dict[int, float] = {}
            for w, cnt in tf.items():
                idx = self._vocab.get(w)
                if idx is not None:
                    tfidf = (cnt / total) * self._idf.get(idx, 1.0)
                    if tfidf > 0:
                        vec[idx] = tfidf
            self._vectors[doc_id] = vec

    # ── 检索 ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
        source_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        语义检索。

        Args:
            query         : 查询文本
            top_k         : 返回最多 K 条结果
            min_score     : 最小相似度阈值（0~1）
            source_filter : 只检索指定来源
            tag_filter    : 只检索含指定标签的文档

        Returns:
            List[SearchResult]，按相关度降序排列
        """
        if not self._vectors and not self._neural_vectors:
            return []

        if not query.strip():
            return []

        # 过滤候选文档
        candidates = set(self._meta.keys())
        if source_filter:
            candidates = {d for d in candidates
                          if self._meta[d].get("source") == source_filter}
        if tag_filter:
            candidates = {d for d in candidates
                          if tag_filter in self._meta[d].get("tags", [])}

        # 神经网络检索
        if self._neural_encoder is not None and self._neural_vectors:
            return self._neural_search(query, candidates, top_k, min_score)

        # TF-IDF 检索
        return self._tfidf_search(query, candidates, top_k, min_score)

    def _tfidf_search(
        self,
        query: str,
        candidates: set,
        top_k: int,
        min_score: float,
    ) -> List[SearchResult]:
        """TF-IDF 相似度检索。"""
        tokens = tokenize(query)
        if not tokens:
            return []

        # 构建查询向量
        tf_q = Counter(tokens)
        total_q = sum(tf_q.values()) or 1
        q_vec: Dict[int, float] = {}
        for w, cnt in tf_q.items():
            idx = self._vocab.get(w)
            if idx is not None:
                q_vec[idx] = (cnt / total_q) * self._idf.get(idx, 1.0)

        if not q_vec:
            # 关键词在词汇表中不存在，降级到关键词匹配
            return self._keyword_search(tokens, candidates, top_k, min_score)

        # 计算相似度
        scored: List[Tuple[float, str]] = []
        for doc_id in candidates:
            vec = self._vectors.get(doc_id, {})
            if not vec:
                continue
            score = sparse_cosine_similarity(q_vec, vec)
            # 重要度加权
            importance = self._meta.get(doc_id, {}).get("importance", 0.5)
            score = score * 0.85 + importance * 0.15
            if score >= min_score:
                scored.append((score, doc_id))

        scored.sort(reverse=True)
        return [
            SearchResult(
                doc_id  = doc_id,
                score   = score,
                meta    = self._meta.get(doc_id, {}),
                snippet = self._meta.get(doc_id, {}).get("text", "")[:150],
            )
            for score, doc_id in scored[:top_k]
        ]

    def _keyword_search(
        self,
        tokens: List[str],
        candidates: set,
        top_k: int,
        min_score: float,
    ) -> List[SearchResult]:
        """降级：关键词命中计数检索。"""
        scored: List[Tuple[float, str]] = []
        for doc_id in candidates:
            meta = self._meta.get(doc_id, {})
            text = (meta.get("text", "") + " " + meta.get("title", "") +
                    " ".join(meta.get("tags", []))).lower()
            hits = sum(text.count(t) for t in tokens)
            if hits > 0:
                score = min(hits / len(tokens) * 0.3, 1.0)
                if score >= min_score:
                    scored.append((score, doc_id))
        scored.sort(reverse=True)
        return [
            SearchResult(
                doc_id  = doc_id,
                score   = score,
                meta    = self._meta.get(doc_id, {}),
                snippet = self._meta.get(doc_id, {}).get("text", "")[:150],
            )
            for score, doc_id in scored[:top_k]
        ]

    def _neural_search(
        self,
        query: str,
        candidates: set,
        top_k: int,
        min_score: float,
    ) -> List[SearchResult]:
        """神经网络嵌入检索。"""
        try:
            q_vec = self._neural_encoder.encode(
                query[:512], normalize_embeddings=True
            ).tolist()
        except Exception:
            return self._tfidf_search(query, candidates, top_k, min_score)

        scored: List[Tuple[float, str]] = []
        for doc_id in candidates:
            d_vec = self._neural_vectors.get(doc_id)
            if not d_vec:
                continue
            score = cosine_similarity(q_vec, d_vec)
            importance = self._meta.get(doc_id, {}).get("importance", 0.5)
            score = score * 0.85 + importance * 0.15
            if score >= min_score:
                scored.append((score, doc_id))

        scored.sort(reverse=True)
        return [
            SearchResult(
                doc_id  = doc_id,
                score   = score,
                meta    = self._meta.get(doc_id, {}),
                snippet = self._meta.get(doc_id, {}).get("text", "")[:150],
            )
            for score, doc_id in scored[:top_k]
        ]

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def save(self) -> None:
        """保存索引到磁盘。"""
        if not self._dirty:
            return

        # vocab
        (self.index_dir / "vocab.json").write_text(
            json.dumps(self._vocab, ensure_ascii=False), encoding="utf-8"
        )
        # sparse vectors（转为 list-of-pairs 格式节省空间）
        vecs_serial = {
            doc_id: [[k, v] for k, v in vec.items()]
            for doc_id, vec in self._vectors.items()
        }
        (self.index_dir / "vectors.json").write_text(
            json.dumps(vecs_serial, ensure_ascii=False), encoding="utf-8"
        )
        # meta
        (self.index_dir / "meta.json").write_text(
            json.dumps(self._meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # tf_raw
        tf_serial = {
            doc_id: dict(counter)
            for doc_id, counter in self._tf_raw.items()
        }
        (self.index_dir / "tf_raw.json").write_text(
            json.dumps(tf_serial, ensure_ascii=False), encoding="utf-8"
        )
        # neural vectors（若存在）
        if self._neural_vectors:
            (self.index_dir / "neural_vectors.json").write_text(
                json.dumps(self._neural_vectors, ensure_ascii=False), encoding="utf-8"
            )
        self._dirty = False

    def load(self) -> bool:
        """从磁盘加载索引。返回 True 表示成功。"""
        try:
            vocab_path = self.index_dir / "vocab.json"
            if not vocab_path.exists():
                return False
            self._vocab = json.loads(vocab_path.read_text(encoding="utf-8"))

            meta_path = self.index_dir / "meta.json"
            if meta_path.exists():
                self._meta = json.loads(meta_path.read_text(encoding="utf-8"))

            tf_path = self.index_dir / "tf_raw.json"
            if tf_path.exists():
                tf_serial = json.loads(tf_path.read_text(encoding="utf-8"))
                self._tf_raw = {doc_id: Counter(tf) for doc_id, tf in tf_serial.items()}
            
            # 加载神经向量
            neural_path = self.index_dir / "neural_vectors.json"
            if neural_path.exists() and self._neural_encoder:
                self._neural_vectors = json.loads(neural_path.read_text(encoding="utf-8"))

            # 重建 IDF 和向量
            self._rebuild_tfidf()
            self._dirty = False
            return True
        except Exception as e:
            return False

    def clear(self) -> None:
        """清空索引。"""
        self._vocab.clear()
        self._idf.clear()
        self._vectors.clear()
        self._meta.clear()
        self._tf_raw.clear()
        self._neural_vectors.clear()
        self._dirty = True

    def stats(self) -> dict:
        """返回索引统计信息。"""
        return {
            "documents": len(self._meta),
            "vocab_size": len(self._vocab),
            "backend":   self.backend,
            "index_dir": str(self.index_dir),
        }

    def __len__(self) -> int:
        return len(self._meta)

    def __repr__(self) -> str:
        return (f"VectorSearch(docs={len(self)}, vocab={len(self._vocab)}, "
                f"backend={self.backend!r})")


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_default_vs: Optional[VectorSearch] = None


def get_vector_search(index_dir: Optional[Path] = None) -> VectorSearch:
    """获取全局向量搜索实例（自动加载持久化索引）。"""
    global _default_vs
    if _default_vs is None or index_dir is not None:
        _default_vs = VectorSearch(index_dir)
        _default_vs.load()
    return _default_vs
