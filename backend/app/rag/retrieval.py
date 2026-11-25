"""Hybrid retrieval over the ACTIVE knowledge base only: BGE-M3 cosine + BM25, fused with RRF."""
import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select

from ..core import db
from ..llm.ollama_client import Ollama
from .bm25 import BM25
from .normalize import tokens

STOP = {"the", "a", "an", "is", "are", "do", "does", "you", "your", "i", "my", "me", "to", "of", "for", "in", "on",
        "it", "can", "what", "how", "please", "we", "and", "or", "have", "be", "this", "that", "with"}


@dataclass
class Hit:
    chunk_id: int
    source: str
    location: str
    text: str
    cosine: float
    bm25: float
    score: float


class Index:
    def __init__(self, kb_id: int, rows: list):
        self.kb_id = kb_id
        self.rows = rows
        self.vecs = np.vstack([np.frombuffer(r.embedding, dtype=np.float32) for r in rows]) if rows else None
        self.bm25 = BM25([[w for w in tokens(r.text) if w not in STOP] for r in rows])


_lock = threading.Lock()
_index: Index | None = None


def invalidate() -> None:
    global _index
    with _lock:
        _index = None


def get_index() -> Index | None:
    global _index
    with _lock:
        if _index is not None:
            return _index
        with db.session() as s:
            kb = s.scalar(select(db.KnowledgeBase.id).where(db.KnowledgeBase.active.is_(True)))
            if kb is None:
                return None
            rows = s.scalars(select(db.KnowledgeChunk).where(db.KnowledgeChunk.kb_id == kb)).all()
        _index = Index(kb, list(rows))
        return _index


def search(query: str, ollama: Ollama, top_k: int = 4, extra_terms: str = "") -> list[Hit]:
    idx = get_index()
    if idx is None or not idx.rows:
        return []
    qv = ollama.embed([query])[0]
    cos = idx.vecs @ qv
    bm = idx.bm25.scores([w for w in tokens(f"{query} {extra_terms}") if w not in STOP])
    n = len(idx.rows)
    fused = np.zeros(n, dtype=np.float32)
    for sig in (cos, bm):
        if not sig.any():
            continue
        ranks = np.empty(n, dtype=np.int64)
        ranks[np.argsort(-sig)] = np.arange(n)
        part = 1.0 / (20 + ranks + 1)
        part[sig <= 0] = 0
        fused += part
    order = np.argsort(-fused)[:top_k]
    bmax = float(bm.max()) or 1.0
    return [Hit(idx.rows[i].id, idx.rows[i].source, idx.rows[i].location, idx.rows[i].text,
                float(cos[i]), float(bm[i] / bmax), float(fused[i])) for i in order]
