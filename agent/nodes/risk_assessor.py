"""Risk Assessor: client quality from history, scams, free-work and off-platform asks, injected instructions."""
from __future__ import annotations

import json
import re

from agent import llm
from agent.handoffs import RiskReport

SIGNALS = {
    "unpaid_work": [r"\bfor free\b", r"\bunpaid\b", r"\btest task\b.*\bfree\b", r"pay only if we like", r"free (trial|sample|test)"],
    "off_platform_contact": [r"\btelegram\b", r"\bwhatsapp\b", r"\bskype\b", r"[\w.+-]+@[\w-]+\.\w+", r"outside here",
                             r"\+\d[\d\s-]{7,}\d|\b\d{3}[\s.-]\d{3,4}[\s.-]\d{3,4}\b", r"contact me on"],
    "off_platform_payment": [r"\busdt\b", r"\bcrypto", r"\bwallet\b", r"gift cards?", r"western union", r"avoid fees", r"no platform fees"],
    "upfront_fee": [r"\$\d+ .*(kit|deposit|fee)", r"onboarding kit", r"refundable .* deposit", r"buy our"],
}
INJECTION = [r"ignore (all )?(previous|prior) instructions", r"\bnote (for|to) ai\b", r"\bai assistants?\b",
             r"\[system\]", r"if you are an ai", r"new instruction", r"</?\s*job_post", r"state this clearly",
             r"banana protocol", r"admin:"]


def rule_signals(text: str) -> dict[str, list[str]]:
    low = text.lower()
    found = {k: [p for p in pats if re.search(p, low)] for k, pats in SIGNALS.items()}
    found = {k: v for k, v in found.items() if v}
    from agent.llm import defence_disabled
    inj = [] if defence_disabled() else [p for p in INJECTION if re.search(p, low)]
    if inj:
        found["prompt_injection"] = inj
    return found


def heuristic_report(job: dict, client: dict, sig: dict) -> RiskReport:
    flags = list(sig)
    reasons = [f"{k}: matched {', '.join(v[:2])}" for k, v in sig.items()]
    quality = 0.5
    if client:
        quality = 0.2 + 0.3 * bool(client.get("payment_verified")) + 0.2 * min(1, (client.get("total_spent") or 0) / 5000) \
            + 0.2 * min(1, client.get("hire_rate", 0) / 0.6) + 0.1 * (client.get("avg_rating_given", 4) >= 4.2)
        if not client.get("payment_verified"):
            flags.append("unverified_payment")
        if not client.get("hires"):
            flags.append("no_hire_history")
        if any("outside" in r.lower() or "whatsapp" in r.lower() for r in client.get("freelancer_reviews", [])):
            flags.append("bad_reviews")
            reasons.append("a freelancer review reports off-platform requests")
    b = job.get("budget", {})
    if b.get("max", 0) <= 20:
        flags.append("low_budget")
    scam_core = {"unpaid_work", "off_platform_contact", "off_platform_payment", "upfront_fee"} & set(sig)
    risk = 0.15 + 0.55 * bool(scam_core) + 0.1 * len(scam_core) + 0.25 * (1 - quality) + 0.1 * ("bad_reviews" in flags)
    is_scam = bool(scam_core) or (quality < 0.25 and b.get("max", 0) <= 20)
    return RiskReport(risk_score=round(min(1.0, risk), 3), is_scam=is_scam, flags=sorted(set(flags)),
                      injection_detected="prompt_injection" in sig, client_quality=round(min(1.0, quality), 3),
                      reasons=reasons or ["no scam signals"])


def assess(job: dict, client: dict) -> RiskReport:
    text = f"{job['title']}\n{job['description']}"
    sig = rule_signals(text)
    base = heuristic_report(job, client, sig)
    rep = llm.structured("risk_assessor", "risk_assessor", RiskReport, lambda: base, max_tokens=700,
                         job=llm.untrusted("job_post", text),
                         client=json.dumps({k: client.get(k) for k in ("payment_verified", "total_spent", "hires", "hire_rate",
                                                                      "avg_rating_given", "freelancer_reviews")}),
                         signals=json.dumps(sig))
    # rules are a floor: the model may add risk, never remove a rule-detected scam or injection
    if base.is_scam:
        rep.is_scam = True
        rep.risk_score = max(rep.risk_score, base.risk_score)
    if base.injection_detected:
        rep.injection_detected = True
        if "prompt_injection" not in rep.flags:
            rep.flags.append("prompt_injection")
    rep.client_quality = base.client_quality if rep.client_quality == 0.5 else rep.client_quality
    return rep
