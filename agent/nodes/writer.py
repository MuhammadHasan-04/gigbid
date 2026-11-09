"""Proposal Writer: cover letter + screening answers where every claim cites portfolio evidence."""
from __future__ import annotations

import json
import re

from agent import llm
from agent.handoffs import ProposalDraft
from rag.skills import GENERIC

NEED_LINES = {
    "documentation": "I will leave written runbooks and a recorded walkthrough so your team can maintain it without me.",
    "timezone": "I can keep a daily overlap window with your team for check-ins.",
    "deadline": "I would plan the milestones backwards from your demo date so a working version exists a week early.",
    "legacy_code": "I would start by mapping the existing system before changing anything, so nothing breaks silently.",
    "data_privacy": "I would keep sensitive data out of logs and agree data-handling rules with you on day one.",
}


def _short(text: str, n: int = 140) -> str:
    t = re.sub(r"[#*`>\-\[\]]", " ", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n].rsplit(" ", 1)[0]


def heuristic_draft(job: dict, spec: dict, fit: dict, price: dict, evidence: dict[str, str], persona: dict,
                    style_rules: list[str], feedback: list[str], strategy: str = "A") -> ProposalDraft:
    strong = [m for m in fit.get("matches", []) if m["strength"] == "strong" and m["evidence_ids"]]
    strong.sort(key=lambda m: m["requirement"] in GENERIC)
    partial = [m for m in fit.get("matches", []) if m["strength"] == "partial" and m["evidence_ids"]]
    title = job["title"].rstrip(".")
    industry = job.get("industry") or "your"
    focus = [r for r in (spec.get('requirements') or []) if r not in GENERIC][:2] or (spec.get('requirements') or ['the stack'])[:2]
    sents = [f"For your {title.lower()}, the core of the work is getting {' and '.join(focus)} right for a {industry} team, so here is the closest match from my portfolio."]
    used_projects = set()
    for m in (strong + partial)[:3]:
        eid = m["evidence_ids"][0]
        pid = (m.get("project_ids") or [None])[0]
        if pid in used_projects:
            continue
        used_projects.add(pid)
        ev = evidence.get(eid, "")
        ptitle = ev.split(" (", 1)[0].strip() or "a past project"
        res = re.search(r"The project ([^.]+)\.", ev)
        result = f", which {res.group(1)}" if res else ""
        verb = "I used" if m["strength"] == "strong" else "I worked with"
        sents.append(f"{verb} {m['requirement']} on \"{ptitle}\"{result} [E:{eid}].")
    unsupported = fit.get("unsupported_requirements", [])
    if unsupported:
        sents.append(f"I have not used {', '.join(unsupported[:2])} on client work yet, so I would budget time to ramp up and say so up front.")
    for need in spec.get("hidden_needs", [])[:2]:
        if need in NEED_LINES:
            sents.append(NEED_LINES[need])
    reqs = [r for r in (spec.get("requirements") or []) if r not in GENERIC] or spec.get("requirements") or ["the core feature"]
    sents.append(f"I would start with a short scoping call, then deliver {reqs[0]} as the first milestone so you can review real output early.")
    if price:
        sents.append(f"My fixed price for this scope is {price.get('amount', 0):.0f} USD.")
    sents.append("Which part of this is the most urgent for you?")
    if strategy == "B":
        # B = question-first and short: open with a diagnostic question, one proof, one plan line
        q = (f"Before anything else: is the main risk in your {title.lower()} the {focus[0]} part or the hand-over to your team?")
        proof = [x for x in sents if "[E:" in x][:1]
        sents = [q] + proof + [x for x in sents if x.startswith("I would start")][:1] + [x for x in sents if x.startswith("My fixed price")]
    if any("short" in r.lower() for r in style_rules + feedback):
        sents = [sents[0]] + sents[1:3] + sents[-2:]
    answers = []
    for q in spec.get("screening_questions", []):
        if strong:
            eid = strong[0]["evidence_ids"][0]
            answers.append(f"The closest example is {_short(evidence.get(eid, ''), 110)} [E:{eid}]. I would follow the same approach here.")
        else:
            answers.append("I would approach it in small, reviewable milestones and confirm the details on a short call.")
    return ProposalDraft(cover_letter=" ".join(sents), screening_answers=answers)


def write(job: dict, spec: dict, fit: dict, price: dict, evidence: dict[str, str], persona: dict, style_rules: list[str],
          exemplars: list[str], feedback: list[str], revision: int, strategy: str = "A") -> ProposalDraft:
    matrix = [{"requirement": m["requirement"], "strength": m["strength"], "evidence": m["evidence_ids"]} for m in fit.get("matches", [])]
    ev_text = "\n".join(f"{k}: {_short(v, 600)}" for k, v in list(evidence.items())[:12])
    d = llm.structured(
        "writer", "writer" if strategy == "A" else "writer_b", ProposalDraft,
        lambda: heuristic_draft(job, spec, fit, price, evidence, persona, style_rules, feedback, strategy), max_tokens=1500,
        freelancer_name=persona.get("name", ""), freelancer_title=persona.get("title", ""),
        unsupported=", ".join(fit.get("unsupported_requirements", [])) or "none",
        style_rules="; ".join(style_rules) or "none yet", exemplars="\n---\n".join(exemplars) or "none yet",
        job=llm.untrusted("job_post", f"{job['title']}\n{job['description']}"), jobspec=json.dumps(spec),
        matrix=json.dumps(matrix), evidence=ev_text, price=str(price.get("amount") if price else ""),
        feedback="; ".join(feedback))
    d.revision = revision
    d.strategy = strategy
    d.cover_letter = d.cover_letter.strip()
    return d
