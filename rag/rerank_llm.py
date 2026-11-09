"""Pointwise LLM reranker (V3 alternative when cross-encoder weights are unavailable)."""
from __future__ import annotations

from pydantic import BaseModel

from agent import llm
from rag.index.stores import tokenize


class Scores(BaseModel):
    scores: list[float]


def llm_scores(query: str, passages: list[str]) -> list[float]:
    def heuristic() -> Scores:
        q = set(tokenize(query))
        return Scores(scores=[len(q & set(tokenize(p))) / (len(q) or 1) for p in passages])
    numbered = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(passages))
    out = llm.structured("verifier", "rerank", Scores, heuristic, max_tokens=300, query=query, passages=numbered)
    s = out.scores
    return (s + [0.0] * len(passages))[: len(passages)]
