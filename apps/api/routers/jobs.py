"""Job inbox, job detail, scouting and analysis triggers."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent.runtime import get_runtime
from apps.api import db
from apps.api.auth.security import User
from apps.api.queue import enqueue
from apps.api.schemas.models import Accepted, JobDetail, JobRow

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def to_row(r: dict) -> JobRow:
    posted = r.get("posted") or {}
    return JobRow(**{k: r.get(k) for k in JobRow.model_fields if k in r and k not in ("flags", "reasons", "budget")},
                  flags=r.get("flags") or [], reasons=r.get("reasons") or [], budget=posted.get("budget"))


@router.get("", response_model=list[JobRow])
async def inbox(u: dict = User, status: str | None = None, action: str | None = None, limit: int = 100):
    rows = await db.q("select * from jobs_seen where user_id=%s order by (action='bid') desc, fit_score desc nulls last, updated_at desc limit %s",
                      u["id"], limit)
    out = [to_row(r) for r in rows]
    if status:
        out = [r for r in out if r.status == status]
    if action:
        out = [r for r in out if r.action == action]
    return out


@router.post("/scout", response_model=Accepted)
async def scout_now(u: dict = User):
    await enqueue("scout_job", u["id"])
    return Accepted(detail="scouting queued")


@router.post("/{job_id}/analyse", response_model=Accepted)
async def analyse(job_id: str, u: dict = User):
    rt = await get_runtime()
    await db.q("insert into jobs_seen (user_id, job_id, status) values (%s,%s,'queued') on conflict do nothing", u["id"], job_id)
    await enqueue("analyse_job", u["id"], job_id, job_id=f"analyse:{u['id']}:{job_id}")
    return Accepted(thread_id=rt.bid_thread(u["id"], job_id), job_id=job_id)


@router.post("/{job_id}/retry", response_model=Accepted)
async def retry(job_id: str, u: dict = User):
    await db.q("update jobs_seen set status='queued' where user_id=%s and job_id=%s and status in ('dead_letter','error','needs_attention')",
               u["id"], job_id)
    await enqueue("analyse_job", u["id"], job_id)
    return Accepted(job_id=job_id)


@router.get("/{job_id}", response_model=JobDetail)
async def detail(job_id: str, u: dict = User):
    rt = await get_runtime()
    row = await db.q1("select * from jobs_seen where user_id=%s and job_id=%s", u["id"], job_id)
    st = await rt.state(rt.bid_thread(u["id"], job_id), u["id"])
    if not row and not st["values"]:
        raise HTTPException(404, "job not analysed yet")
    v = dict(st["values"])
    job = v.get("job") or (row or {}).get("posted") or {}
    v.pop("job", None)
    return JobDetail(job=job, row=to_row(row) if row else None, state=v, next=st["next"],
                     interrupt=st["interrupts"][0] if st["interrupts"] else None)
