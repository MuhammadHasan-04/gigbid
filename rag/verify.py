"""Claim splitting and grounding (B3). Runs after drafting, before the Critic.

1. split the proposal into sentences; keep those that assert experience (claims)
2. for each claim collect candidate evidence: ids it cites + top hits for the claim text
3. entity check: skills (canonical + ontology aliases), numbers, proper nouns must appear in
   the evidence -> supported / partial / unsupported
4. optional LLM adjudication for claims the entity check cannot decide (no entities)
5. unsupported claims are removed (or the sentence rewritten) before the Critic sees the draft
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from agent import llm, settings
from agent.handoffs import Claim
from gigsim.world import SKILLS
from rag.skills import tag_skills

CITE = re.compile(r"\[E:([^\]]+)\]")
FUTURE = re.compile(r"\b(i would|i'd|i will|i'll|i can|i could|i plan|i propose|we could|we can|happy to|let's|would you|could you)\b", re.I)
EXPERIENCE = re.compile(r"\b(i (have|'ve|built|delivered|shipped|led|created|designed|developed|used|worked|implemented|deployed|automated|reduced|improved|cut|ran|wrote|migrated|trained|analysed|analyzed)|my (work|project|experience)|years of|experience (with|in))\b", re.I)
NUM = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|ms|k|x|weeks?|hours?|years?)?")
STOP_CAPS = {"I", "My", "For", "The", "This", "That", "Your", "In", "On", "At", "We", "It", "As", "With", "And", "But",
             "Happy", "Hi", "Hello", "Thanks", "Best", "Looking", "If", "When", "Since", "After", "Before", "To", "A", "An"}


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def is_claim(sentence: str) -> bool:
    s = CITE.sub("", sentence)
    if s.strip().endswith("?"):
        return False
    if FUTURE.search(s) and not EXPERIENCE.search(s):
        return False
    return bool(EXPERIENCE.search(s) or (tag_skills(s) and re.search(r"\b(i|my)\b", s, re.I)))


def _skills_in(text: str) -> set[str]:
    low = text.lower()
    found = set(tag_skills(text, code=True))
    for k, aliases in SKILLS.items():
        if any(a.lower() in low for a in aliases):
            found.add(k)
    return found


def entities(claim: str) -> dict[str, set[str]]:
    c = CITE.sub("", claim)
    nums = {n.strip().lower() for n in NUM.findall(c) if re.search(r"\d", n)}
    caps = {w for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}(?:\s[A-Z][a-zA-Z]+)?\b", c)
            if w.split()[0] not in STOP_CAPS and not tag_skills(w)}
    return {"skills": _skills_in(c), "numbers": nums, "names": caps}


def _check(claim: str, evidence_texts: dict[str, str]) -> tuple[str, list[str], str]:
    ent = entities(claim)
    total = sum(len(v) for v in ent.values())
    if not evidence_texts:
        return "unsupported", [], "no evidence retrieved or cited"
    best, best_ids, missing_best = -1.0, [], []
    joined_skills = {eid: _skills_in(t) for eid, t in evidence_texts.items()}
    for eid, t in evidence_texts.items():
        low = t.lower()
        found, missing = 0, []
        for s in ent["skills"]:
            if s in joined_skills[eid]:
                found += 1
            else:
                missing.append(s)
        for n in ent["numbers"]:
            (found := found + 1) if n.split()[0] in low else missing.append(n)
        for n in ent["names"]:
            (found := found + 1) if n.lower() in low else missing.append(n)
        frac = found / total if total else 0.0
        if frac > best:
            best, best_ids, missing_best = frac, [eid], missing
    if total == 0:
        return "partial", best_ids, "no checkable entities"
    # allow the union of cited items to support a claim (e.g. CV line + case study)
    union_missing = [m for m in missing_best if not any(
        (m in joined_skills[e]) or (m.lower() in evidence_texts[e].lower()) for e in evidence_texts)]
    if not union_missing:
        return "supported", list(evidence_texts)[:3] if best < 1 else best_ids, "all entities found"
    thr = settings.get("verification.support_threshold", 0.5)
    hard_missing = [m for m in union_missing if m in ent["numbers"] or m in ent["names"]]
    if hard_missing:  # a wrong client name or number is fabrication, not "partly supported"
        return "unsupported", best_ids, f"unverifiable facts: {', '.join(hard_missing)}"
    if best >= thr:
        return "partial", best_ids, f"missing: {', '.join(union_missing)}"
    return "unsupported", best_ids, f"missing: {', '.join(union_missing)}"


class _Verdicts(BaseModel):
    verdicts: list[dict]


def verify(text: str, retriever, evidence_lookup: dict[str, str] | None = None, use_llm: bool = True) -> list[Claim]:
    """evidence_lookup: evidence_id -> text for ids the writer was shown (cited ids resolve here)."""
    evidence_lookup = evidence_lookup or {}
    by_id = {c.evidence_id: c.text for c in retriever.chunks}
    claims = []
    for sent in split_sentences(text):
        if not is_claim(sent):
            continue
        cited = CITE.findall(sent)
        ev = {}
        for cid in cited:
            for one in cid.split(","):
                one = one.strip()
                if one in evidence_lookup:
                    ev[one] = evidence_lookup[one]
                elif one in by_id:
                    ev[one] = by_id[one]
        for h in retriever.retrieve_query(CITE.sub("", sent), k=3):
            for c in h.chunks[:2]:
                ev.setdefault(c.evidence_id, by_id.get(c.evidence_id, c.text))
        verdict, ids, reason = _check(sent, ev)
        claims.append(Claim(text=sent, verdict=verdict, evidence_ids=ids, reason=reason))
    if use_llm:
        ambiguous = [c for c in claims if c.reason == "no checkable entities"]
        if ambiguous:
            ev_text = "\n".join(f"{i}: {by_id.get(i, evidence_lookup.get(i, ''))[:400]}" for c in ambiguous for i in c.evidence_ids)
            out = llm.structured("verifier", "verifier", _Verdicts, lambda: _Verdicts(verdicts=[]), max_tokens=600,
                                 claims="\n".join(f"{i}. {c.text}" for i, c in enumerate(ambiguous)), evidence=ev_text)
            for i, v in enumerate(out.verdicts[: len(ambiguous)]):
                if v.get("verdict") in ("supported", "partial", "unsupported"):
                    ambiguous[i].verdict = v["verdict"]
                    ambiguous[i].reason = "llm: " + str(v.get("reason", ""))[:200]
    return claims


def apply(text: str, claims: list[Claim]) -> str:
    """Remove unsupported claim sentences; keep partial ones (the Critic sees their reasons)."""
    if not settings.get("verification.remove_unsupported", True):
        return text
    bad = {c.text for c in claims if c.verdict == "unsupported"}
    kept = [s for s in split_sentences(text) if s not in bad]
    return " ".join(kept)


def unsupported_rate(claims: list[Claim]) -> int:
    return sum(c.verdict == "unsupported" for c in claims)
