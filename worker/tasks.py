"""Background work (E1): scouting, bid runs, approval resumes, conversations, marketplace sync.

Run by the Arq worker (worker/main.py) on Redis; with RUN_INLINE=1 (single-container demo) the API
runs the same functions as background asyncio tasks. Never inside a web request.
Idempotency: one graph thread per (user, job); a job already analysed is never analysed twice,
and resumes reuse the thread's checkpoint + idempotency keys, so a worker restart cannot
double-analyse or double-submit.
"""
from __future__ import annotations

import hashlib
import logging
import time

from agent import tracing
from agent.mcp_client import MCPTools, ToolUnavailable
from agent.memory import promotion_rules
from agent.runtime import get_runtime
from apps.api import db

log = logging.getLogger("gigbid.worker")
logging.getLogger("httpx").setLevel(logging.WARNING)


async def publish(user: str, thread: str, trace_id: str, event: dict):
    await db.q("insert into run_events (user_id, thread_id, trace_id, event) values (%s,%s,%s,%s)",
               user, thread, trace_id, db.j(event))


def content_hash(job: dict) -> str:
    t = (job.get("title", "") + "|" + job.get("description", "").replace("(reposted)", "")).lower()
    return hashlib.sha256(" ".join(t.split()).encode()).hexdigest()[:20]


async def scout(user_id: str) -> dict:
    """Run the user's saved searches, de-duplicate (id and content hash), queue new jobs."""
    u = await db.q1("select * from users where id=%s", user_id)
    if not u or not u["persona"]:
        return {"skipped": "not onboarded"}
    s = u["settings"]
    tools = MCPTools(user=user_id)
    queued, dupes = [], 0
    for search in s.get("saved_searches", []):
        try:
            res = await tools.call("scout", "marketplace.search_jobs", query=search.get("query", ""), limit=search.get("limit", 15),
                                   posted_within_min=search.get("posted_within_min"))
        except ToolUnavailable as e:
            return {"error": "marketplace_unavailable", "detail": str(e)}
        for job in res.get("jobs", []):
            if job["budget"].get("max", 0) < s.get("filters", {}).get("min_budget", 0):
                continue
            h = content_hash(job)
            exists = await db.q1("select job_id from jobs_seen where user_id=%s and (job_id=%s or content_hash=%s)", user_id, job["job_id"], h)
            if exists:
                dupes += 1
                continue
            await db.q("insert into jobs_seen (user_id, job_id, content_hash, title, category, posted, status) values (%s,%s,%s,%s,%s,%s,'queued') "
                       "on conflict do nothing", user_id, job["job_id"], h, job["title"], job.get("category"), db.j(job))
            queued.append(job["job_id"])
    return {"queued": queued, "duplicates": dupes}


async def analyse(user_id: str, job_id: str, trace_id: str | None = None) -> dict:
    u = await db.q1("select * from users where id=%s", user_id)
    row = await db.q1("select * from jobs_seen where user_id=%s and job_id=%s", user_id, job_id)
    rt = await get_runtime()
    thread = rt.bid_thread(user_id, job_id)
    if row and row["status"] not in ("queued", "dead_letter", "error") and row.get("thread_id"):
        return {"skipped": "already analysed", "status": row["status"]}
    tid = trace_id or tracing.new_trace_id()
    t0 = time.time()
    await db.q("insert into jobs_seen (user_id, job_id, status, thread_id, trace_id) values (%s,%s,'analysing',%s,%s) "
               "on conflict (user_id, job_id) do update set status='analysing', thread_id=excluded.thread_id, trace_id=excluded.trace_id, updated_at=now()",
               user_id, job_id, thread, tid)
    st = await rt.state(thread, user_id)
    inputs = None if st["values"] else {"user_id": user_id, "persona": u["persona"], "freelancer_id": u["freelancer_id"],
                                        "job_id": job_id, "trace_id": tid, "autonomy": u["settings"].get("autonomy", "suggest")}
    if inputs is not None and row and row.get("posted"):
        inputs["job"] = row["posted"]  # the scout already fetched it; saves a marketplace call
    extra = {"hourly_floor": u["settings"].get("hourly_floor")}
    async for ev in rt.stream(thread, user_id, inputs, tid, **extra):
        await publish(user_id, thread, tid, ev)
    await sync_job_row(user_id, job_id, latency=time.time() - t0)
    return {"thread": thread, "trace_id": tid}


async def sync_job_row(user_id: str, job_id: str, latency: float | None = None):
    rt = await get_runtime()
    thread = rt.bid_thread(user_id, job_id)
    s = await rt.state(thread, user_id)
    v = s["values"]
    job = v.get("job") or {}
    dec, risk, fit, price = v.get("decision") or {}, v.get("risk") or {}, v.get("fit") or {}, v.get("price") or {}
    summ = tracing.summarize(v.get("trace_id", ""))
    await db.q("""update jobs_seen set status=%s, action=%s, fit_score=%s, risk_score=%s, is_scam=%s, flags=%s, price=%s,
                  connects_cost=%s, reasons=%s, attention_reason=%s, title=coalesce(title,%s), category=coalesce(category,%s),
                  posted=coalesce(posted,%s), tokens=%s, usd=%s, latency_s=coalesce(%s, latency_s), updated_at=now()
                  where user_id=%s and job_id=%s""",
               v.get("status"), dec.get("action"), fit.get("fit_score"), risk.get("risk_score"), risk.get("is_scam"),
               db.j(risk.get("flags", [])), price.get("amount"), price.get("connects_cost") or job.get("connects_cost"),
               db.j(dec.get("reasons", [])), v.get("attention_reason"), job.get("title"), job.get("category"), db.j(job),
               summ["tokens"], summ["usd"], latency, user_id, job_id)


async def resume(user_id: str, thread: str, decision: dict) -> dict:
    rt = await get_runtime()
    st = await rt.state(thread, user_id)
    tid = st["values"].get("trace_id") or tracing.new_trace_id()
    async for ev in rt.stream(thread, user_id, __import__("langgraph.types", fromlist=["Command"]).Command(resume=decision), tid):
        await publish(user_id, thread, tid, ev)
    v = (await rt.state(thread, user_id))["values"]
    if thread.startswith("bid:"):
        await sync_job_row(user_id, v["job_id"])
        if decision.get("action") == "reject":
            await db.q("insert into rejections (user_id, job_id, reason) values (%s,%s,%s)", user_id, v["job_id"], decision.get("reason", ""))
        if v.get("status") == "submitted":
            sub = v.get("submission") or {}
            await db.q("insert into pipeline (user_id, proposal_id, job_id, title, category, status, bid, connects, cover_letter, events) "
                       "values (%s,%s,%s,%s,%s,'submitted',%s,%s,%s,%s) on conflict (user_id, proposal_id) do nothing",
                       user_id, sub.get("proposal_id"), v["job_id"], v["job"]["title"], v["job"].get("category"),
                       (v.get("approval") or {}).get("bid_amount"), sub.get("connects_cost"),
                       (v.get("approval") or {}).get("cover_letter"), db.j(sub.get("events", [])))
    else:
        await db.q("update conversations set status=%s, updated_at=now() where user_id=%s and graph_thread=%s", v.get("status"), user_id, thread)
    return {"status": v.get("status")}


async def converse(user_id: str, thread_id: str) -> dict:
    u = await db.q1("select * from users where id=%s", user_id)
    rt = await get_runtime()
    gthread = rt.conv_thread(user_id, thread_id) + f":{int(time.time())}"
    tid = tracing.new_trace_id()
    p = await db.q1("select * from conversations where user_id=%s and thread_id=%s", user_id, thread_id)
    job = {}
    if p and p.get("job_id"):
        jr = await db.q1("select title, price from jobs_seen where user_id=%s and job_id=%s", user_id, p["job_id"])
        job = {"title": (jr or {}).get("title"), "bid_amount": (jr or {}).get("price")}
    inputs = {"user_id": user_id, "persona": u["persona"], "freelancer_id": u["freelancer_id"], "thread_id": thread_id,
              "trace_id": tid, "job": job}
    await db.q("update conversations set graph_thread=%s, status='drafting', updated_at=now() where user_id=%s and thread_id=%s",
               gthread, user_id, thread_id)
    async for ev in rt.stream(gthread, user_id, inputs, tid):
        await publish(user_id, gthread, tid, ev)
    v = (await rt.state(gthread, user_id))["values"]
    await db.q("update conversations set status=%s, intent=%s where user_id=%s and thread_id=%s", v.get("status"),
               (v.get("intent") or {}).get("intent"), user_id, thread_id)
    return {"graph_thread": gthread}


async def sync_marketplace(user_id: str) -> dict:
    """Pull proposal status changes and new client messages; feed outcome memory; start conversations."""
    u = await db.q1("select * from users where id=%s", user_id)
    if not u or not u["freelancer_id"]:
        return {}
    tools = MCPTools(user=user_id)
    try:
        props = (await tools.call("ui", "marketplace.list_proposals", freelancer_id=u["freelancer_id"]))["data"].get("proposals", [])
        threads = (await tools.call("ui", "marketplace.list_messages", freelancer_id=u["freelancer_id"]))["data"].get("threads", [])
    except ToolUnavailable as e:
        return {"error": str(e)}
    changed = 0
    for p in props:
        row = await db.q1("select status, category, cover_letter from pipeline where user_id=%s and proposal_id=%s", user_id, p["proposal_id"])
        if not row or row["status"] == p["status"]:
            continue
        await db.q("update pipeline set status=%s, events=%s, updated_at=now() where user_id=%s and proposal_id=%s",
                   p["status"], db.j(p.get("events", [])), user_id, p["proposal_id"])
        await promotion_rules.record_outcome(user_id, row["category"] or "unknown", row["cover_letter"] or "", p["status"])
        changed += 1
    new_threads = []
    for t in threads:
        last = t["messages"][-1] if t.get("messages") else None
        row = await db.q1("select * from conversations where user_id=%s and thread_id=%s", user_id, t["thread_id"])
        if not row:
            await db.q("insert into conversations (user_id, thread_id, job_id, status, last_client_msg) values (%s,%s,%s,'new',%s)",
                       user_id, t["thread_id"], t.get("job_id"), last["body"] if last else "")
            new_threads.append(t["thread_id"])
        elif last and last["from"] == "client" and last["body"] != row["last_client_msg"]:
            await db.q("update conversations set last_client_msg=%s, status='new' where user_id=%s and thread_id=%s",
                       last["body"], user_id, t["thread_id"])
            new_threads.append(t["thread_id"])
    return {"status_changes": changed, "new_messages": new_threads}
