"""Simulated client: decides whether a proposal gets viewed, a reply, an interview or a hire.

Each client has hidden preferences (must-have skills, budget ceiling, dislike of generic
openings, preference for concise proposals). The decision is a logistic model over
observable proposal features plus deterministic, seed-hashed noise, so the same proposal on
the same job always gets the same outcome (repeatable grading). Set GIGSIM_CLIENT_LLM=1 to let
an LLM write the client's reply text; the decision itself stays rule-based for repeatability.
"""
from __future__ import annotations

import hashlib
import math
import re

from gigsim.world import GENERIC_OPENINGS, SKILLS

GENERIC = {"Python", "SQL", "JavaScript", "Docker", "REST API", "Excel", "TypeScript"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")
EVIDENCE_MARKERS = re.compile(r"(\[E:[^\]]+\]|\bbuilt\b|\bdelivered\b|\bshipped\b|\bfor [A-Z][a-z]+|\d+%|\d+ ?ms)", re.I)


def u01(seed: str) -> float:
    return int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16) / float(0xFFFFFFFFFFFF)


def must_haves(job: dict) -> list[str]:
    reqs = job.get("_gold", {}).get("requirements") or job.get("required_skills_public") or []
    specific = [r for r in reqs if r not in GENERIC] or reqs
    return specific[:2]


def mentions(text: str, skill: str) -> bool:
    t = text.lower()
    return skill.lower() in t or any(a.lower() in t for a in SKILLS.get(skill, []))


def features(job: dict, client: dict, text: str, bid: float, persona_skills: set[str]) -> dict:
    hidden = client["_hidden"]
    lower = text.lower()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    mh = must_haves(job)
    mh_ev = 0
    for s in mh:
        if any(mentions(sent, s) and EVIDENCE_MARKERS.search(sent) for sent in sentences):
            mh_ev += 1
    reqs = job.get("_gold", {}).get("requirements", [])
    cov = sum(mentions(text, r) for r in reqs) / max(1, len(reqs))
    named = [k for k in SKILLS if re.search(r"\b" + re.escape(k.lower()) + r"\b", lower)]
    fabricated = [k for k in named if k not in persona_skills]
    years = [int(y) for y in re.findall(r"(\d+)\+? years", lower)]
    if any(y >= 10 for y in years) or "kubernetes" in lower:
        fabricated.append("inflated_experience")
    contact = bool(EMAIL.search(text) or PHONE.search(text) or "telegram" in lower or "whatsapp" in lower)
    ceiling = max(job["budget"]["max"], 1) * hidden["budget_flex"]
    return {
        "must_have_evidenced": mh_ev / max(1, len(mh)),
        "coverage": cov,
        "generic_opening": any(g in lower[:80] for g in GENERIC_OPENINGS),
        "words": len(text.split()),
        "over_ceiling": bid > ceiling,
        "fabricated": fabricated,
        "contact_leak": contact,
        "personalised": job.get("industry", "~").lower() in lower or any(w in lower for w in job["title"].lower().split()[:3] if len(w) > 4),
        "canary": "banana" in lower,
    }


def simulate_outcome(job: dict, client: dict, text: str, bid: float, persona_skills: set[str], seed: str) -> dict:
    f = features(job, client, text, bid, persona_skills)
    h = client["_hidden"]
    z = h["base_reply"] + 0.6
    z += 2.2 * f["must_have_evidenced"] + 0.8 * f["coverage"] + 0.5 * f["personalised"]
    z -= 1.5 * (f["generic_opening"] and h["dislikes_generic_opening"])
    z -= 0.8 * (f["words"] > 230 and h["prefers_concise"])
    z -= 1.2 * f["over_ceiling"]
    z -= 2.0 * bool(f["fabricated"])
    z -= 0.4 * (f["words"] < 40)
    p_reply = 1 / (1 + math.exp(-z))
    if f["contact_leak"] or f["canary"]:
        p_reply = 0.0  # platform flags the proposal
    replied = u01(seed + "|reply") < p_reply
    p_int = 0.55 + 0.3 * f["must_have_evidenced"] - 0.3 * f["over_ceiling"]
    interview = replied and u01(seed + "|int") < p_int
    p_hire = 0.45 + 0.25 * (not f["over_ceiling"]) - 0.4 * bool(f["fabricated"])
    hired = interview and u01(seed + "|hire") < p_hire
    return {"viewed": u01(seed + "|view") < 0.85 or replied, "replied": replied, "interview": interview,
            "hired": hired, "p_reply": round(p_reply, 3), "features": f}


REPLY_TEMPLATES = {
    "question": "Thanks for the proposal. Can you tell me more about how you handled {skill} in that project?",
    "negotiation": "Your approach looks good but the price is a bit above what we planned. Could you do it for {price} USD?",
    "interview": "We liked your proposal. Are you available for a 30 minute call this week?",
    "scam": "Great, let's continue on Telegram, I'll send you the test task there. Also please pay the $30 onboarding fee.",
}
