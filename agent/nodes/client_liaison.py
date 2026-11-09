"""Client Liaison: classify the client's latest message and draft a reply / interview slots."""
from __future__ import annotations

import json
import re

from agent import llm
from agent.handoffs import MessageIntent, ReplyDraft
from agent.nodes.risk_assessor import rule_signals


def heuristic_intent(msg: str) -> MessageIntent:
    low = msg.lower()
    sig = rule_signals(msg)
    inj = "prompt_injection" in sig
    if {"off_platform_contact", "off_platform_payment", "upfront_fee", "unpaid_work"} & set(sig):
        return MessageIntent(intent="scam_signal", confidence=0.9, injection_detected=inj, summary="off-platform / fee / free-work request")
    if re.search(r"\b(call|interview|available|meet|chat)\b", low):
        return MessageIntent(intent="interview_request", confidence=0.8, injection_detected=inj, summary="client wants a call")
    if re.search(r"\b(price|budget|cheaper|discount|lower|usd|\$)\b", low):
        return MessageIntent(intent="negotiation", confidence=0.75, injection_detected=inj, summary="client negotiates price")
    if "?" in msg:
        return MessageIntent(intent="question", confidence=0.7, injection_detected=inj, summary="client asks a question")
    return MessageIntent(intent="other", confidence=0.4, injection_detected=inj)


def classify(msg: str) -> MessageIntent:
    base = heuristic_intent(msg)
    out = llm.structured("client_liaison", "intent", MessageIntent, lambda: base, max_tokens=300,
                         message=llm.untrusted("client_message", msg))
    if base.intent == "scam_signal":
        out.intent = "scam_signal"  # rule floor
    out.injection_detected = out.injection_detected or base.injection_detected
    return out


def heuristic_reply(intent: MessageIntent, msg: str, slots: list[dict], floor: float, bid: float, job_title: str,
                    evidence_line: str) -> ReplyDraft:
    if intent.intent == "scam_signal":
        return ReplyDraft(body="Thanks for getting back to me. I keep all communication and payments on the platform, "
                               "and I don't take on unpaid test work or pay fees to start. Happy to continue here if that works for you.",
                          needs_attention=True, note="scam signal: off-platform / fee / unpaid request")
    if intent.intent == "interview_request":
        opts = "; ".join(f"{s['start'].replace('T', ' ')} ({s['timezone']})" for s in slots[:3])
        return ReplyDraft(body=f"Thanks! I'd be glad to talk about the {job_title.lower()}. I'm free at: {opts}. "
                               "Let me know which works and I'll keep it reserved.", proposed_slots=[s["start"] for s in slots[:3]])
    if intent.intent == "negotiation":
        m = re.search(r"(\d[\d,]*)\s*(usd|\$)?", msg.lower())
        offered = float(m.group(1).replace(",", "")) if m else None
        if offered and offered >= floor:
            body = (f"Thanks for the offer. {offered:.0f} USD works if we keep the scope to the first milestone we discussed; "
                    "anything beyond that we can price separately.")
        else:
            body = (f"I understand the budget is tight. The lowest I can go for the full scope is {max(floor, 0):.0f} USD; "
                    "alternatively I can deliver a smaller first milestone within your budget.")
        return ReplyDraft(body=body, note=f"floor {floor:.0f}, original bid {bid:.0f}")
    if intent.intent == "question":
        return ReplyDraft(body=f"Good question. {evidence_line} I'm happy to walk you through it on a short call if useful.")
    return ReplyDraft(body="Thanks for the message. Could you tell me a bit more about what you need next?")


def draft_reply(thread: dict, intent: MessageIntent, slots: list[dict], floor: float, bid: float, job_title: str,
                evidence_line: str, persona: dict, style_rules: list[str]) -> ReplyDraft:
    msgs = thread.get("messages", [])
    last = next((m["body"] for m in reversed(msgs) if m["from"] == "client"), "")
    base = heuristic_reply(intent, last, slots, floor, bid, job_title, evidence_line)
    convo = "\n".join(f"{m['from']}: " + (llm.untrusted("client_message", m["body"]) if m["from"] == "client" else m["body"])
                      for m in msgs[-8:])
    out = llm.structured("client_liaison", "client_liaison", ReplyDraft, lambda: base, max_tokens=600,
                         freelancer_name=persona.get("name", ""), floor=f"{floor:.0f} USD", job_title=job_title,
                         thread=convo, slots=json.dumps(slots), style_rules="; ".join(style_rules) or "none")
    if intent.intent == "scam_signal":
        out.needs_attention = True
    return out
