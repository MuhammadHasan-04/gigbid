"""Compliance Guard: enforce the active policy pack (agent/config.yaml policy.version). Rules are data."""
from __future__ import annotations

import re

from agent import settings
from agent.handoffs import ComplianceVerdict
from rag.verify import split_sentences


def scan(text: str, policy: dict, claims: list[dict] | None = None) -> list[dict]:
    out = []
    from agent.llm import defence_disabled
    for rule in policy["rules"]:
        if defence_disabled() and rule["id"] == "no_injected_instructions":
            continue
        if rule["detector"] == "regex":
            for s in split_sentences(text):
                if any(re.search(p, s) for p in rule["patterns"]):
                    out.append({"rule": rule["id"], "severity": rule["severity"], "sentence": s, "fix": rule["fix"]})
        elif rule["detector"] == "claim_verifier" and claims:
            for c in claims:
                if c.get("verdict") == "unsupported" and c["text"] in text:
                    out.append({"rule": rule["id"], "severity": rule["severity"], "sentence": c["text"], "fix": rule["fix"]})
    return out


def enforce(text: str, answers: list[str], claims: list[dict] | None, risk: dict | None = None,
            policy: dict | None = None) -> ComplianceVerdict:
    policy = policy or settings.policy()
    violations = scan(text, policy, claims)
    bad = {v["sentence"] for v in violations}
    cleaned = " ".join(s for s in split_sentences(text) if s not in bad)
    cleaned_answers = []
    for a in answers:
        av = scan(a, policy)
        violations += [{**v, "in": "screening_answer"} for v in av]
        cleaned_answers.append(" ".join(s for s in split_sentences(a) if s not in {v["sentence"] for v in av}))
    remaining = scan(cleaned, policy, claims)
    blocked = None
    if risk and risk.get("is_scam"):
        blocked = "job flagged as a scam by the Risk Assessor"
    elif remaining:
        blocked = "violations remain after automatic fixes: " + ", ".join(sorted({v["rule"] for v in remaining}))
    elif len(cleaned.split()) < 40:
        blocked = "too little text left after removing violations; rewrite needed"
    return ComplianceVerdict(allowed=blocked is None, blocked_reason=blocked, violations=violations, cleaned_text=cleaned,
                             cleaned_answers=cleaned_answers, policy_version=int(policy.get("version", 1)))
