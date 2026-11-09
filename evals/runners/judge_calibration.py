"""LLM-judge calibration (B4): the author labels 30 proposals; report Cohen's kappa with the judge.

Step 1  python -m evals.runners.judge_calibration export   -> evals/datasets/judge_labels.csv (blank human_score)
Step 2  a human fills `human_score` (1-5, rubric in agent/prompts/judge.md) WITHOUT looking at judge scores
Step 3  python -m evals.runners.judge_calibration score    -> evals/results/judge_calibration.json
"""
from __future__ import annotations

import csv
import json
import random
import sys

from evals.runners.common import DATASETS, RESULTS, load_jobs, write

CSV = DATASETS / "judge_labels.csv"


def export(src: str = "pipeline_open_dev.json"):
    f = RESULTS / src
    if not f.exists():
        f = sorted(RESULTS.glob("pipeline_*dev*.json"))[-1]
    rows = [r for r in json.loads(f.read_text())["rows"] if r.get("cover_letter")]
    random.Random(30).shuffle(rows)
    jobs = load_jobs()
    with open(CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "job_id", "job_title", "job_description", "proposal", "human_score"])
        for i, r in enumerate(rows[:30]):
            j = jobs[r["job_id"]]
            w.writerow([i, r["job_id"], j["title"], j["description"][:600], r["cover_letter"], ""])
    print(f"wrote {CSV} from {f.name}; fill human_score (1-5) using agent/prompts/judge.md")


def kappa(a: list[int], b: list[int], weights: str | None = None) -> float:
    cats = [1, 2, 3, 4, 5]
    n = len(a)
    obs = [[0] * 5 for _ in cats]
    for x, y in zip(a, b):
        obs[x - 1][y - 1] += 1
    pa = [sum(obs[i]) / n for i in range(5)]
    pb = [sum(obs[i][j] for i in range(5)) / n for j in range(5)]
    w = (lambda i, j: ((i - j) ** 2) / 16) if weights == "quadratic" else (lambda i, j: 0 if i == j else 1)
    po = sum(w(i, j) * obs[i][j] / n for i in range(5) for j in range(5))
    pe = sum(w(i, j) * pa[i] * pb[j] for i in range(5) for j in range(5))
    return round(1 - po / pe, 4) if pe else 1.0


def score():
    from evals.runners.pipeline_eval import judge
    rows = list(csv.DictReader(open(CSV)))
    rows = [r for r in rows if r["human_score"].strip()]
    if len(rows) < 30:
        print(f"only {len(rows)} labelled items; the assignment asks for 30")
    jobs = load_jobs()
    human, model, items = [], [], []
    for r in rows:
        s = judge(jobs[r["job_id"]], r["proposal"])
        if s is None:
            raise SystemExit("judge needs a model endpoint (MODEL_PROFILE=open)")
        human.append(int(r["human_score"]))
        model.append(int(s))
        items.append({"item": r["item"], "job_id": r["job_id"], "human": int(r["human_score"]), "judge": int(s)})
    out = {"n": len(items), "cohen_kappa": kappa(human, model), "quadratic_weighted_kappa": kappa(human, model, "quadratic"),
           "exact_agreement": round(sum(h == m for h, m in zip(human, model)) / len(items), 4),
           "within_one": round(sum(abs(h - m) <= 1 for h, m in zip(human, model)) / len(items), 4),
           "disagreements": [i for i in items if abs(i["human"] - i["judge"]) >= 2], "items": items}
    write("judge_calibration", out)
    print({k: v for k, v in out.items() if k not in ("items", "disagreements")})


if __name__ == "__main__":
    {"export": export, "score": score}[sys.argv[1]]()
