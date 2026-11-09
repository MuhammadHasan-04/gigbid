"""Analytics: reply/hire by category, Connects vs outcomes, cost and latency, rejection reasons."""
from __future__ import annotations

from fastapi import APIRouter

from apps.api import db
from apps.api.auth.security import User
from apps.api.schemas.models import Analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 3) if xs else None


@router.get("", response_model=Analytics)
async def analytics(u: dict = User):
    uid = u["id"]
    cats = await db.q("""select coalesce(category,'unknown') as category, count(*) as sent,
                         sum(case when status in ('replied','interview','hired') then 1 else 0 end) as replied,
                         sum(case when status='hired' then 1 else 0 end) as hired, sum(connects) as connects
                         from pipeline where user_id=%s group by 1 order by 2 desc""", uid)
    for c in cats:
        c["reply_rate"] = round(c["replied"] / c["sent"], 3) if c["sent"] else None
        c["hire_rate"] = round(c["hired"] / c["sent"], 3) if c["sent"] else None
    jobs = await db.q("select action, status, tokens, usd, latency_s from jobs_seen where user_id=%s", uid)
    spent = sum(c["connects"] or 0 for c in cats)
    funnel = {"seen": len(jobs), "bid": sum(j["action"] == "bid" for j in jobs), "skipped": sum(j["action"] == "skip" for j in jobs),
              "watch": sum(j["action"] == "watch" for j in jobs), "submitted": sum(c["sent"] for c in cats),
              "replied": sum(c["replied"] for c in cats), "hired": sum(c["hired"] for c in cats)}
    lat = [j["latency_s"] for j in jobs]
    props = [j for j in jobs if j["status"] in ("awaiting_approval", "submitted", "approved")]
    cost = {"jobs": len(jobs), "p50_latency_s_per_job": pct(lat, 0.5), "p95_latency_s_per_job": pct(lat, 0.95),
            "usd_per_job": round(sum(j["usd"] or 0 for j in jobs) / len(jobs), 6) if jobs else None,
            "p95_latency_s_per_proposal": pct([j["latency_s"] for j in props], 0.95),
            "usd_per_proposal": round(sum(j["usd"] or 0 for j in props) / len(props), 6) if props else None,
            "tokens_per_job": round(sum(j["tokens"] or 0 for j in jobs) / len(jobs), 1) if jobs else None}
    rej = await db.q("select reason, count(*) as n from rejections where user_id=%s group by reason order by n desc limit 10", uid)
    skip = await db.q("select reasons from jobs_seen where user_id=%s and action='skip'", uid)
    from collections import Counter
    sk = Counter((r["reasons"] or ["?"])[0].split(":")[0].split(" ")[0] for r in skip)
    rejection = [{"reason": r["reason"], "n": r["n"], "kind": "user_rejected_draft"} for r in rej] + \
                [{"reason": k, "n": n, "kind": "agent_skip"} for k, n in sk.most_common(6)]
    return Analytics(by_category=cats, connects={"spent": spent, "weekly_budget": u["settings"].get("weekly_connects_budget"),
                                                 "per_reply": round(spent / funnel["replied"], 1) if funnel["replied"] else None},
                     cost_latency=cost, rejection_reasons=rejection, funnel=funnel)
