"""Vector and BM25 indexes over chunks (in-process; numpy cosine + rank_bm25).

The vector store is an in-process numpy matrix persisted under data/processed. For a portfolio
of a few hundred items this is faster than any network vector DB and keeps `docker compose up`
small; pgvector is the documented swap (ADR 0003) if a tenant's corpus grows past ~100k chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from rank_bm25 import BM25Okapi

from rag.index.embed import Embedder

TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


def tokenize(text: str) -> list[str]:
    return [t.strip(".-") for t in TOKEN.findall(text.lower()) if len(t) > 1 or t in {"r", "c"}]


@dataclass
class Chunk:
    chunk_id: str
    evidence_id: str
    text: str
    meta: dict
    view: str = "full"  # full | summary | readme | code (V5)
    context: str = ""  # V6 contextual line

    @property
    def unit(self) -> str:
        """Retrieval unit used for evaluation and for the writer: the project when known."""
        return self.meta.get("project_id") or self.evidence_id

    @property
    def index_text(self) -> str:
        return (self.context + "\n" + self.text) if self.context else self.text


@dataclass
class DenseIndex:
    chunks: list[Chunk]
    embedder: Embedder
    matrix: np.ndarray = field(init=False)

    def __post_init__(self):
        self.matrix = self.embedder.embed([c.index_text for c in self.chunks])

    def search(self, query: str, k: int = 20, mask: np.ndarray | None = None) -> list[tuple[int, float]]:
        q = self.embedder.embed([query])[0]
        sims = self.matrix @ q
        if mask is not None:
            sims = np.where(mask, sims, -1e9)
        idx = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in idx if sims[i] > -1e8]


@dataclass
class BM25Index:
    chunks: list[Chunk]
    bm25: BM25Okapi = field(init=False)

    def __post_init__(self):
        self.bm25 = BM25Okapi([tokenize(c.index_text) for c in self.chunks])

    def search(self, query: str, k: int = 20, mask: np.ndarray | None = None) -> list[tuple[int, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        if mask is not None:
            scores = np.where(mask, scores, -1e9)
        idx = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in idx if scores[i] > 0]


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in rankings:
        for rank, i in enumerate(r):
            out[i] = out.get(i, 0.0) + 1.0 / (k + rank + 1)
    return out
