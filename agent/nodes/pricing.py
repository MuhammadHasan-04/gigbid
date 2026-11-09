"""Pricing Strategist: bid from market statistics, client spend and the user's floor; is the Connects cost worth it?"""
from __future__ import annotations

import json

from agent import llm, settings
from agent.handoffs import PriceQuote


def connects_cost(job: dict, policy: dict) -> int:
    """Connects cost comes from the job plus any surcharge in the active policy pack (change request lives here)."""
    cost = int(job.get("connects_cost", 0))
    for s in (policy.get("connects") or {}).get("surcharges", []) or []:
        when = s.get("when", {})
        if "proposals_count_gte" in when and job.get("proposals_count", 0) >= when["proposals_count_gte"]:
            cost += int(s.get("add", 0))
    return cost


def quote(job: dict, spec: dict, client: dict, market: dict, hourly_floor: float, fit_score: float,
          policy: dict, reply_rate_prior: float = 0.25) -> PriceQuote:
    b = job.get("budget", {})
    bmax, bmin = float(b.get("max") or 0), float(b.get("min") or 0)
    p25, p50, p75 = (market.get(k) for k in ("p25", "p50", "p75"))
    n_req = len(spec.get("requirements") or [])
    # estimated effort from the market median and the floor rate; floor = never price below this
    est_hours = (p50 / 45.0) * (0.8 + 0.12 * n_req) if p50 else max(10.0, bmax / max(hourly_floor, 1))
    floor = round(hourly_floor * est_hours * 0.5, -1)
    target = p50 if p50 else (bmin + bmax) / 2 or floor
    if client.get("total_spent", 0) > 50000:
        target *= 1.08  # established clients pay closer to the upper quartile
    if fit_score > 0.8 and p75:
        target = (target + p75) / 2
    if bmax:
        target = min(target, bmax)  # stay inside the posted budget
    amount = max(target, floor, 50.0)
    cost = connects_cost(job, policy)
    unit = settings.get("thresholds.connects_value_per_unit_usd", 0.15)
    p_reply = reply_rate_prior * (0.5 + fit_score)
    ev = p_reply * 0.35 * amount * 0.1  # chance of a reply x hire-given-reply x 10% margin proxy
    worth = ev > cost * unit
    rationale = (f"Market p50 for {job.get('category')} is {p50}; budget {bmin:.0f}-{bmax:.0f}; floor {floor:.0f} "
                 f"from your rate. Bid {amount:.0f}. {cost} Connects (~${cost * unit:.2f}) vs expected value ${ev:.2f}.")
    return PriceQuote(amount=round(amount, -1) or 50, market_p25=p25, market_p50=p50, market_p75=p75, floor=floor,
                      connects_cost=cost, connects_worth_it=worth, expected_value_usd=round(ev, 2), rationale=rationale)


def price(job, spec, client, market, hourly_floor, fit_score, policy, reply_rate_prior=0.25) -> PriceQuote:
    q = quote(job, spec, client, market, hourly_floor, fit_score, policy, reply_rate_prior)
    out = llm.structured("pricing", "pricing", PriceQuote, lambda: q, max_tokens=400, quote=q.model_dump_json(),
                         budget=json.dumps(job.get("budget")), market=json.dumps(market),
                         client_spend=str(client.get("total_spent")))
    q.rationale = out.rationale or q.rationale  # the model may only rewrite the rationale; numbers are computed
    return q
