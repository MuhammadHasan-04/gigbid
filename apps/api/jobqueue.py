"""Enqueue background work: Arq on Redis, or inline asyncio tasks when RUN_INLINE=1 (single container)."""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("gigbid.queue")
_arq = None
_inline_tasks: set[asyncio.Task] = set()
INLINE = os.getenv("RUN_INLINE", "0") == "1"


async def _pool():
    global _arq
    if _arq is None:
        from arq import create_pool
        from arq.connections import RedisSettings
        _arq = await create_pool(RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0")))
    return _arq


async def enqueue(fn: str, *args, job_id: str | None = None):
    if INLINE:
        from worker import main as wm

        class _Ctx(dict):
            pass

        async def run():
            try:
                ctx = _Ctx(redis=_InlineRedis())
                await getattr(wm, fn)(ctx, *args)
            except Exception:
                log.exception("inline task %s failed", fn)
        t = asyncio.create_task(run())
        _inline_tasks.add(t)
        t.add_done_callback(_inline_tasks.discard)
        return job_id
    p = await _pool()
    j = await p.enqueue_job(fn, *args, _job_id=job_id)
    return j.job_id if j else job_id


class _InlineRedis:
    async def enqueue_job(self, fn, *args, _job_id=None):
        return await enqueue(fn, *args, job_id=_job_id)
