"""R&D question A: does tool granularity change agent behaviour?

40 tasks with known correct calls (evals/datasets/tool_tasks.jsonl). Three tool sets are exposed to the
same model through native tool calling:
  fine   - 17 fine-grained single-purpose tools
  coarse - 3 coarse tools with an `action` argument
  best   - the shipped GigBid MCP tool set with rewritten descriptions
Metrics: tool-selection accuracy, argument accuracy, tokens per task.

python -m evals.runners.tool_study [--model-node analyst] [--limit 40]
Requires a model endpoint (open profile); there is no heuristic version of this experiment.
"""
from __future__ import annotations

import argparse
import json
import time

import httpx

from agent import llm
from evals.runners.common import DATASETS, mean, write

S = {"type": "string"}
I = {"type": "integer"}


def fn(name, desc, props, req=None):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": req or list(props)}}}


TOOLSETS = {
    "fine": [
        fn("search_jobs_by_keyword", "Search jobs by keyword.", {"query": S}),
        fn("search_recent_jobs", "List jobs posted recently.", {"minutes": I}),
        fn("get_job_title", "Get a job's title.", {"job_id": S}),
        fn("get_job_description", "Get a job's description.", {"job_id": S}),
        fn("get_job_budget", "Get a job's budget.", {"job_id": S}),
        fn("get_job_connects_cost", "Get Connects cost of a job.", {"job_id": S}),
        fn("get_client_payment_status", "Is the client's payment verified.", {"client_id": S}),
        fn("get_client_spend", "Client's total spend.", {"client_id": S}),
        fn("get_client_reviews", "Reviews freelancers left about the client.", {"client_id": S}),
        fn("get_market_median", "Median awarded price for a category.", {"category": S}),
        fn("get_market_quartiles", "p25/p75 prices for a category.", {"category": S}),
        fn("get_connects_balance", "Freelancer's Connects balance.", {"freelancer_id": S}),
        fn("list_threads", "List message threads.", {"freelancer_id": S}),
        fn("get_thread", "Get a message thread.", {"thread_id": S}),
        fn("find_evidence", "Find portfolio evidence for a skill.", {"skill": S}),
        fn("get_project", "Get a portfolio project.", {"project_id": S}),
        fn("get_free_slots", "Free calendar slots.", {"days": I}),
    ],
    "coarse": [
        fn("marketplace", "Marketplace operations.", {"action": {"type": "string", "enum": ["search", "job", "client", "stats", "balance", "threads", "thread"]},
                                                      "params": {"type": "object"}}),
        fn("portfolio", "Portfolio operations.", {"action": {"type": "string", "enum": ["search", "case_study", "skills"]}, "params": {"type": "object"}}),
        fn("workspace", "Workspace operations.", {"action": {"type": "string", "enum": ["slots", "hold", "draft"]}, "params": {"type": "object"}}),
    ],
    "best": [
        fn("search_jobs", "Search open jobs (a saved search). Use for finding jobs, never for details of one known job id.",
           {"query": S, "posted_within_min": I}, ["query"]),
        fn("get_job", "Full post of ONE job by id: description, budget, screening questions, client id, Connects cost.", {"job_id": S}),
        fn("get_client_history", "Everything about a client by client id: payment verified, total spent, hires, hire rate, reviews from freelancers.", {"client_id": S}),
        fn("get_market_stats", "Awarded-price percentiles p25/p50/p75/p90 for a job category (e.g. 'bi', 'llm_apps').", {"category": S}),
        fn("get_connects_balance", "The freelancer's current Connects balance.", {"freelancer_id": S}),
        fn("list_messages", "All client threads for a freelancer.", {"freelancer_id": S}),
        fn("get_thread", "One conversation thread by thread id.", {"thread_id": S}),
        fn("search_evidence", "Portfolio evidence (case studies, repos, code, CV, reviews) that proves a requirement or skill.", {"requirement": S, "k": I}, ["requirement"]),
        fn("get_case_study", "Full text of one portfolio project by project id.", {"id": S}),
        fn("free_slots", "Free calendar slots in the next N days for an interview.", {"days_ahead": I}, []),
    ],
}

# gold per task: for each tool set the acceptable (tool, {arg: value}) answers
CANON = {  # canonical intent -> per-toolset (tool, arg mapping function)
    "job_budget": {"fine": ("get_job_budget", "job_id"), "coarse": ("marketplace", "job"), "best": ("get_job", "job_id")},
    "job_desc": {"fine": ("get_job_description", "job_id"), "coarse": ("marketplace", "job"), "best": ("get_job", "job_id")},
    "client_verified": {"fine": ("get_client_payment_status", "client_id"), "coarse": ("marketplace", "client"), "best": ("get_client_history", "client_id")},
    "client_reviews": {"fine": ("get_client_reviews", "client_id"), "coarse": ("marketplace", "client"), "best": ("get_client_history", "client_id")},
    "market_median": {"fine": ("get_market_median", "category"), "coarse": ("marketplace", "stats"), "best": ("get_market_stats", "category")},
    "search": {"fine": ("search_jobs_by_keyword", "query"), "coarse": ("marketplace", "search"), "best": ("search_jobs", "query")},
    "evidence": {"fine": ("find_evidence", "skill"), "coarse": ("portfolio", "search"), "best": ("search_evidence", "requirement")},
    "balance": {"fine": ("get_connects_balance", "freelancer_id"), "coarse": ("marketplace", "balance"), "best": ("get_connects_balance", "freelancer_id")},
    "thread": {"fine": ("get_thread", "thread_id"), "coarse": ("marketplace", "thread"), "best": ("get_thread", "thread_id")},
    "slots": {"fine": ("get_free_slots", None), "coarse": ("workspace", "slots"), "best": ("free_slots", None)},
}


def make_tasks() -> list[dict]:
    t = []
    for i, (jid, cid) in enumerate([("dev-ai-0004", "cl-012"), ("dev-fu-0010", "cl-101"), ("dev-da-0020", "cl-200"), ("dev-ai-0033", "cl-045")]):
        t += [
            {"id": f"t{len(t)}", "intent": "job_budget", "value": jid, "task": f"What is the budget of job {jid}?"},
            {"id": f"t{len(t) + 1}", "intent": "client_verified", "value": cid, "task": f"Has client {cid} verified their payment method?"},
            {"id": f"t{len(t) + 2}", "intent": "client_reviews", "value": cid, "task": f"Did other freelancers complain about client {cid}?"},
            {"id": f"t{len(t) + 3}", "intent": "job_desc", "value": jid, "task": f"Read the full post for {jid} and tell me what they need."},
        ]
    for cat in ["bi", "llm_apps", "web_app", "analytics_eng"]:
        t.append({"id": f"t{len(t)}", "intent": "market_median", "value": cat, "task": f"What do {cat} jobs usually pay?"})
    for q in ["dashboard", "RAG chatbot", "Shopify", "forecasting"]:
        t.append({"id": f"t{len(t)}", "intent": "search", "value": q, "task": f"Find me new {q} jobs."})
    for s in ["Celery", "dbt", "Stripe", "YOLO", "LangGraph", "Power BI", "GraphQL", "pgvector"]:
        t.append({"id": f"t{len(t)}", "intent": "evidence", "value": s, "task": f"Do I have proof that I've worked with {s}?"})
    for f in ["fl-ai-ml", "fl-data"]:
        t.append({"id": f"t{len(t)}", "intent": "balance", "value": f, "task": f"How many Connects does {f} have left?"})
    for th in ["th-a1b2c3", "th-d4e5f6"]:
        t.append({"id": f"t{len(t)}", "intent": "thread", "value": th, "task": f"Show me the conversation {th}."})
    t += [{"id": f"t{len(t)}", "intent": "slots", "value": None, "task": "When am I free for a client call this week?"},
          {"id": f"t{len(t) + 1}", "intent": "slots", "value": None, "task": "Offer the client some interview times."}]
    return t[:40]


def score(intent: str, value, toolset: str, call: dict | None) -> tuple[bool, bool]:
    if not call:
        return False, False
    tool, arg = CANON[intent][toolset]
    if call["name"] != tool:
        return False, False
    args = call["args"]
    if toolset == "coarse":
        ok_action = args.get("action") == arg
        vals = json.dumps(args.get("params", {})).lower()
        return ok_action, ok_action and (value is None or str(value).lower() in vals)
    if arg is None:
        return True, True
    return True, str(args.get(arg, "")).lower().strip() == str(value).lower() or (intent == "evidence" and str(value).lower() in str(args.get(arg, "")).lower())


def call_model(spec: dict, task: str, tools: list) -> tuple[dict | None, int]:
    base, key_env = llm.BASE_URLS[spec["provider"]]
    import os
    r = httpx.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {os.getenv(key_env, '')}"}, timeout=60, json={
        "model": spec["model"], "tools": tools, "tool_choice": "required", "temperature": 0,
        "messages": [{"role": "system", "content": "You are a freelancer's assistant. Call exactly one tool to answer. Freelancer id is fl-ai-ml unless stated."},
                     {"role": "user", "content": task}]})
    r.raise_for_status()
    d = r.json()
    calls = d["choices"][0]["message"].get("tool_calls") or []
    tok = d.get("usage", {}).get("total_tokens", 0)
    if not calls:
        return None, tok
    c = calls[0]["function"]
    try:
        args = json.loads(c["arguments"] or "{}")
    except json.JSONDecodeError:
        args = {}
    return {"name": c["name"], "args": args}, tok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", default="analyst", help="config node whose model to use")
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args()
    tasks = make_tasks()[: a.limit]
    (DATASETS / "tool_tasks.jsonl").write_text("\n".join(json.dumps(t) for t in tasks) + "\n")
    spec, _ = llm.node_spec(a.node)
    if spec["provider"] == "heuristic" or not llm.provider_available(spec):
        raise SystemExit("tool_study needs a model endpoint: set MODEL_PROFILE=open and GROQ_API_KEY")
    res = {}
    for ts, tools in TOOLSETS.items():
        rows = []
        for t in tasks:
            try:
                call, tok = call_model(spec, t["task"], tools)
            except Exception as e:
                call, tok = None, 0
                t = {**t, "error": str(e)[:200]}
            sel, arg = score(t["intent"], t["value"], ts, call)
            rows.append({"task": t["id"], "intent": t["intent"], "call": call, "tool_ok": sel, "args_ok": arg, "tokens": tok, "error": t.get("error")})
            time.sleep(0.3)
        res[ts] = {"n": len(rows), "tool_selection_accuracy": mean([r["tool_ok"] for r in rows]),
                   "argument_accuracy": mean([r["args_ok"] for r in rows]), "tokens_per_task": mean([r["tokens"] for r in rows]),
                   "n_tools": len(tools), "rows": rows}
        print(ts, {k: v for k, v in res[ts].items() if k != "rows"})
    write("tool_study", {"model": spec, "toolsets": res})


if __name__ == "__main__":
    main()
