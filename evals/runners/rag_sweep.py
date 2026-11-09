"""Pick the shipped retrieval design by measurement: grid over the component switches, ranked by
nDCG@10 on the dev set (pre-declared primary metric), Recall@5 as tie-break. Then confirm on held-out.

python -m evals.runners.rag_sweep
"""
from __future__ import annotations

import itertools

from agent import settings
from evals.runners.rag_eval import run
from evals.runners.common import write
from rag.pipeline import RetrievalConfig


def main():
    grid = {}
    for q, r, mv, cx, ch, ob in itertools.product(["whole", "decompose"], ["dense", "hybrid"], [False, True], [False, True],
                                                  ["fixed", "structural"], [0.0, 0.5]):
        name = f"{q[:3]}-{r[:3]}-mv{int(mv)}-cx{int(cx)}-{ch[:3]}-ob{int(ob > 0)}"
        grid[name] = RetrievalConfig(name=name, chunking=ch, query=q, retrieval=r, multi_vector=mv, contextual=cx, outcome_boost=ob)
    out = run(grid)
    s = out["summary"]
    ranked = sorted(s, key=lambda k: (s[k]["ndcg10"], s[k]["recall5"]), reverse=True)
    top = ranked[0]
    print("top 8:")
    for k in ranked[:8]:
        print(f"  {k:32s} nDCG@10={s[k]['ndcg10']} R@5={s[k]['recall5']} MRR={s[k]['mrr']}")
    write(f"rag_sweep_{settings.get('models.profile')}", {"primary_metric": "ndcg10", "ranked": [{"name": k, **{m: s[k][m] for m in ("recall5", "mrr", "ndcg10")}} for k in ranked],
                                                          "winner": top, "winner_config": grid[top].__dict__})


if __name__ == "__main__":
    main()
