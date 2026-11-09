"""Collect failed dev jobs from a pipeline run and group them into the report's taxonomy.

python -m evals.runners.failure_analysis pipeline_heuristic_dev.json
Taxonomy: missed evidence, wrong skip, wrong bid, mispriced, unsupported claim, generic opening,
compliance miss, injection, tool error.
"""
import json
import sys
from collections import defaultdict

from evals.runners.common import PERSONAS, RESULTS, load_dev, write


def main(name):
    run = json.loads((RESULTS / name).read_text())
    gold = {g["job_id"]: g for p in PERSONAS for g in load_dev(p)}
    cats = defaultdict(list)
    for r in run["rows"]:
        g = gold.get(r["job_id"])
        if not g:
            continue
        item = {"job_id": r["job_id"], "persona": r["persona"], "category": g["category"], "action": r["action"],
                "gold_bid": g["bid"], "gold_reasons": g["skip_reasons"], "fit": r["fit"], "price": r["price"],
                "band": g["fair_price_band"], "trace_id": r["trace_id"]}
        if r.get("error"):
            cats["tool_error"].append({**item, "error": r["error"]})
        elif r["action"] != "bid" and g["bid"]:
            cats["wrong_skip" if (r["fit"] or 0) >= 0.3 else "missed_evidence"].append(item)
        elif r["action"] == "bid" and not g["bid"]:
            cats["wrong_bid"].append(item)
        elif r["action"] == "bid" and r["price"] and not (g["fair_price_band"][0] <= r["price"] <= g["fair_price_band"][1]):
            cats["mispriced"].append(item)
        if r.get("removed_claims"):
            cats["unsupported_claim_removed"].append({**item, "removed": r["removed_claims"][:2]})
        if (r.get("gigsim") or {}).get("generic"):
            cats["generic_opening"].append(item)
        if g["injection"] and r.get("cover_letter") and r.get("is_scam_pred") is False:
            cats["injection_reached_writer"].append({**item, "injection": g["injection"]})
    summary = {k: len(v) for k, v in cats.items()}
    write("failure_analysis", {"source": name, "counts": summary, "examples": {k: v[:6] for k, v in cats.items()}})
    print(summary)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pipeline_heuristic_dev.json")
