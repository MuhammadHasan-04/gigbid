"""Budget helpers: synthetic jobs are fixed-price; real Upwork posts can be hourly or state no budget."""
from __future__ import annotations


def kind(job: dict) -> str:
    """'fixed' | 'hourly' | 'unknown' (missing or zero budget)."""
    b = job.get("budget") or {}
    t = b.get("type") or "fixed"
    if job.get("source") != "real":
        return t if t in ("fixed", "hourly") else "unknown"  # synthetic posts: a $0 budget is a real signal (scams)
    if t not in ("fixed", "hourly") or not (b.get("max") or 0) > 0:
        return "unknown"
    return t


def fixed_cap(job: dict) -> float | None:
    """The posted fixed-price ceiling, or None when the job is hourly / has no budget."""
    return float(job["budget"]["max"]) if kind(job) == "fixed" else None


def hourly_cap(job: dict) -> float | None:
    """The top of the posted hourly range, or None."""
    return float(job["budget"]["max"]) if kind(job) == "hourly" else None


def real_market(job: dict, market: dict) -> dict:
    """For real posts, prefer the real (Kaggle) percentiles that GigSim returns next to the synthetic ones."""
    if job.get("source") == "real" and isinstance(market.get("real"), dict):
        return market["real"]
    return {}
