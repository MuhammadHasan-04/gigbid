"""Produce the public example traces (docs/traces/*.jsonl + an index): a skipped scam, an approved
proposal, a Critic loop, an ignored injected instruction, and a crash-and-resume. Uses the active model profile."""
import asyncio
import json
import os
import shutil
from pathlib import Path

os.environ.setdefault("TRACE_DIR", "docs/traces/raw")
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent import tracing  # noqa: E402
from agent.graphs.bid_graph import build  # noqa: E402
from agent.memory.store import set_store  # noqa: E402
from evals.runners.common import load_dev, load_jobs, public  # noqa: E402

OUT = Path("docs/traces")


async def run(name, job_id, persona="ai_ml", resume=None, crash=False):
    set_store(InMemoryStore())
    saver = InMemorySaver()
    tid = f"tr-public-{name}"
    job = public(load_jobs()[job_id])
    cfg = {"configurable": {"thread_id": tid}}
    tracing.set_trace(tid)
    out = await build(saver).ainvoke({"user_id": "public", "persona": persona, "freelancer_id": {"ai_ml": "fl-ai-ml"}[persona],
                                      "job_id": job_id, "job": job, "trace_id": tid, "autonomy": "suggest"}, cfg)
    if resume:
        if crash:
            tracing.emit("note", "simulated_crash", detail="graph object discarded while waiting for approval; new process resumes from Postgres-equivalent checkpoint")
        out = await build(saver).ainvoke(Command(resume=resume), cfg)
        if crash:
            hist = [h async for h in build(saver).aget_state_history(cfg)]
            before = next(h for h in hist if h.next == ("submit",))
            tracing.emit("note", "replay_submit_node", detail="re-running submit from the checkpoint before it (crash after HTTP call)")
            out = await build(saver).ainvoke(None, before.config)
    return {"name": name, "job_id": job_id, "trace_id": tid, "status": out.get("status"), "decision": (out.get("decision") or {}).get("action"),
            "summary": tracing.summarize(tid), "log": [f"{l['node']}: {l['msg']}" for l in out.get("log", [])]}


async def main():
    shutil.rmtree(OUT / "raw", ignore_errors=True)
    dev = load_dev("ai_ml")
    scam = next(g["job_id"] for g in dev if g["scam"])
    inj = next(g["job_id"] for g in dev if g["injection"] and g["bid"])
    bids = [g["job_id"] for g in dev if g["bid"]]
    res = [await run("skipped-scam", scam), await run("approved-proposal", bids[0], resume={"action": "approve"}),
           await run("injection-ignored", inj), await run("crash-and-resume", bids[1], resume={"action": "approve"}, crash=True)]
    # critic loop: first bid job whose run used a revision
    for j in bids[2:40]:
        r = await run("critic-loop", j)
        if any(l.startswith("writer: draft r1") for l in r["log"]):
            res.append(r)
            break
    (OUT / "index.json").write_text(json.dumps(res, indent=1))
    md = ["# Public traces", "", "Each file in `raw/` is the full PII-masked span log (every node, model call, tool call with arguments and result preview).", ""]
    for r in res:
        md += [f"## {r['name']} ({r['job_id']}): {r['decision']} → {r['status']}", f"Trace: [`raw/{r['trace_id']}.jsonl`](raw/{r['trace_id']}.jsonl)", ""]
        md += [f"1. {x}" for x in r["log"]] + [""]
    (OUT / "README.md").write_text("\n".join(md))
    print([(r["name"], r["status"]) for r in res])


asyncio.run(main())
