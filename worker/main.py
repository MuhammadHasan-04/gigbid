"""Arq worker. `arq worker.main.WorkerSettings`

Schedules: every user's saved searches are scouted on their own interval (GigSim default 30 min,
live mode >= marketplace.live_poll_interval_minutes, see docs/RUNBOOK.md); marketplace sync every
5 minutes. Jobs use deterministic Arq job ids, so a job enqueued twice runs once.
"""
from __future__ import annotations

import os
import time

from arq import cron
from arq.connections import RedisSettings

from agent import settings
from apps.api import db
from worker import tasks


async def scout_job(ctx, user_id: str):
    res = await tasks.scout(user_id)
    for jid in res.get("queued", []):
        await ctx["redis"].enqueue_job("analyse_job", user_id, jid, _job_id=f"analyse:{user_id}:{jid}")
    return res


async def analyse_job(ctx, user_id: str, job_id: str):
    return await tasks.analyse(user_id, job_id)


async def resume_job(ctx, user_id: str, thread: str, decision: dict):
    return await tasks.resume(user_id, thread, decision)


async def converse_job(ctx, user_id: str, thread_id: str):
    return await tasks.converse(user_id, thread_id)


async def sync_job(ctx, user_id: str):
    res = await tasks.sync_marketplace(user_id)
    for t in res.get("new_messages", []):
        await ctx["redis"].enqueue_job("converse_job", user_id, t, _job_id=f"conv:{user_id}:{t}:{int(time.time() // 300)}")
    return res


def _interval_minutes(user: dict) -> int:
    mode = user["settings"].get("marketplace", "gigsim")
    base = settings.get("worker.scout_interval_minutes", 30)
    if mode == "upwork_live":
        return max(base, settings.get("marketplace.live_poll_interval_minutes", 240))
    searches = user["settings"].get("saved_searches") or [{}]
    return max(base, min(s.get("every_minutes", base) for s in searches))


async def tick(ctx):
    """Every minute: enqueue scouting for users whose interval elapsed, sync every 5 minutes."""
    now = int(time.time() // 60)
    for u in await db.q("select * from users where persona is not null"):
        if now % _interval_minutes(u) == 0:
            await ctx["redis"].enqueue_job("scout_job", u["id"], _job_id=f"scout:{u['id']}:{now}")
        if now % 5 == 0:
            await ctx["redis"].enqueue_job("sync_job", u["id"], _job_id=f"sync:{u['id']}:{now}")


async def startup(ctx):
    await db.pool()


async def shutdown(ctx):
    await db.close()


class WorkerSettings:
    functions = [scout_job, analyse_job, resume_job, converse_job, sync_job]
    cron_jobs = [cron(tick, minute=set(range(60)), run_at_startup=False)]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = int(os.getenv("WORKER_CONCURRENCY", "4"))
    job_timeout = 600
    keep_result = 3600
