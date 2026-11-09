"""Explicit promotion rules: the only code that writes long-term memory.

Style memory  - an edit pattern (e.g. "cut the first sentence", "never say 'passionate'") becomes a
                promoted rule only after it is observed in >= memory.style_promotion_min_occurrences
                distinct approved edits, and is dropped if a later edit contradicts it.
Outcome memory - per job category, counts of sent / replied / hired come ONLY from marketplace
                status events for proposals the user approved; a proposal text becomes an exemplar
                only if it got a reply AND the category has >= memory.outcome_promotion_min_samples sends.
"""
from __future__ import annotations

import difflib
import re
import time

from agent import settings
from agent.memory.store import get_store

BANNED_WORD_CANDIDATES = ["passionate", "excited", "dear sir", "hello", "i hope this finds you well", "guarantee",
                          "rockstar", "ninja", "best quality", "100%", "hard-working", "expert"]


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]


def diff_patterns(before: str, after: str) -> list[tuple[str, str]]:
    """Extract (key, rule) style patterns from one human edit."""
    pats = []
    b, a = _sentences(before), _sentences(after)
    if b and a and b[0] != a[0] and b[0] not in a:
        pats.append(("cut_first_sentence", "Cut the generic first sentence; open directly with the client's problem."))
    bl, al = before.lower(), after.lower()
    for w in BANNED_WORD_CANDIDATES:
        if w in bl and w not in al:
            pats.append((f"avoid:{w}", f"Never say \"{w}\"."))
    if len(after.split()) < 0.8 * len(before.split()):
        pats.append(("shorter", "Keep proposals short: under 150 words."))
    if after.strip().endswith("?") and not before.strip().endswith("?"):
        pats.append(("end_with_question", "End with one concrete question for the client."))
    if re.search(r"\bmilestone", al) and not re.search(r"\bmilestone", bl):
        pats.append(("milestones", "Propose concrete milestones."))
    return pats


def unified_diff(before: str, after: str) -> str:
    return "\n".join(difflib.unified_diff(_sentences(before), _sentences(after), "draft", "edited", lineterm=""))


async def record_edit(user: str, job_id: str, before: str, after: str) -> dict:
    """Called when the user edits a draft in the approval screen. Returns what was promoted."""
    s = get_store()
    edit_id = f"{job_id}-{int(time.time())}"
    pats = diff_patterns(before, after)
    await s.aput(("edits", user), edit_id, {"job_id": job_id, "diff": unified_diff(before, after),
                                             "patterns": [k for k, _ in pats], "ts": time.time()})
    need = settings.get("memory.style_promotion_min_occurrences", 2)
    promoted = []
    for key, rule in pats:
        cand = await s.aget(("style_candidates", user), key)
        seen = set(cand.value["edits"]) if cand else set()
        seen.add(job_id)  # distinct jobs, so one edit session cannot promote alone
        await s.aput(("style_candidates", user), key, {"rule": rule, "edits": sorted(seen), "count": len(seen)})
        if len(seen) >= need:
            existing = await s.aget(("style", user), key)
            if not existing:
                await s.aput(("style", user), key, {"rule": rule, "promoted": True, "promoted_at": time.time(),
                                                    "because": f"seen in {len(seen)} edits: {sorted(seen)[:5]}"})
                promoted.append(rule)
    # contradiction: the user re-added a word we had banned -> demote that rule
    for w in BANNED_WORD_CANDIDATES:
        if w in after.lower() and w not in before.lower():
            if await s.aget(("style", user), f"avoid:{w}"):
                await s.adelete(("style", user), f"avoid:{w}")
    return {"patterns": [k for k, _ in pats], "promoted": promoted}


async def record_outcome(user: str, category: str, proposal_text: str, status: str) -> dict:
    """Called from marketplace status events (replied / hired / lost) for approved proposals."""
    s = get_store()
    item = await s.aget(("outcome", user), category)
    v = item.value if item else {"sent": 0, "replied": 0, "hired": 0, "lost": 0, "exemplars": []}
    if status == "submitted":
        v["sent"] += 1
    elif status in ("replied", "hired", "lost", "interview"):
        key = "replied" if status == "interview" else status
        v[key] = v.get(key, 0) + 1
    if status in ("replied", "interview", "hired") and v["sent"] >= settings.get("memory.outcome_promotion_min_samples", 3):
        if proposal_text not in v["exemplars"]:
            v["exemplars"] = (v["exemplars"] + [proposal_text[:900]])[-5:]
    v["reply_rate"] = round(v["replied"] / v["sent"], 3) if v["sent"] else None
    await s.aput(("outcome", user), category, v)
    return v
