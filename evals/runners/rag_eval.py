"""Retrieval evaluation: every variant (and ablations of `best`) on the dev set, per persona and job type.

python -m evals.runners.rag_eval [--variants v0,v1,...] [--ablate] [--limit N] [--tag NAME]
Writes evals/results/rag_<tag>.json and .csv. Requirements come from the Job Analyst (the
model profile in config), never from gold labels.
"""
from __future__ import annotations

import argparse
import csv
import time
from dataclasses import replace

from agent import settings
from agent.nodes.analyst import analyze
from evals.runners.common import (PERSONAS, RESULTS, load_dev, load_jobs, mean, mrr, ndcg_at, pct, public,
                                  recall_at, write)
from rag.pipeline import Retriever
from rag.variants import VARIANTS


def ablations(best):
    out = {}
    if best.query != "whole":
        out["best-no_decompose"] = replace(best, name="best-no_decompose", query="whole")
    if best.retrieval == "hybrid":
        out["best-no_bm25"] = replace(best, name="best-no_bm25", retrieval="dense")
    if not best.multi_vector:
        out["best+multivector"] = replace(best, name="best+multivector", multi_vector=True)
    if best.multi_vector:
        out["best-no_multivector"] = replace(best, name="best-no_multivector", multi_vector=False)
    if best.contextual:
        out["best-no_context"] = replace(best, name="best-no_context", contextual=False)
    if best.chunking == "structural":
        out["best-fixed_chunks"] = replace(best, name="best-fixed_chunks", chunking="fixed")
    if best.outcome_boost:
        out["best-no_outcome"] = replace(best, name="best-no_outcome", outcome_boost=0.0)
    return out


def job_type(g: dict) -> str:
    return "4+_requirements" if len(g["requirements"]) >= 4 else "1-3_requirements"


def run(variants: dict, limit: int | None = None, split: str = "dev") -> dict:
    jobs = load_jobs()
    specs = {}
    results = {}
    for pkey in PERSONAS:
        dev = [g for g in load_dev(pkey, split) if g["relevant_projects"]][:limit]
        for g in dev:
            if g["job_id"] not in specs:
                specs[g["job_id"]] = analyze(public(jobs[g["job_id"]]))
        for vname, cfg in variants.items():
            try:
                r = Retriever(pkey, cfg)
            except Exception as e:  # e.g. reranker weights unavailable offline
                results.setdefault(vname, {})["error"] = f"{type(e).__name__}: {e}"[:300]
                continue
            rows = []
            for g in dev:
                job = public(jobs[g["job_id"]])
                t0 = time.time()
                try:
                    hits = r.retrieve(job, specs[g["job_id"]].requirements, k=10)
                except Exception as e:
                    results.setdefault(vname, {})["error"] = f"{type(e).__name__}: {e}"[:300]
                    break
                lat = time.time() - t0
                ranked = [h.unit for h in hits]
                gold = g["relevant_projects"]
                rows.append({"job_id": g["job_id"], "persona": pkey, "type": job_type(g), "category": g["category"],
                             "recall5": recall_at(ranked, gold, 5), "mrr": mrr(ranked, gold),
                             "ndcg10": ndcg_at(ranked, gold, 10), "latency_s": lat})
            results.setdefault(vname, {}).setdefault("rows", []).extend(rows)
    summary = {}
    for vname, res in results.items():
        rows = res.get("rows", [])
        if not rows:
            summary[vname] = {"error": res.get("error")}
            continue
        s = {"n": len(rows), "recall5": mean(r["recall5"] for r in rows), "mrr": mean(r["mrr"] for r in rows),
             "ndcg10": mean(r["ndcg10"] for r in rows), "p50_latency_s": pct([r["latency_s"] for r in rows], 0.5),
             "p95_latency_s": pct([r["latency_s"] for r in rows], 0.95), "by_persona": {}, "by_type": {}}
        for p in PERSONAS:
            pr = [r for r in rows if r["persona"] == p]
            s["by_persona"][p] = {"n": len(pr), "recall5": mean(r["recall5"] for r in pr), "ndcg10": mean(r["ndcg10"] for r in pr)}
        for t in ("1-3_requirements", "4+_requirements"):
            tr = [r for r in rows if r["type"] == t]
            s["by_type"][t] = {"n": len(tr), "recall5": mean(r["recall5"] for r in tr), "ndcg10": mean(r["ndcg10"] for r in tr)}
        if res.get("error"):
            s["error"] = res["error"]
        summary[vname] = s
    return {"summary": summary, "rows": {k: v.get("rows", []) for k, v in results.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="v0,v1,v2,v3,v4,v5,v6,v7,v8,best")
    ap.add_argument("--ablate", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--split", default="dev", choices=["dev", "heldout"])
    a = ap.parse_args()
    vs = {v: VARIANTS[v] for v in a.variants.split(",")}
    if a.ablate:
        vs.update(ablations(VARIANTS["best"]))
    out = run(vs, a.limit, a.split)
    tag = a.tag or settings.get("models.profile")
    out["config"] = {"profile": settings.get("models.profile"), "embeddings": settings.get("rag.embeddings"),
                     "variants": {k: v.__dict__ for k, v in vs.items()}}
    p = write(f"rag_{tag}", out)
    with open(RESULTS / f"rag_{tag}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "n", "recall5", "mrr", "ndcg10", "p95_latency_s", "error"])
        for k, s in out["summary"].items():
            w.writerow([k, s.get("n"), s.get("recall5"), s.get("mrr"), s.get("ndcg10"), s.get("p95_latency_s"), s.get("error", "")])
    for k, s in out["summary"].items():
        print(f"{k:22s} n={s.get('n')} R@5={s.get('recall5')} MRR={s.get('mrr')} nDCG@10={s.get('ndcg10')} "
              f"p95={s.get('p95_latency_s')} {s.get('error', '')[:60] if s.get('error') else ''}")
    print("->", p)


if __name__ == "__main__":
    main()
