"""GigSim stand-in REST API.

Run: uvicorn gigsim.server:app --port 8081
Behaviour that matters to GigBid:
  * bearer-token auth (GIGSIM_API_TOKEN), per-token rate limit (GIGSIM_RPM, default 60/min) -> 429
  * occasional 5xx errors (GIGSIM_ERROR_RATE, default 0.02) -> clients must retry with backoff
  * Connects balance per freelancer; submit spends Connects exactly once per Idempotency-Key
  * a simulated clock: stream jobs become visible as simulated minutes pass
  * simulated clients decide view / reply / interview / hire (gigsim.client_model)
State is persisted to data/runtime/gigsim_state.json so a restart keeps proposals and threads.

Real data (GIGSIM_REAL_JOBS=1): ~1.3k real Upwork posts and their clients' public stats from Kaggle
(data/real/, built by scripts/ingest_kaggle.py) are added to the job board next to the synthetic jobs.
Every job and client carries `source` = "real" | "synthetic"; /v1/market/stats adds a `real` block with
awarded-contract and 2024-posting percentiles. Simulated client preferences stay synthetic for all clients.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gigsim.client_model import REPLY_TEMPLATES, must_haves, simulate_outcome

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "gigsim"
STATE_FILE = Path(os.getenv("GIGSIM_STATE_FILE", ROOT / "data" / "runtime" / "gigsim_state.json"))
TOKEN = os.getenv("GIGSIM_API_TOKEN", "gigsim-dev-token")
ADMIN_TOKEN = os.getenv("GIGSIM_ADMIN_TOKEN", "gigsim-admin-token")
RPM = int(os.getenv("GIGSIM_RPM", "60"))
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", "0.02"))
POLICY_VERSION = int(os.getenv("GIGSIM_POLICY_VERSION", "1"))

app = FastAPI(title="GigSim (stand-in)", version="0.2.0")
_lock = threading.RLock()
_rng = random.Random(int(os.getenv("GIGSIM_SEED", "7")))


def _load(name: str):
    return json.loads((DATA / name).read_text())


JOBS: dict[str, dict] = {j["job_id"]: j for j in _load("jobs.json")}
STREAM: list[dict] = _load("stream.json")
for j in STREAM:
    JOBS[j["job_id"]] = j
HELDOUT_DIR = ROOT / "evals" / "heldout"
if os.getenv("GIGSIM_INCLUDE_HELDOUT") == "1" and HELDOUT_DIR.exists():
    for f in HELDOUT_DIR.glob("jobs_*.json"):
        for j in json.loads(f.read_text()):
            JOBS[j["job_id"]] = j
CLIENTS: dict[str, dict] = {c["client_id"]: c for c in _load("clients.json")}
for _j in JOBS.values():
    _j.setdefault("source", "synthetic")
for _c in CLIENTS.values():
    _c.setdefault("source", "synthetic")
HISTORY: list[dict] = _load("history.json")
REAL = ROOT / "data" / "real"
REAL_MARKET: dict = json.loads((REAL / "market_real.json").read_text())["by_category"] if (REAL / "market_real.json").exists() else {}
N_REAL = 0
if os.getenv("GIGSIM_REAL_JOBS", "0") == "1" and (REAL / "jobs_real.json.gz").exists():
    _real = json.loads(gzip.decompress((REAL / "jobs_real.json.gz").read_bytes()))
    _real.sort(key=lambda j: hashlib.sha1(j["job_id"].encode()).hexdigest())
    for _i, _j in enumerate(_real):
        # spread real posts over the simulated clock like the synthetic stream (a few already visible)
        _j["posted_offset_min"] = -600 + _i * 3
        JOBS[_j["job_id"]] = _j
    for _c in json.loads((REAL / "clients_real.json").read_text()):
        CLIENTS[_c["client_id"]] = _c
    N_REAL = len(_real)
FREELANCERS: dict[str, dict] = {f["freelancer_id"]: f for f in _load("freelancers.json")}


def _fresh_state() -> dict:
    return {"clock_min": 0, "started": time.time(), "connects": {fid: 200 for fid in FREELANCERS},
            "proposals": {}, "threads": {}, "idempotency": {}, "ledger": []}


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return _fresh_state()


STATE = _load_state()


def _save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE))
    tmp.replace(STATE_FILE)


# ------------------------------------------------------------------ middleware: auth, rate limit, chaos
_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def chaos_and_limits(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json") or request.url.path.startswith("/v1/admin"):
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    tok = auth.removeprefix("Bearer ").strip()
    if tok != TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    now = time.time()
    q = _hits[tok]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RPM:
        return JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
    q.append(now)
    if request.method == "GET" and _rng.random() < ERROR_RATE:
        return JSONResponse({"error": "upstream_unavailable"}, status_code=503)
    return await call_next(request)


def admin(authorization: str = Header("")):
    if authorization.removeprefix("Bearer ").strip() != ADMIN_TOKEN:
        raise HTTPException(401, "admin token required")


def public_job(j: dict) -> dict:
    out = {k: v for k, v in j.items() if not k.startswith("_")}
    out["posted_minutes_ago"] = STATE["clock_min"] - j.get("posted_offset_min", -10_000)
    return out


def _pub(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def visible(j: dict) -> bool:
    return j.get("posted_offset_min", -1) <= STATE["clock_min"]


# ------------------------------------------------------------------ read endpoints
@app.get("/health")
def health():
    return {"ok": True, "jobs": len(JOBS), "real_jobs": N_REAL, "clock_min": STATE["clock_min"], "policy_version": POLICY_VERSION}


@app.get("/v1/jobs")
def search_jobs(q: str = "", category: str | None = None, ids_prefix: str | None = None,
                posted_within_min: int | None = None, limit: int = Query(20, le=100), offset: int = 0):
    terms = [t for t in q.lower().split() if t]
    res = []
    for j in JOBS.values():
        if not visible(j):
            continue
        if ids_prefix and not j["job_id"].startswith(ids_prefix):
            continue
        if category and j["category"] != category:
            continue
        if posted_within_min is not None and "posted_offset_min" in j and STATE["clock_min"] - j["posted_offset_min"] > posted_within_min:
            continue
        if posted_within_min is not None and "posted_offset_min" not in j:
            continue
        hay = (j["title"] + " " + j["description"]).lower()
        if terms and not all(t in hay for t in terms):
            continue
        res.append(public_job(j))
    # newest first (like a real job feed); the fixed dev/held-out sets have no post time and come last
    res.sort(key=lambda j: j["posted_minutes_ago"])
    return {"total": len(res), "jobs": res[offset: offset + limit]}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str):
    j = JOBS.get(job_id)
    if not j or not visible(j):
        raise HTTPException(404, "job not found")
    return public_job(j)


@app.get("/v1/clients/{client_id}")
def client_history(client_id: str):
    c = CLIENTS.get(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    return {k: v for k, v in c.items() if not k.startswith("_")}


@app.get("/v1/market/stats")
def market_stats(category: str):
    xs = sorted(h["awarded_price"] for h in HISTORY if h["category"] == category)
    if not xs:
        raise HTTPException(404, "unknown category")
    pick = lambda q: xs[int(q * (len(xs) - 1))]
    out = {"category": category, "n": len(xs), "p25": pick(0.25), "p50": pick(0.5), "p75": pick(0.75), "source": "synthetic",
           "p90": pick(0.9), "avg_proposals": round(sum(h["proposals_count"] for h in HISTORY if h["category"] == category) / len(xs), 1)}
    if category in REAL_MARKET:
        # real percentiles (Kaggle: awarded contracts + 2024 postings); the synthetic numbers above stay unchanged
        out["real"] = {"source": "real", **REAL_MARKET[category]}
    return out


@app.get("/v1/freelancers/{fid}/connects")
def connects(fid: str):
    if fid not in STATE["connects"]:
        raise HTTPException(404, "freelancer not found")
    return {"freelancer_id": fid, "balance": STATE["connects"][fid]}


@app.get("/v1/policy")
def policy():
    import yaml
    return yaml.safe_load((ROOT / "data" / "policy_pack" / f"policy_v{POLICY_VERSION}.yaml").read_text())


@app.get("/v1/proposals")
def list_proposals(freelancer_id: str):
    return {"proposals": [_pub(p) for p in STATE["proposals"].values() if p["freelancer_id"] == freelancer_id]}


@app.get("/v1/proposals/{pid}")
def get_proposal(pid: str):
    p = STATE["proposals"].get(pid)
    if not p:
        raise HTTPException(404, "proposal not found")
    return _pub(p)


@app.get("/v1/threads")
def list_threads(freelancer_id: str):
    return {"threads": [_pub(t) for t in STATE["threads"].values() if t["freelancer_id"] == freelancer_id]}


@app.get("/v1/threads/{tid}")
def get_thread(tid: str):
    t = STATE["threads"].get(tid)
    if not t:
        raise HTTPException(404, "thread not found")
    return _pub(t)


# ------------------------------------------------------------------ write endpoints
class ProposalIn(BaseModel):
    freelancer_id: str
    job_id: str
    cover_letter: str = Field(min_length=20, max_length=5000)
    bid_amount: float = Field(gt=0, le=1_000_000)
    screening_answers: list[str] = []


def _connects_cost(job: dict) -> int:
    cost = int(job["connects_cost"])
    if POLICY_VERSION >= 2 and job.get("proposals_count", 0) >= 20:
        cost += 2
    return cost


def _idem(key: str | None, scope: str) -> dict | None:
    if key:
        return STATE["idempotency"].get(f"{scope}:{key}")
    return None


@app.post("/v1/proposals")
def create_draft(body: ProposalIn, idempotency_key: str | None = Header(None)):
    with _lock:
        if (prev := _idem(idempotency_key, "draft")):
            return prev
        job = JOBS.get(body.job_id)
        if not job:
            raise HTTPException(404, "job not found")
        if body.freelancer_id not in FREELANCERS:
            raise HTTPException(404, "freelancer not found")
        pid = "prop-" + uuid.uuid4().hex[:10]
        p = {"proposal_id": pid, **body.model_dump(), "status": "draft", "connects_cost": _connects_cost(job),
             "created_clock": STATE["clock_min"], "events": [{"status": "draft", "clock": STATE["clock_min"]}]}
        STATE["proposals"][pid] = p
        if idempotency_key:
            STATE["idempotency"][f"draft:{idempotency_key}"] = p
        _save()
        return p


@app.post("/v1/proposals/{pid}/submit")
def submit(pid: str, idempotency_key: str = Header(...)):
    with _lock:
        if (prev := _idem(idempotency_key, "submit")):
            return {**prev, "idempotent_replay": True}
        p = STATE["proposals"].get(pid)
        if not p:
            raise HTTPException(404, "proposal not found")
        if p["status"] != "draft":
            raise HTTPException(409, f"proposal already {p['status']}")
        fid = p["freelancer_id"]
        cost = p["connects_cost"]
        if STATE["connects"][fid] < cost:
            raise HTTPException(402, "not enough Connects")
        STATE["connects"][fid] -= cost
        STATE["ledger"].append({"freelancer_id": fid, "proposal_id": pid, "connects": -cost, "clock": STATE["clock_min"]})
        job = JOBS[p["job_id"]]
        client = CLIENTS[job["client_id"]]
        persona_skills = set(FREELANCERS[fid]["skills"])
        res = simulate_outcome(job, client, p["cover_letter"] + " " + " ".join(p["screening_answers"]),
                               p["bid_amount"], persona_skills, seed=f"{pid}|{job['job_id']}")
        p["status"] = "submitted"
        p["events"].append({"status": "submitted", "clock": STATE["clock_min"]})
        p["_outcome"] = res
        # outcome events are revealed as the clock advances (viewed +30, replied +120, hired +600)
        p["_pending"] = []
        if res["viewed"]:
            p["_pending"].append({"status": "viewed", "at": STATE["clock_min"] + 30})
        if res["replied"]:
            p["_pending"].append({"status": "replied", "at": STATE["clock_min"] + 120})
            if res["hired"]:
                p["_pending"].append({"status": "hired", "at": STATE["clock_min"] + 600})
        else:
            p["_pending"].append({"status": "lost", "at": STATE["clock_min"] + 1440})
        result = {k: v for k, v in p.items() if not k.startswith("_")}
        STATE["idempotency"][f"submit:{idempotency_key}"] = result
        _save()
        return result


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@app.post("/v1/threads/{tid}/messages")
def send_message(tid: str, msg: MessageIn, idempotency_key: str = Header(...)):
    with _lock:
        if (prev := _idem(idempotency_key, "msg")):
            return {**prev, "idempotent_replay": True}
        t = STATE["threads"].get(tid)
        if not t:
            raise HTTPException(404, "thread not found")
        m = {"message_id": "msg-" + uuid.uuid4().hex[:8], "from": "freelancer", "body": msg.body, "clock": STATE["clock_min"]}
        t["messages"].append(m)
        low = msg.body.lower()
        if any(w in low for w in ["slot", "available", "call", "monday", "tuesday", "wednesday", "thursday", "friday"]):
            t["messages"].append({"message_id": "msg-" + uuid.uuid4().hex[:8], "from": "client",
                                  "body": "The first slot works for me, sending an invite.", "clock": STATE["clock_min"] + 60})
            prop = STATE["proposals"].get(t["proposal_id"])
            if prop and prop["status"] in ("replied", "viewed", "submitted"):
                prop["status"] = "interview"
                prop["events"].append({"status": "interview", "clock": STATE["clock_min"]})
        STATE["idempotency"][f"msg:{idempotency_key}"] = m
        _save()
        return m


# ------------------------------------------------------------------ clock / evaluation helpers
def _advance(minutes: int):
    STATE["clock_min"] += minutes
    for p in STATE["proposals"].values():
        for ev in list(p.get("_pending", [])):
            if ev["at"] <= STATE["clock_min"]:
                p["_pending"].remove(ev)
                p["status"] = ev["status"]
                p["events"].append({"status": ev["status"], "clock": ev["at"]})
                if ev["status"] == "replied":
                    _open_thread(p)


def _open_thread(p: dict):
    job = JOBS[p["job_id"]]
    client = CLIENTS[job["client_id"]]
    seed = random.Random(p["proposal_id"])
    if client["_risky"] and seed.random() < 0.5:
        intent = "scam"
    else:
        intent = seed.choice(["question", "negotiation", "interview", "interview"])
    mh = must_haves(job) or ["the stack"]
    body = REPLY_TEMPLATES[intent].format(skill=mh[0], price=int(p["bid_amount"] * 0.8))
    tid = "th-" + p["proposal_id"][5:]
    STATE["threads"][tid] = {"thread_id": tid, "proposal_id": p["proposal_id"], "job_id": p["job_id"],
                             "client_id": job["client_id"], "freelancer_id": p["freelancer_id"],
                             "messages": [{"message_id": "msg-" + uuid.uuid4().hex[:8], "from": "client", "body": body,
                                           "clock": STATE["clock_min"]}], "_intent": intent}


@app.post("/v1/admin/tick", dependencies=[Depends(admin)])
def tick(minutes: int = 60):
    with _lock:
        _advance(minutes)
        _save()
        return {"clock_min": STATE["clock_min"]}


@app.post("/v1/admin/reset", dependencies=[Depends(admin)])
def reset():
    global STATE
    with _lock:
        STATE = _fresh_state()
        _save()
        return {"ok": True}


class ScoreIn(BaseModel):
    freelancer_id: str
    job_id: str
    cover_letter: str
    bid_amount: float
    screening_answers: list[str] = []


@app.post("/v1/admin/score", dependencies=[Depends(admin)])
def score(body: ScoreIn):
    """Side-effect-free outcome for a proposal (used by the fixed-job-set reply-rate evaluation)."""
    job = JOBS[body.job_id]
    client = CLIENTS[job["client_id"]]
    res = simulate_outcome(job, client, body.cover_letter + " " + " ".join(body.screening_answers), body.bid_amount,
                           set(FREELANCERS[body.freelancer_id]["skills"]), seed=f"eval|{body.job_id}|" + hashlib.sha256(body.cover_letter.encode()).hexdigest()[:8])
    return res


@app.get("/v1/admin/ledger", dependencies=[Depends(admin)])
def ledger():
    return {"ledger": STATE["ledger"], "submitted": [p["proposal_id"] for p in STATE["proposals"].values() if p["status"] != "draft"]}
