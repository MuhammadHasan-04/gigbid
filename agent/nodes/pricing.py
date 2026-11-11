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


def quote_real(job: dict, spec: dict, client: dict, real: dict, hourly_floor: float, fit_score: float,
               policy: dict, reply_rate_prior: float = 0.25) -> PriceQuote:
    """Real Upwork posts: price from real awarded contracts (Kaggle) and the post's own budget type.

    hourly posts -> an hourly rate inside the posted range; fixed / no-budget posts -> a fixed amount from
    the real fixed-contract percentiles, capped by the posted budget. Never below the user's floor."""
    from agent import budget as B
    con, post = real.get("contracts") or {}, real.get("postings_2024") or {}
    k = B.kind(job)
    b = job.get("budget") or {}
    unit = settings.get("thresholds.connects_value_per_unit_usd", 0.15)
    cost = connects_cost(job, policy)
    p_reply = reply_rate_prior * (0.5 + fit_score)
    if k == "hourly":
        h50, h75 = con.get("hourly_p50") or hourly_floor, con.get("hourly_p75") or hourly_floor
        target = (h50 + h75) / 2 if fit_score > 0.8 else h50
        if client.get("total_spent", 0) > 50000:
            target *= 1.08
        lo, hi = float(b.get("min") or 0), float(b.get("max") or 0)
        rate = min(max(target, hourly_floor, lo), hi) if hi else max(target, hourly_floor)
        ev = p_reply * 0.35 * rate * 20 * 0.1  # ~20 billed hours for a first engagement
        rationale = (f"Real {job.get('category')} contracts pay ${con.get('hourly_p25')}-${con.get('hourly_p75')}/h "
                     f"(median ${con.get('hourly_p50')}, n={con.get('n_hourly')}); posted range ${lo:.0f}-${hi:.0f}/h; "
                     f"your floor ${hourly_floor:.0f}/h. Bid ${rate:.0f}/h. {cost} Connects (~${cost * unit:.2f}) vs expected value ${ev:.2f}.")
        return PriceQuote(amount=round(rate) or 1, unit="hour", market_p25=con.get("hourly_p25"), market_p50=con.get("hourly_p50"),
                          market_p75=con.get("hourly_p75"), floor=hourly_floor, connects_cost=cost,
                          connects_worth_it=ev > cost * unit, expected_value_usd=round(ev, 2), rationale=rationale, market_source="real")
    f25, f50, f75 = con.get("fixed_p25"), con.get("fixed_p50"), con.get("fixed_p75")
    hr = con.get("hourly_p50") or 30.0
    est_hours = (f50 / hr) * (0.8 + 0.12 * len(spec.get("requirements") or [])) if f50 else 10.0
    floor = round(hourly_floor * est_hours * 0.5, -1)
    target = f50 or post.get("budget_p50") or floor
    if fit_score > 0.8 and f75:
        target = (target + f75) / 2
    cap = B.fixed_cap(job)
    if cap:
        target = min(target, cap)
    amount = max(target, floor, 50.0)
    ev = p_reply * 0.35 * amount * 0.1
    rationale = (f"Real completed fixed-price {job.get('category')} contracts: p25/p50/p75 ${f25}/${f50}/${f75} "
                 f"(n={con.get('n_fixed')}); posted budget {'$%.0f' % cap if cap else 'not stated'}; floor {floor:.0f} from your rate. "
                 f"Bid {amount:.0f}. {cost} Connects (~${cost * unit:.2f}) vs expected value ${ev:.2f}.")
    return PriceQuote(amount=round(amount, -1) or 50, market_p25=f25, market_p50=f50, market_p75=f75, floor=floor,
                      connects_cost=cost, connects_worth_it=ev > cost * unit, expected_value_usd=round(ev, 2),
                      rationale=rationale, market_source="real")


def quote(job: dict, spec: dict, client: dict, market: dict, hourly_floor: float, fit_score: float,
          policy: dict, reply_rate_prior: float = 0.25) -> PriceQuote:
    from agent import budget as B
    real = B.real_market(job, market)
    if real:
        return quote_real(job, spec, client, real, hourly_floor, fit_score, policy, reply_rate_prior)
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
