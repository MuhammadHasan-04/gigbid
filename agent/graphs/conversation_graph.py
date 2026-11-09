"""Conversation graph (one thread per client conversation).

load_thread -> classify (intent + injection check) -> [interview_request] slots -> draft_reply
-> compliance -> approval (interrupt) -> send (+ tentative calendar hold) -> END
"""
from __future__ import annotations

import hashlib

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.graphs.bid_graph import persona_profile
from agent.memory import promotion_rules
from agent.memory.store import style_rules
from agent.nodes.base import RETRY, node, tools_from
from agent.nodes.client_liaison import classify, draft_reply
from agent.nodes.compliance import enforce
from agent.state import ConvState


def _key(state: dict, what: str) -> str:
    n = len(state["thread"].get("messages", []))
    return hashlib.sha256(f"{state['user_id']}|{state['thread_id']}|{n}|{what}".encode()).hexdigest()[:24]


@node("client_liaison")
async def load_thread(state: ConvState, config) -> dict:
    tools = tools_from(config)
    t = (await tools.call("client_liaison", "marketplace.get_thread", thread_id=state["thread_id"]))["data"]
    return {"thread": t, "status": "analysing", "_log": f"{len(t.get('messages', []))} messages"}


@node("client_liaison")
async def classify_node(state: ConvState, config) -> dict:
    last = next((m["body"] for m in reversed(state["thread"]["messages"]) if m["from"] == "client"), "")
    it = classify(last)
    return {"intent": it.model_dump(), "_log": f"intent={it.intent} injection={it.injection_detected}"}


@node("client_liaison")
async def slots_node(state: ConvState, config) -> dict:
    tools = tools_from(config)
    slots = await tools.call("client_liaison", "workspace.free_slots", days_ahead=5, max_slots=3)
    return {"slots": slots if isinstance(slots, list) else [], "_log": f"{len(slots)} free slots"}


@node("client_liaison")
async def draft_node(state: ConvState, config) -> dict:
    prof = persona_profile(state["persona"])
    rules = await style_rules(state["user_id"])
    job = state.get("job") or {}
    floor = state.get("floor") or prof["hourly_floor"] * 10
    bid = float(job.get("bid_amount") or floor)
    ev_line = "In my past projects I documented each step and shared demos weekly, and I'd do the same here."
    r = draft_reply(state["thread"], _intent(state), state.get("slots", []), floor, bid, job.get("title", "this project"),
                    ev_line, prof, rules)
    return {"reply": r.model_dump(), "_log": r.body[:120]}


def _intent(state):
    from agent.handoffs import MessageIntent
    return MessageIntent(**state["intent"])


@node("compliance")
async def comp_node(state: ConvState, config) -> dict:
    v = enforce(state["reply"]["body"], [], None, None)
    # short replies are fine in conversations: only rule violations block
    blocked = v.blocked_reason if v.blocked_reason and "too little text" not in v.blocked_reason else None
    return {"compliance": {**v.model_dump(), "allowed": blocked is None, "blocked_reason": blocked},
            "_log": f"violations={[x['rule'] for x in v.violations]}"}


@node("approval")
async def approval_node(state: ConvState, config) -> dict:
    tools = tools_from(config)
    body = state["compliance"]["cleaned_text"] or state["reply"]["body"]
    preview = await tools.call("ui", "marketplace.send_message", thread_id=state["thread_id"], body=body,
                               idempotency_key=_key(state, "msg"), dry_run=True)
    human = interrupt({"kind": "message", "thread_id": state["thread_id"], "intent": state["intent"], "body": body,
                       "proposed_slots": state["reply"].get("proposed_slots", []), "slots": state.get("slots", []),
                       "needs_attention": state["reply"].get("needs_attention"), "note": state["reply"].get("note"),
                       "compliance": state["compliance"], "thread": state["thread"], "dry_run": preview})
    if human.get("action") == "reject":
        return {"approval": {"action": "reject", "reason": human.get("reason", "")}, "status": "rejected"}
    text = human.get("body", body) if human.get("action") == "edit" else body
    mem = None
    if human.get("action") == "edit":
        mem = await promotion_rules.record_edit(state["user_id"], state["thread_id"], body, text)
        v = enforce(text, [], None, None)
        if v.violations:
            return {"approval": {"action": "edit_blocked", "memory": mem}, "status": "needs_attention",
                    "attention_reason": "edited reply violates policy: " + ", ".join(x["rule"] for x in v.violations),
                    "compliance": {**v.model_dump(), "allowed": False}, "reply": {**state["reply"], "body": text}}
    if not state["compliance"].get("allowed", True) and human.get("action") != "edit":
        return {"approval": {"action": "edit_blocked"}, "status": "needs_attention",
                "attention_reason": state["compliance"].get("blocked_reason")}
    return {"approval": {"action": "approve", "body": text, "slot": human.get("slot"), "memory": mem}, "status": "approved"}


@node("client_liaison")
async def send_node(state: ConvState, config) -> dict:
    from mcp_servers.marketplace.server import approval_token
    tools = tools_from(config)
    body = state["approval"]["body"]
    sent = await tools.call("executor", "marketplace.send_message", thread_id=state["thread_id"], body=body,
                            idempotency_key=_key(state, "msg"), approval_id=approval_token("message", state["thread_id"], body))
    hold = None
    slots = state.get("reply", {}).get("proposed_slots") or []
    if slots and _intent(state).intent == "interview_request":
        s = state["approval"].get("slot") or slots[0]
        end = next((x["end"] for x in state.get("slots", []) if x["start"] == s), s)
        hold = await tools.call("executor", "workspace.create_tentative_hold", start=s, end=end,
                                title=f"Interview: {state.get('job', {}).get('title', state['thread_id'])}",
                                idempotency_key=_key(state, "hold"))
    if sent.get("status") in ("error", "rejected"):
        return {"status": "needs_attention", "attention_reason": sent.get("error"), "errors": [{"node": "send", "error": sent.get("error")}]}
    return {"sent": {**sent, "hold": hold}, "status": "sent", "_log": f"sent; hold={bool(hold)}"}


def build(checkpointer=None, store=None):
    g = StateGraph(ConvState)
    g.add_node("load_thread", load_thread, retry_policy=RETRY)
    g.add_node("classify", classify_node, retry_policy=RETRY)
    g.add_node("slots", slots_node, retry_policy=RETRY)
    g.add_node("draft", draft_node, retry_policy=RETRY)
    g.add_node("compliance", comp_node)
    g.add_node("approval", approval_node)
    g.add_node("send", send_node, retry_policy=RETRY)
    g.add_edge(START, "load_thread")
    g.add_edge("load_thread", "classify")
    g.add_conditional_edges("classify", lambda s: "slots" if s["intent"]["intent"] == "interview_request" else "draft",
                            ["slots", "draft"])
    g.add_edge("slots", "draft")
    g.add_edge("draft", "compliance")
    g.add_edge("compliance", "approval")
    g.add_conditional_edges("approval", lambda s: "send" if s.get("status") == "approved" else
                            ("approval" if (s.get("approval") or {}).get("action") == "edit_blocked" else END),
                            ["send", "approval", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer, store=store)
