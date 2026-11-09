"""Bid graph (one thread per job).

intake -> [Send] analyst | risk_assessor | fit_matcher (parallel) -> decide
  decide: skip / watch -> END ; bid -> pricing -> writer -> verifier -> critic
  critic: fail and revision < max -> writer ; else -> compliance
  compliance -> approval (interrupt: approve / edit / reject) -> submit -> END
Budgets (steps, tokens) are enforced in every node; exceeding them -> status needs_attention.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from agent import settings
from agent.handoffs import BidDecision, JobSpec
from agent.memory import promotion_rules
from agent.memory.store import exemplars, outcome_stats, style_rules
from agent.nodes import analyst, client_liaison  # noqa: F401
from agent.nodes.base import RETRY, node, tools_from
from agent.nodes.compliance import enforce
from agent.nodes.critic import critique
from agent.nodes.fit_matcher import match
from agent.nodes.pricing import price as price_fn
from agent.nodes.risk_assessor import assess
from agent.nodes.writer import write
from agent.state import BidState
from rag.verify import apply as apply_verdicts
from rag.verify import verify_async

ROOT = Path(__file__).resolve().parents[2]


def persona_profile(persona: str) -> dict:
    return json.loads((ROOT / "data" / "personas" / persona / "profile.json").read_text())


def _search(tools, persona: str, agent: str):
    async def s(q: str, k: int) -> dict:
        return await tools.call(agent, "portfolio.search_evidence", requirement=q[:300], k=k, portfolio=persona)
    return s


def idem_key(state: dict, what: str) -> str:
    return hashlib.sha256(f"{state['user_id']}|{state['job_id']}|{what}".encode()).hexdigest()[:24]


# ------------------------------------------------------------------ nodes
@node("scout")
async def intake(state: BidState, config) -> dict:
    tools = tools_from(config)
    job = state.get("job")
    if not job:
        rec = await tools.call("scout", "marketplace.get_job", job_id=state["job_id"])
        job = rec["data"]
        if "error" in job and len(job) <= 2:
            return {"status": "dead_letter", "errors": [{"node": "scout", "error": str(job)}], "_log": "job not found"}
    return {"job": job, "status": "analysing", "revision": 0, "_log": f"loaded {job['job_id']}"}


def fan_out(state: BidState):
    if state.get("status") in ("dead_letter", "needs_attention"):
        return END
    return [Send("analyst", state), Send("risk_assessor", state), Send("fit_matcher", state)]


@node("analyst")
async def analyst_node(state: BidState, config) -> dict:
    spec = analyst.analyze(state["job"])
    return {"job_spec": spec.model_dump(), "_log": f"{len(spec.requirements)} requirements, needs={spec.hidden_needs}"}


@node("risk_assessor")
async def risk_node(state: BidState, config) -> dict:
    tools = tools_from(config)
    rec = await tools.call("risk_assessor", "marketplace.get_client_history", client_id=state["job"]["client_id"])
    client = rec.get("data", {})
    rep = assess(state["job"], client)
    return {"risk": rep.model_dump(), "client": client, "_log": f"risk={rep.risk_score} scam={rep.is_scam} flags={rep.flags}"}


@node("fit_matcher")
async def fit_node(state: BidState, config) -> dict:
    # runs in parallel with the analyst, so it extracts requirements with the cheap rule extractor;
    # `decide` tops up any requirement the analyst found that this branch missed.
    tools = tools_from(config)
    reqs = analyst.heuristic_spec(state["job"]).requirements
    rep, ev = await match(reqs, _search(tools, state["persona"], "fit_matcher"), state["job"])
    return {"fit": rep.model_dump(), "evidence": ev, "_log": f"fit={rep.fit_score} unsupported={rep.unsupported_requirements}"}


@node("decide")
async def decide(state: BidState, config) -> dict:
    tools = tools_from(config)
    spec, risk, fit = state["job_spec"], state["risk"], dict(state["fit"])
    missing = [r for r in spec["requirements"] if r not in {m["requirement"] for m in fit["matches"]}]
    ev = {}
    if missing:
        extra, ev = await match(missing, _search(tools, state["persona"], "fit_matcher"), state["job"])
        fit["matches"] = fit["matches"] + [m.model_dump() for m in extra.matches]
        from agent.handoffs import RequirementMatch
        from agent.nodes.fit_matcher import _score
        fit["fit_score"] = _score([RequirementMatch(**m) for m in fit["matches"]])
        fit["unsupported_requirements"] = [m["requirement"] for m in fit["matches"] if m["strength"] == "none"]
    th = settings.get("thresholds")
    prof = persona_profile(state["persona"])
    b = state["job"].get("budget", {})
    reasons, action = [], "bid"
    if risk["is_scam"]:
        action = "skip"
        reasons.append("scam signals: " + ", ".join(f for f in risk["flags"] if f in
                                                     ("unpaid_work", "off_platform_contact", "off_platform_payment", "upfront_fee")))
    elif risk["risk_score"] > th["maximum_risk_score"]:
        action = "skip"
        reasons.append(f"client risk {risk['risk_score']:.2f} above {th['maximum_risk_score']}")
    if fit["fit_score"] < th["minimum_fit_score"] - th["watch_band"]:
        action = "skip"
        reasons.append(f"fit {fit['fit_score']:.2f} below {th['minimum_fit_score']}")
    elif fit["fit_score"] < th["minimum_fit_score"] and action == "bid":
        action = "watch"
        reasons.append(f"fit {fit['fit_score']:.2f} just under threshold")
    est_floor = prof["hourly_floor"] * 10
    if b.get("max", 0) < est_floor and action == "bid":
        action = "skip"
        reasons.append(f"budget {b.get('max')} below your floor for this scope")
    stats = await outcome_stats(state["user_id"], state["job"].get("category"))
    if action == "bid" and stats.get("sent", 0) >= 8 and (stats.get("reply_rate") or 0) < 0.05:
        action = "watch"
        reasons.append(f"you got {stats.get('replied', 0)}/{stats['sent']} replies in this category")
    if action == "bid":
        reasons.append(f"fit {fit['fit_score']:.2f}, risk {risk['risk_score']:.2f}")
    if risk.get("injection_detected"):
        reasons.append("job post contains instructions aimed at AI tools; they were ignored")
    auto = action == "skip" and state.get("autonomy") == "auto_skip_low_fit"
    d = BidDecision(action=action, reasons=reasons, auto=auto)
    status = {"skip": "skipped", "watch": "watch", "bid": "drafting"}[action]
    return {"decision": d.model_dump(), "fit": fit, "evidence": ev, "status": status, "_log": f"{action}: {'; '.join(reasons)}"}


def route_decision(state: BidState) -> str:
    if state.get("status") == "needs_attention":
        return END
    return "pricing" if state["decision"]["action"] == "bid" else END


@node("pricing")
async def pricing_node(state: BidState, config) -> dict:
    tools = tools_from(config)
    job = state["job"]
    market = (await tools.call("pricing", "marketplace.get_market_stats", category=job.get("category") or "unknown")).get("data", {})
    prof = persona_profile(state["persona"])
    floor = (config.get("configurable", {}).get("hourly_floor") or prof["hourly_floor"])
    stats = await outcome_stats(state["user_id"], job.get("category"))
    q = price_fn(job, state["job_spec"], state.get("client") or {}, market if "error" not in market else {}, floor,
                 state["fit"]["fit_score"], settings.policy(), stats.get("reply_rate") or 0.25)
    return {"price": q.model_dump(), "_log": q.rationale}


@node("writer")
async def writer_node(state: BidState, config) -> dict:
    prof = persona_profile(state["persona"])
    rules = await style_rules(state["user_id"])
    ex = await exemplars(state["user_id"], state["job"].get("category"))
    fb = state["critiques"][-1]["issues"] if state.get("critiques") else []
    rev = state.get("revision", 0) + (1 if state.get("critiques") else 0)
    d = write(state["job"], state["job_spec"], state["fit"], state["price"], state.get("evidence", {}), prof, rules, ex, fb, rev)
    return {"draft": d.model_dump(), "revision": rev, "status": "drafting", "_log": f"draft r{rev}, {len(d.cover_letter.split())} words"}


@node("verifier")
async def verifier_node(state: BidState, config) -> dict:
    tools = tools_from(config)
    d = dict(state["draft"])
    search = _search(tools, state["persona"], "verifier")
    claims = await verify_async(d["cover_letter"], search, state.get("evidence", {}))
    before = sum(c.verdict == "unsupported" for c in claims)
    d["cover_letter"] = apply_verdicts(d["cover_letter"], claims)
    answers = []
    for a in d.get("screening_answers", []):
        ac = await verify_async(a, search, state.get("evidence", {}), use_llm=False)
        answers.append(apply_verdicts(a, ac))
    d["screening_answers"] = answers
    kept = [c for c in claims if c.verdict != "unsupported"]
    d["claims"] = [c.model_dump() for c in kept]
    d["removed_claims"] = [c.model_dump() for c in claims if c.verdict == "unsupported"]
    d["unsupported_before"] = before
    d["unsupported_after"] = 0
    return {"draft": d, "_log": f"{len(claims)} claims, {before} unsupported removed"}


@node("critic")
async def critic_node(state: BidState, config) -> dict:
    c = critique(state["draft"], state["job_spec"], state["job"])
    return {"critiques": [c.model_dump()], "_log": f"passed={c.passed} issues={c.issues}"}


def route_critic(state: BidState) -> str:
    if state.get("status") == "needs_attention":
        return END
    last = state["critiques"][-1]
    if not last["passed"] and state.get("revision", 0) < settings.get("budgets.max_revisions", 2):
        return "writer"
    return "compliance"


@node("compliance")
async def compliance_node(state: BidState, config) -> dict:
    d = state["draft"]
    v = enforce(d["cover_letter"], d.get("screening_answers", []), d.get("claims"), state.get("risk"))
    return {"compliance": v.model_dump(), "status": "awaiting_approval" if v.allowed else "needs_attention",
            "attention_reason": v.blocked_reason, "_log": f"allowed={v.allowed} violations={[x['rule'] for x in v.violations]}"}


@node("approval")
async def approval_node(state: BidState, config) -> dict:
    tools = tools_from(config)
    d, comp, price = state["draft"], state["compliance"], state["price"]
    text = comp["cleaned_text"] or d["cover_letter"]
    answers = comp.get("cleaned_answers") or d.get("screening_answers", [])
    preview = await tools.call("ui", "marketplace.create_proposal_draft", freelancer_id=state["freelancer_id"],
                               job_id=state["job_id"], cover_letter=text if len(text) >= 50 else text.ljust(50),
                               bid_amount=price["amount"], idempotency_key=idem_key(state, "draft"),
                               screening_answers=answers, dry_run=True)
    balance = (await tools.call("ui", "marketplace.get_connects_balance", freelancer_id=state["freelancer_id"])).get("data", {})
    payload = {
        "kind": "proposal", "job_id": state["job_id"], "title": state["job"]["title"],
        "cover_letter": text, "screening_answers": answers,
        "claims": d.get("claims", []), "removed_claims": d.get("removed_claims", []),
        "evidence": {k: v[:600] for k, v in state.get("evidence", {}).items()},
        "risk": state["risk"], "price": price, "fit": state["fit"], "decision": state["decision"],
        "compliance": {"allowed": comp["allowed"], "blocked_reason": comp["blocked_reason"], "violations": comp["violations"]},
        "dry_run": {**preview, "connects_cost": price["connects_cost"], "connects_balance": balance.get("balance")},
        "critiques": state.get("critiques", []),
    }
    human = interrupt(payload)  # <- the graph pauses here until the UI resumes it
    action = human.get("action")
    if action == "reject":
        return {"approval": {"action": "reject", "reason": human.get("reason", "")}, "status": "rejected",
                "_log": f"rejected: {human.get('reason', '')}"}
    if action == "edit":
        new_text = human.get("cover_letter", text)
        mem = await promotion_rules.record_edit(state["user_id"], state["job_id"], text, new_text)
        v = enforce(new_text, human.get("screening_answers", answers), None, state.get("risk"))
        new_price = dict(price, amount=float(human.get("bid_amount", price["amount"])))
        if not v.allowed:
            return {"approval": {"action": "edit_blocked", "memory": mem}, "compliance": v.model_dump(),
                    "draft": dict(d, cover_letter=new_text), "price": new_price, "status": "needs_attention",
                    "attention_reason": v.blocked_reason, "_log": "edit blocked by compliance"}
        return {"approval": {"action": "approve", "edited": True, "memory": mem, "cover_letter": v.cleaned_text,
                             "screening_answers": v.cleaned_answers, "bid_amount": new_price["amount"]},
                "price": new_price, "status": "approved", "_log": f"approved with edits; promoted={mem['promoted']}"}
    if not comp["allowed"]:
        return {"approval": {"action": "edit_blocked"}, "status": "needs_attention",
                "attention_reason": "Compliance blocked this draft: " + str(comp["blocked_reason"]) + ". Edit it or reject.",
                "_log": "approve refused: compliance block"}
    return {"approval": {"action": "approve", "edited": False, "cover_letter": text, "screening_answers": answers,
                         "bid_amount": price["amount"]}, "status": "approved", "_log": "approved"}


def route_approval(state: BidState) -> str:
    s = state.get("status")
    if s == "approved":
        return "submit"
    if s == "needs_attention" and (state.get("approval") or {}).get("action") == "edit_blocked":
        return "approval"  # show the blocked edit again; the user fixes it or rejects
    return END


@node("submit")
async def submit_node(state: BidState, config) -> dict:
    """Not an LLM agent: executes exactly what the human approved, with idempotency keys derived from
    the thread, so a crash + resume can never submit twice or spend Connects twice."""
    from mcp_servers.marketplace.server import approval_token
    tools = tools_from(config)
    a = state["approval"]
    text, amount = a["cover_letter"], float(a["bid_amount"])
    draft = await tools.call("executor", "marketplace.create_proposal_draft", freelancer_id=state["freelancer_id"],
                             job_id=state["job_id"], cover_letter=text, bid_amount=amount,
                             idempotency_key=idem_key(state, "draft"), screening_answers=a.get("screening_answers", []),
                             approval_id=approval_token("proposal", state["job_id"], text + str(amount)))
    if draft.get("status") in ("error", "rejected"):
        return {"status": "needs_attention", "attention_reason": f"draft failed: {draft.get('error')}",
                "errors": [{"node": "submit", "error": draft.get("error")}]}
    pid = draft["result"]["proposal_id"]
    sub = await tools.call("executor", "marketplace.submit_proposal", proposal_id=pid, freelancer_id=state["freelancer_id"],
                           idempotency_key=idem_key(state, "submit"),
                           approval_id=approval_token("submit", pid, text + str(amount)))
    if sub.get("status") in ("error", "rejected"):
        return {"status": "needs_attention", "attention_reason": f"submit failed: {sub.get('error')}",
                "errors": [{"node": "submit", "error": sub.get("error")}]}
    await promotion_rules.record_outcome(state["user_id"], state["job"].get("category") or "unknown", text, "submitted")
    return {"submission": {"proposal_id": pid, **sub}, "status": "submitted",
            "_log": f"submitted {pid}; replay={sub.get('idempotent_replay')}; connects={sub.get('connects_cost')}"}


def build(checkpointer=None, store=None):
    g = StateGraph(BidState)
    g.add_node("intake", intake, retry_policy=RETRY)
    g.add_node("analyst", analyst_node, retry_policy=RETRY)
    g.add_node("risk_assessor", risk_node, retry_policy=RETRY)
    g.add_node("fit_matcher", fit_node, retry_policy=RETRY)
    g.add_node("decide", decide, retry_policy=RETRY)
    g.add_node("pricing", pricing_node, retry_policy=RETRY)
    g.add_node("writer", writer_node, retry_policy=RETRY)
    g.add_node("verifier", verifier_node, retry_policy=RETRY)
    g.add_node("critic", critic_node, retry_policy=RETRY)
    g.add_node("compliance", compliance_node)
    g.add_node("approval", approval_node)
    g.add_node("submit", submit_node, retry_policy=RETRY)
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk_assessor", "fit_matcher", END])
    g.add_edge("analyst", "decide")
    g.add_edge("risk_assessor", "decide")
    g.add_edge("fit_matcher", "decide")
    g.add_conditional_edges("decide", route_decision, ["pricing", END])
    g.add_edge("pricing", "writer")
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", route_critic, ["writer", "compliance", END])
    g.add_conditional_edges("compliance", lambda s: END if s.get("attention_reason", "") and "budget" in (s.get("attention_reason") or "") else "approval",
                            ["approval", END])
    g.add_conditional_edges("approval", route_approval, ["submit", "approval", END])
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer, store=store)
