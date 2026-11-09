"""Critic: grounding, personalisation and length. Sends the draft back (max twice, config budgets.max_revisions)."""
from __future__ import annotations

import json

from agent import llm
from agent.handoffs import Critique
from gigsim.world import GENERIC_OPENINGS


def heuristic_critique(draft: dict, spec: dict, job: dict) -> Critique:
    text = draft["cover_letter"]
    low = text.lower()
    claims = draft.get("claims", [])
    words = len(text.split())
    supported = [c for c in claims if c["verdict"] == "supported"]
    grounding = (len(supported) + 0.5 * sum(c["verdict"] == "partial" for c in claims)) / len(claims) if claims else 0.3
    issues = []
    if claims and any(c["verdict"] == "unsupported" for c in claims):
        issues.append("remove or rewrite unsupported claims")
    if not claims or "[E:" not in text:
        issues.append("cite at least one concrete past project as evidence")
    generic = any(g in low[:90] for g in GENERIC_OPENINGS)
    if generic:
        issues.append("replace the generic opening with the client's problem")
    pers = 0.4 + 0.3 * ((job.get("industry") or "~").lower() in low) + 0.3 * any(
        w in low for w in job["title"].lower().split() if len(w) > 4)
    if generic:
        pers -= 0.3
    length_ok = 60 <= words <= 230
    if words > 230:
        issues.append("too long: cut to under 200 words")
    if words < 60:
        issues.append("too short: add one more piece of concrete evidence")
    passed = grounding >= 0.6 and pers >= 0.6 and length_ok and not generic
    return Critique(passed=passed, grounding=round(min(1, grounding), 3), personalisation=round(max(0, min(1, pers)), 3),
                    length_ok=length_ok, issues=issues)


def critique(draft: dict, spec: dict, job: dict) -> Critique:
    base = heuristic_critique(draft, spec, job)
    c = llm.structured("critic", "critic", Critique, lambda: base, max_tokens=600, jobspec=json.dumps(spec),
                       draft=draft["cover_letter"], claims=json.dumps(draft.get("claims", [])[:12]))
    # hard checks the model cannot overrule
    if not base.length_ok or (base.grounding < 0.5 and draft.get("claims")):
        c.passed = False
        c.issues = list(dict.fromkeys(base.issues + c.issues))
    return c
