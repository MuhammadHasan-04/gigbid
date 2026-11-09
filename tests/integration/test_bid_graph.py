"""Graph runs against GigSim (in-process): parallel analysis, scam skip, approval interrupt,
crash-and-resume submits exactly once, critic loop bounded, budget exceeded -> needs_attention."""
import asyncio
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from tests.fakes import gigsim_adapter


@pytest.fixture(autouse=True)
def port():
    from mcp_servers.marketplace import server
    server.set_port(gigsim_adapter())
    from agent.memory.store import set_store
    set_store(InMemoryStore())


def gold(job_id):
    for line in open("evals/datasets/dev_ai_ml.jsonl"):
        r = json.loads(line)
        if r["job_id"] == job_id:
            return r


def first(pred):
    for line in open("evals/datasets/dev_ai_ml.jsonl"):
        r = json.loads(line)
        if pred(r):
            return r["job_id"]


def inputs(job_id):
    return {"user_id": "t", "persona": "ai_ml", "freelancer_id": "fl-ai-ml", "job_id": job_id, "trace_id": "tr-test", "autonomy": "suggest"}


def test_scam_is_skipped_without_drafting():
    from agent.graphs.bid_graph import build
    g = build(InMemorySaver())
    jid = first(lambda r: r["scam"])
    out = asyncio.run(g.ainvoke(inputs(jid), {"configurable": {"thread_id": "s1"}}))
    assert out["decision"]["action"] == "skip" and out["risk"]["is_scam"]
    assert not out.get("draft")
    nodes = [l["node"] for l in out["log"]]
    assert {"analyst", "risk_assessor", "fit_matcher"} <= set(nodes)


def test_crash_and_resume_submits_exactly_once():
    from agent.graphs.bid_graph import build
    saver = InMemorySaver()
    jid = first(lambda r: r["bid"])
    cfg = {"configurable": {"thread_id": "c1"}}
    out = asyncio.run(build(saver).ainvoke(inputs(jid), cfg))
    assert "__interrupt__" in out
    # "crash": a brand new graph object on the same checkpointer
    g2 = build(saver)
    out2 = asyncio.run(g2.ainvoke(Command(resume={"action": "approve"}), cfg))
    assert out2["status"] == "submitted"
    pid = out2["submission"]["proposal_id"]
    # replay from the checkpoint just before `submit` (= worker crashed after the HTTP call but
    # before the checkpoint was written): the node re-runs with the same idempotency keys
    g3 = build(saver)

    async def replay():
        hist = [h async for h in g3.aget_state_history(cfg)]
        before_submit = next(h for h in hist if h.next == ("submit",))
        return await g3.ainvoke(None, before_submit.config)
    out3 = asyncio.run(replay())
    assert out3["submission"]["proposal_id"] == pid and out3["submission"].get("idempotent_replay")
    from mcp_servers.marketplace.server import port
    letter = out2["approval"]["cover_letter"]
    props = [p for p in port().list_proposals("fl-ai-ml")["proposals"]
             if p["job_id"] == jid and p["status"] != "draft" and p["cover_letter"] == letter]
    assert len(props) == 1 and props[0]["proposal_id"] == pid


def test_reject_with_reason():
    from agent.graphs.bid_graph import build
    g = build(InMemorySaver())
    jid = first(lambda r: r["bid"] and r["job_id"] != first(lambda x: x["bid"]))
    cfg = {"configurable": {"thread_id": "r1"}}
    asyncio.run(g.ainvoke(inputs(jid), cfg))
    out = asyncio.run(g.ainvoke(Command(resume={"action": "reject", "reason": "too far from my niche"}), cfg))
    assert out["status"] == "rejected" and not out.get("submission")


def test_step_budget(monkeypatch):
    monkeypatch.setenv("GIGBID__BUDGETS__MAX_GRAPH_STEPS", "3")
    from agent import settings
    settings.reload()
    from agent.graphs.bid_graph import build
    out = asyncio.run(build(InMemorySaver()).ainvoke(inputs(first(lambda r: r["bid"])), {"configurable": {"thread_id": "b1"}}))
    assert out["status"] == "needs_attention" and "budget" in out["attention_reason"]
    monkeypatch.delenv("GIGBID__BUDGETS__MAX_GRAPH_STEPS")
    settings.reload()
