"""V8 agentic: corrective RAG loop in LangGraph.

retrieve (per requirement, hybrid) -> grade each requirement's best evidence -> rewrite the
query for weak requirements (max 1 retry) -> refuse to claim requirements that stay unsupported.
The refused list is passed to the Writer, which must not claim those requirements.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agent import llm
from rag.pipeline import Hit, RetrievalConfig, job_text
from rag.skills import GENERIC
from rag.index.stores import rrf

CONFIG = RetrievalConfig(name="v8", chunking="structural", query="decompose", retrieval="hybrid", corrective=True)


class CState(TypedDict, total=False):
    reqs: list[str]
    queries: dict[str, str]
    hits: dict[str, list]
    grades: dict[str, str]
    attempts: int
    refused: list[str]


class Rewrites(BaseModel):
    queries: dict[str, str]


def _grade(req: str, hits: list[Hit]) -> str:
    if not hits:
        return "none"
    top = hits[:3]
    named = any(req in c.meta.get("skills", []) or req.lower() in c.text.lower() for h in top for c in h.chunks[:3])
    return "strong" if named else "weak"


def corrective_retrieve(retriever, job: dict, reqs: list[str], k: int = 10) -> list[Hit]:
    specific = [r for r in reqs if r not in GENERIC] or reqs or [job.get("title", "")]

    def retrieve(s: CState) -> CState:
        hits = dict(s.get("hits", {}))
        for r in s["reqs"]:
            if s.get("grades", {}).get(r) == "strong":
                continue
            hits[r] = retriever.retrieve_query(s["queries"].get(r, r), k=5)
        return {"hits": hits}

    def grade(s: CState) -> CState:
        return {"grades": {r: _grade(r, s["hits"].get(r, [])) for r in s["reqs"]}}

    def rewrite(s: CState) -> CState:
        weak = [r for r, g in s["grades"].items() if g != "strong"]

        def heuristic() -> Rewrites:
            # no vocabulary leak: reuse the job's own sentence that mentions the requirement
            sents = job_text(job).split(".")
            return Rewrites(queries={r: next((x for x in sents if r.lower() in x.lower()), r) + " project built delivered" for r in weak})
        rw = llm.structured("verifier", "rewrite_query", Rewrites, heuristic, max_tokens=400,
                            job=llm.untrusted("job_post", job_text(job)), requirements=", ".join(weak))
        return {"queries": {**s["queries"], **rw.queries}, "attempts": s.get("attempts", 0) + 1}

    def refuse(s: CState) -> CState:
        return {"refused": [r for r, g in s["grades"].items() if g == "none" or (g == "weak" and not s["hits"].get(r))]}

    def route(s: CState) -> str:
        weak = [r for r, g in s["grades"].items() if g != "strong"]
        return "rewrite" if weak and s.get("attempts", 0) < 1 else "refuse"

    g = StateGraph(CState)
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade)
    g.add_node("rewrite", rewrite)
    g.add_node("refuse", refuse)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route, {"rewrite": "rewrite", "refuse": "refuse"})
    g.add_edge("rewrite", "retrieve")
    g.add_edge("refuse", END)
    out = g.compile().invoke({"reqs": specific, "queries": {r: f"{r} — {job.get('title', '')}" for r in specific},
                              "hits": {}, "grades": {}, "attempts": 0})
    retriever.last_refused = out.get("refused", [])
    rankings, per, first = [], {}, {}
    for r in specific:
        hs = out["hits"].get(r, [])
        rankings.append([h.unit for h in hs])
        for h in hs:
            per.setdefault(h.unit, h)
            first.setdefault(h.unit, r)
    fused = rrf(rankings)
    return [Hit(u, s, per[u].chunks, first.get(u)) for u, s in sorted(fused.items(), key=lambda x: -x[1])[:k]]
