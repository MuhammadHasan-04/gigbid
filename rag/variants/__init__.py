"""Variant registry. `best` is the configuration chosen by evals/runners/rag_eval.py (see docs/DATA_CARD.md)."""
from rag.pipeline import RetrievalConfig
from rag.variants import (v0_naive, v1_decompose, v2_hybrid, v3_rerank, v4_outcome, v5_multivector,
                          v6_contextual, v7_hyde, v8_corrective)

VARIANTS: dict[str, RetrievalConfig] = {
    "v0": v0_naive.CONFIG, "v1": v1_decompose.CONFIG, "v2": v2_hybrid.CONFIG, "v3": v3_rerank.CONFIG,
    "v4": v4_outcome.CONFIG, "v5": v5_multivector.CONFIG, "v6": v6_contextual.CONFIG, "v7": v7_hyde.CONFIG,
    "v8": v8_corrective.CONFIG,
}
# Updated after each evaluation run; the decision paragraph lives in docs/DATA_CARD.md.
# Chosen by evals/runners/rag_sweep.py (64-config grid, primary metric nDCG@10 on dev, heuristic profile):
# winner dec-hyb-mv0-cx1-str -> evals/results/rag_sweep_heuristic.json
VARIANTS["best"] = RetrievalConfig(name="best", chunking="structural", query="decompose", retrieval="hybrid",
                                   multi_vector=False, contextual=True, outcome_boost=0.0)


def get(name: str) -> RetrievalConfig:
    return VARIANTS[name]
