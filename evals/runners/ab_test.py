"""X2 Proposal experiments: strategy A (evidence-first) vs B (question-first, short) on the same jobs in
GigSim, with a paired significance test on reply rate.

python -m evals.runners.ab_test [--limit-per-persona N]
Runs the bid graph twice per job (forced A, forced B), scores both drafts with GigSim's deterministic
simulated clients, then reports reply rates, McNemar's exact test (paired) and a two-proportion z-test.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys

from agent import settings
from evals.runners.common import RESULTS, write


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from discordant pair counts b (A yes, B no) and c (A no, B yes)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def two_prop_z(x1, n1, x2, n2) -> tuple[float, float]:
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else 0
    z = ((x1 / n1) - (x2 / n2)) / se if se else 0.0
    pval = math.erfc(abs(z) / math.sqrt(2))
    return round(z, 3), round(pval, 4)


def run_arm(arm: str, limit: int | None, profile: str) -> dict:
    env = dict(os.environ, GIGBID_FORCE_STRATEGY=arm, MODEL_PROFILE=profile)
    cmd = [sys.executable, "-m", "evals.runners.pipeline_eval", "--tag", f"ab_{arm}_{profile}"]
    if limit:
        cmd += ["--limit-per-persona", str(limit)]
    subprocess.run(cmd, env=env, check=True)
    return json.loads((RESULTS / f"pipeline_ab_{arm}_{profile}.json").read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-per-persona", type=int, default=None)
    a = ap.parse_args()
    profile = settings.get("models.profile")
    A, B = run_arm("A", a.limit_per_persona, profile), run_arm("B", a.limit_per_persona, profile)
    ra = {r["job_id"]: r for r in A["rows"] if r.get("gigsim")}
    rb = {r["job_id"]: r for r in B["rows"] if r.get("gigsim")}
    both = sorted(set(ra) & set(rb))
    ya = [ra[j]["gigsim"]["replied"] for j in both]
    yb = [rb[j]["gigsim"]["replied"] for j in both]
    b = sum(x and not y for x, y in zip(ya, yb))
    c = sum(y and not x for x, y in zip(ya, yb))
    z, pz = two_prop_z(sum(ya), len(ya), sum(yb), len(yb))
    by_p = {}
    for p in ("ai_ml", "fullstack", "data_analyst"):
        js = [j for j in both if ra[j]["persona"] == p]
        by_p[p] = {"n": len(js), "reply_A": round(sum(ra[j]["gigsim"]["replied"] for j in js) / len(js), 4) if js else None,
                   "reply_B": round(sum(rb[j]["gigsim"]["replied"] for j in js) / len(js), 4) if js else None}
    out = {"profile": profile, "n_paired": len(both), "reply_rate_A": round(sum(ya) / len(ya), 4), "reply_rate_B": round(sum(yb) / len(yb), 4),
           "hire_rate_A": round(sum(ra[j]["gigsim"]["hired"] for j in both) / len(both), 4),
           "hire_rate_B": round(sum(rb[j]["gigsim"]["hired"] for j in both) / len(both), 4),
           "discordant_A_only": b, "discordant_B_only": c, "mcnemar_exact_p": round(mcnemar_exact(b, c), 4),
           "two_proportion_z": z, "two_proportion_p": pz, "by_persona": by_p,
           "mean_p_reply_A": round(sum(ra[j]["gigsim"]["p_reply"] for j in both) / len(both), 4),
           "mean_p_reply_B": round(sum(rb[j]["gigsim"]["p_reply"] for j in both) / len(both), 4)}
    write(f"ab_test_{profile}", out)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
