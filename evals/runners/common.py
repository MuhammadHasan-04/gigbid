from __future__ import annotations

import json
import math
import platform
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
DATASETS = ROOT / "evals" / "datasets"
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]


def load_dev(persona: str, split: str = "dev") -> list[dict]:
    base = DATASETS if split == "dev" else ROOT / "evals" / "heldout"
    name = f"dev_{persona}.jsonl" if split == "dev" else f"test_{persona}.jsonl"
    return [json.loads(l) for l in (base / name).read_text().splitlines() if l.strip()]


def load_jobs() -> dict[str, dict]:
    jobs = {j["job_id"]: j for j in json.loads((ROOT / "data" / "gigsim" / "jobs.json").read_text())}
    ho = ROOT / "evals" / "heldout"
    if ho.exists():
        for f in ho.glob("jobs_*.json"):
            for j in json.loads(f.read_text()):
                jobs[j["job_id"]] = j
    return jobs


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def recall_at(ranked: list[str], gold: dict, k: int) -> float:
    if not gold:
        return float("nan")
    return len(set(ranked[:k]) & set(gold)) / min(k, len(gold))


def mrr(ranked: list[str], gold: dict) -> float:
    for i, u in enumerate(ranked):
        if u in gold:
            return 1 / (i + 1)
    return 0.0


def ndcg_at(ranked: list[str], gold: dict, k: int) -> float:
    dcg = sum((2 ** gold.get(u, 0) - 1) / math.log2(i + 2) for i, u in enumerate(ranked[:k]))
    ideal = sorted(gold.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else float("nan")


def mean(xs):
    xs = [x for x in xs if x == x]
    return round(sum(xs) / len(xs), 4) if xs else None


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 4)


def meta() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = "unknown"
    return {"commit": commit, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "python": platform.python_version(),
            "machine": platform.machine(), "cpus": __import__("os").cpu_count()}


def write(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps({"meta": meta(), **payload}, indent=1, default=str))
    return p
