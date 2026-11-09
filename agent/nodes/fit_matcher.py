"""Fit Matcher: map every requirement to portfolio evidence (via the Portfolio MCP server), produce a
fit score with reasons."""
from __future__ import annotations

from typing import Awaitable, Callable

from agent import llm
from agent.handoffs import FitReport, RequirementMatch
from rag.skills import GENERIC

Search = Callable[[str, int], Awaitable[dict]]
STRENGTH = {"strong": 1.0, "partial": 0.4, "none": 0.0}


def _ev_text(i: dict) -> str:
    return f"{i.get('title', '')} ({i.get('industry') or 'n/a'}, {i.get('date') or 'n/a'}) — {i['snippet']}"


def _score(matches: list[RequirementMatch]) -> float:
    w = {m.requirement: (0.5 if m.requirement in GENERIC else 1.0) for m in matches}
    return round(sum(w[m.requirement] * STRENGTH[m.strength] for m in matches) / (sum(w.values()) or 1), 3)


async def match(requirements: list[str], search: Search, job: dict) -> tuple[FitReport, dict[str, str]]:
    evidence: dict[str, str] = {}
    matches = []
    for req in requirements:
        res = await search(f"{req} — {job.get('title', '')}", 6)
        items = res.get("items", [])
        strong = [i for i in items if req in i.get("skills", [])]
        if strong:
            for i in strong[:3]:
                evidence[i["evidence_id"]] = _ev_text(i)
            matches.append(RequirementMatch(
                requirement=req, evidence_ids=list(dict.fromkeys(i["evidence_id"] for i in strong))[:3],
                project_ids=list(dict.fromkeys(i["project_id"] for i in strong if i.get("project_id")))[:3],
                strength="strong", note=f"named in {len(strong)} evidence item(s)"))
        elif items and req not in GENERIC and any(req.lower() in i["snippet"].lower() for i in items):
            i = next(i for i in items if req.lower() in i["snippet"].lower())
            evidence[i["evidence_id"]] = _ev_text(i)
            matches.append(RequirementMatch(requirement=req, evidence_ids=[i["evidence_id"]],
                                            project_ids=[i["project_id"]] if i.get("project_id") else [],
                                            strength="partial", note="mentioned but not tagged"))
        else:
            matches.append(RequirementMatch(requirement=req, strength="none", note="no evidence found"))
    if not requirements:
        return FitReport(fit_score=0.0, matches=[], reasons=["no requirements extracted"]), evidence
    unsupported = [m.requirement for m in matches if m.strength == "none"]
    reasons = [f"{sum(m.strength == 'strong' for m in matches)}/{len(matches)} requirements strongly evidenced"]
    if unsupported:
        reasons.append("no evidence for: " + ", ".join(unsupported))
    base = FitReport(fit_score=_score(matches), matches=matches, unsupported_requirements=unsupported, reasons=reasons)
    # show the model the evidence grouped per requirement (every candidate, short snippets)
    by_req = []
    for m in matches:
        ids = m.evidence_ids or []
        by_req.append(f"## {m.requirement}\n" + ("\n".join(f"{i}: {evidence.get(i, '')[:220]}" for i in ids) or "(no candidates)"))
    rep = llm.structured("fit_matcher", "fit_matcher", FitReport, lambda: base, max_tokens=1200,
                         requirements=", ".join(requirements), evidence="\n".join(by_req))
    # merge: the model may confirm or downgrade a rule match only by citing ids it was shown; an answer that
    # drops a requirement or cites unknown ids keeps the rule-based verdict (found in the open-profile run:
    # the model returned "none" with no ids for requirements whose evidence it had been shown)
    rule = {m.requirement: m for m in matches}
    merged = []
    for m in rep.matches:
        m.evidence_ids = [e.strip().removeprefix("[").removeprefix("E:").rstrip("]") for e in m.evidence_ids]
        m.evidence_ids = [e for e in m.evidence_ids if e in evidence]
        r = rule.get(m.requirement)
        if r is None:
            continue
        if not m.evidence_ids and r.strength != "none":
            m = r  # unexplained downgrade -> keep the rule verdict
        merged.append(m)
    seen = {m.requirement for m in merged}
    merged += [m for m in matches if m.requirement not in seen]
    rep.matches = merged
    rep.fit_score = _score(rep.matches)
    rep.unsupported_requirements = [m.requirement for m in rep.matches if m.strength == "none"]
    return rep, evidence
