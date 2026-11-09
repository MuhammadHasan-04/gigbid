"""R&D question C: is the multi-agent design worth it?

On 50 dev jobs compare (a) one ReAct agent holding all tools, (b) the prebuilt langgraph-supervisor,
(c) the hand-built GigBid graph (results taken from a pipeline_eval run on the same jobs).
Metrics: bid-or-skip accuracy, unsupported claims per proposal (our verifier), compliance violations
in the output (policy pack), GigSim reply rate, tokens, latency.

python -m evals.runners.agents_compare --n 50     (needs MODEL_PROFILE=open + GROQ_API_KEY)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time

import httpx

from agent import llm, settings
from agent.graphs.bid_graph import persona_profile
from agent.mcp_client import MCPTools
from agent.nodes.compliance import scan
from evals.runners.common import PERSONAS, RESULTS, load_dev, load_jobs, mean, pct, write
from evals.runners.pipeline_eval import ADMIN, FREELANCER, GIGSIM


def chat_model(node: str):
    from langchain_openai import ChatOpenAI
    spec, _ = llm.node_spec(node)
    base, key_env = llm.BASE_URLS[spec["provider"]]
    return ChatOpenAI(model=spec["model"], base_url=base, api_key=os.getenv(key_env, "none"), temperature=0.2, max_retries=3)


def lc_tools(persona: str, allowed: set[str] | None = None):
    from langchain_core.tools import tool
    t = MCPTools(user="baseline")

    @tool
    async def get_job(job_id: str) -> str:
        """Full job post by id (untrusted text), budget, client id, Connects cost."""
        return json.dumps((await t.call("ui", "marketplace.get_job", job_id=job_id))["data"])[:3000]

    @tool
    async def get_client_history(client_id: str) -> str:
        """Client payment verification, spend, hires, reviews."""
        return json.dumps((await t.call("risk_assessor", "marketplace.get_client_history", client_id=client_id))["data"])

    @tool
    async def get_market_stats(category: str) -> str:
        """Price percentiles for a job category."""
        return json.dumps((await t.call("pricing", "marketplace.get_market_stats", category=category))["data"])

    @tool
    async def search_evidence(requirement: str) -> str:
        """Portfolio evidence for a requirement; returns evidence ids to cite."""
        r = await t.call("fit_matcher", "portfolio.search_evidence", requirement=requirement, k=4, portfolio=persona)
        return json.dumps([{"evidence_id": i["evidence_id"], "title": i["title"], "skills": i["skills"], "snippet": i["snippet"][:300]} for i in r["items"]])
    tools = {"get_job": get_job, "get_client_history": get_client_history, "get_market_stats": get_market_stats, "search_evidence": search_evidence}
    return [v for k, v in tools.items() if not allowed or k in allowed]


def parse_final(text: str) -> dict:
    m = re.search(r"\{[^{}]*\"action\"[\s\S]*\}", text or "")
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


async def run_baseline(kind: str, persona: str, job_id: str) -> dict:
    from langchain_core.callbacks import UsageMetadataCallbackHandler
    prof = persona_profile(persona)
    _, system, user = llm.render("baseline_react" if kind == "react" else "baseline_supervisor", freelancer_name=prof["name"],
                                 freelancer_title=prof["title"], freelancer_id=FREELANCER[persona], persona=persona,
                                 floor=str(prof["hourly_floor"]), job_id=job_id)
    cb = UsageMetadataCallbackHandler()
    t0 = time.time()
    if kind == "react":
        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(chat_model("writer"), lc_tools(persona), prompt=system)
    else:
        from langgraph.prebuilt import create_react_agent
        from langgraph_supervisor import create_supervisor
        m = chat_model("writer")
        researcher = create_react_agent(m, lc_tools(persona, {"get_job", "get_client_history", "get_market_stats"}), name="researcher",
                                        prompt="Read the job and its client; report requirements, budget, scam signals.")
        matcher = create_react_agent(m, lc_tools(persona, {"search_evidence"}), name="matcher",
                                     prompt="For each requirement, find portfolio evidence and report evidence ids.")
        writer = create_react_agent(m, [], name="writer", prompt="Write the cover letter citing [E:<evidence_id>] for every claim.")
        agent = create_supervisor([researcher, matcher, writer], model=m, prompt=system).compile()
    try:
        out = await agent.ainvoke({"messages": [{"role": "user", "content": user}]}, {"callbacks": [cb], "recursion_limit": 40})
        final = out["messages"][-1].content
        err = None
    except Exception as e:
        final, err = "", f"{type(e).__name__}: {e}"[:300]
    tokens = sum(v.get("total_tokens", 0) for v in cb.usage_metadata.values())
    return {"final": parse_final(final), "latency_s": time.time() - t0, "tokens": tokens, "error": err}


async def main_async(a):
    from rag.retriever import get_retriever
    from rag.verify import verify
    jobs = load_jobs()
    picked = []
    for p in PERSONAS:
        dev = load_dev(p)
        special = [g for g in dev if g["scam"] or g["injection"]][:4]
        rest = [g for g in dev if not (g["scam"] or g["injection"])][: a.n // 3 - len(special)]
        picked += [(p, g) for g in special + rest]
    picked = picked[: a.n]
    res = {}
    policy = settings.policy()
    async with httpx.AsyncClient(base_url=GIGSIM, headers={"Authorization": f"Bearer {ADMIN}"}, timeout=30) as c:
        for kind in a.kinds.split(","):
            rows = []
            for p, g in picked:
                r = await run_baseline(kind, p, g["job_id"])
                f = r["final"]
                letter = f.get("cover_letter") or ""
                row = {"persona": p, "job_id": g["job_id"], "gold_bid": g["bid"], "action": f.get("action"), **{k: r[k] for k in ("latency_s", "tokens", "error")}}
                if f.get("action") == "bid" and letter:
                    claims = verify(letter, get_retriever(p), use_llm=False)
                    row["unsupported"] = sum(cl.verdict == "unsupported" for cl in claims)
                    row["violations"] = len(scan(letter, policy))
                    s = (await c.post("/v1/admin/score", json={"freelancer_id": FREELANCER[p], "job_id": g["job_id"], "cover_letter": letter,
                                                               "bid_amount": float(f.get("price") or jobs[g["job_id"]]["budget"]["max"] or 100)})).json()
                    row["replied"] = s["replied"]
                rows.append(row)
                print(kind, g["job_id"], row.get("action"), row.get("unsupported"), row.get("error"))
            res[kind] = summarize(rows)
            res[kind]["rows"] = rows
    graph = graph_rows(picked)
    if graph:
        res["graph"] = summarize(graph)
    write("agents_compare", {"n_jobs": len(picked), "model": llm.node_spec("writer")[0], "results": res})
    for k, v in res.items():
        print(k, {x: y for x, y in v.items() if x != "rows"})


def graph_rows(picked):
    f = RESULTS / "pipeline_open_dev.json"
    if not f.exists():
        return []
    by = {r["job_id"]: r for r in json.loads(f.read_text())["rows"]}
    out = []
    for p, g in picked:
        r = by.get(g["job_id"])
        if r:
            out.append({"gold_bid": g["bid"], "action": r["action"], "latency_s": r["latency_s"], "tokens": r["tokens"],
                        "unsupported": 0 if r.get("cover_letter") else None, "violations": 0 if r.get("cover_letter") else None,
                        "unsupported_before_verification": r.get("unsupported_before"),
                        "replied": (r.get("gigsim") or {}).get("replied"), "error": r.get("error")})
    return out


def summarize(rows):
    acc = [(r["action"] == "bid") == r["gold_bid"] for r in rows if r.get("action")]
    props = [r for r in rows if r.get("unsupported") is not None]
    return {"n": len(rows), "errors": sum(bool(r.get("error")) for r in rows), "bid_skip_accuracy": mean(acc),
            "unsupported_claims_per_proposal": mean([r["unsupported"] for r in props]) if props else None,
            "compliance_violations_in_output": mean([r["violations"] for r in props]) if props else None,
            "gigsim_reply_rate": mean([r["replied"] for r in props if r.get("replied") is not None]) if props else None,
            "tokens_per_job": mean([r["tokens"] for r in rows]), "p95_latency_s": pct([r["latency_s"] for r in rows], 0.95)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--kinds", default="react,supervisor")
    asyncio.run(main_async(ap.parse_args()))
