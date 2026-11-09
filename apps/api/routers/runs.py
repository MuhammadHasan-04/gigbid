"""Agent run viewer: live node-by-node progress (SSE), traces, checkpoint history and replay."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent import tracing
from agent.runtime import get_runtime
from apps.api import db
from apps.api.auth.security import User
from apps.api.schemas.models import RunEvent, TraceOut, TraceSpan

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[dict])
async def recent(u: dict = User, limit: int = 50):
    return await db.q("select job_id, title, status, action, thread_id, trace_id, tokens, usd, latency_s, updated_at from jobs_seen "
                      "where user_id=%s and trace_id is not null order by updated_at desc limit %s", u["id"], limit)


@router.get("/events", response_model=list[RunEvent])
async def events(thread_id: str, after: int = 0, u: dict = User):
    return await db.q("select id, thread_id, trace_id, event, ts from run_events where user_id=%s and thread_id=%s and id>%s order by id",
                      u["id"], thread_id, after)


@router.get("/stream")
async def stream(request: Request, thread_id: str, after: int = 0, u: dict = User):
    """Server-Sent Events: node-by-node progress as the worker streams LangGraph updates."""
    async def gen():
        last = after
        idle = 0
        yield "retry: 2000\n\n"
        while idle < 600:
            if await request.is_disconnected():
                break
            rows = await db.q("select id, event, trace_id from run_events where user_id=%s and thread_id=%s and id>%s order by id",
                              u["id"], thread_id, last)
            for r in rows:
                last = r["id"]
                yield f"id: {r['id']}\nevent: run\ndata: {json.dumps({**r['event'], 'trace_id': r['trace_id']}, default=str)}\n\n"
            idle = 0 if rows else idle + 1
            if not rows:
                yield ": keep-alive\n\n" if idle % 20 == 0 else ""
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/trace/{trace_id}", response_model=TraceOut)
async def trace(trace_id: str, u: dict = User):
    own = await db.q1("select 1 as x from jobs_seen where user_id=%s and trace_id=%s union select 1 from run_events where user_id=%s and trace_id=%s limit 1",
                      u["id"], trace_id, u["id"], trace_id)
    if not own and not trace_id.startswith("tr-public-"):
        raise HTTPException(404, "trace not found")
    spans = tracing.read_trace(trace_id)
    return TraceOut(trace_id=trace_id, summary=tracing.summarize(trace_id),
                    spans=[TraceSpan(ts=s["ts"], kind=s["kind"], name=s["name"], node=s.get("node"),
                                     data={k: v for k, v in s.items() if k not in ("ts", "kind", "name", "node", "trace_id")}) for s in spans])


@router.get("/history", response_model=list[dict])
async def history(thread_id: str, u: dict = User):
    if f":{u['id']}:" not in thread_id:
        raise HTTPException(403, "not your thread")
    rt = await get_runtime()
    return await rt.history(thread_id, u["id"])
