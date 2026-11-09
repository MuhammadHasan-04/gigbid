"""GigBid API (FastAPI). `uvicorn apps.api.main:app --port 8000`"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agent import tracing
from agent.runtime import get_runtime
from apps.api import db
from apps.api.routers import analytics, approvals, auth, jobs, messages, runs, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


class PIIFilter(logging.Filter):
    def filter(self, record):
        record.msg = tracing.mask_pii(str(record.msg))
        return True


for h in logging.getLogger().handlers:
    h.addFilter(PIIFilter())

ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = ROOT / "apps" / "web" / "dist"


async def seed_reviewer():
    """Reviewer login preloaded with a persona (credentials come from env, never from the repo)."""
    email = os.getenv("REVIEWER_EMAIL")
    pw = os.getenv("REVIEWER_PASSWORD")
    if not email or not pw:
        return
    from agent.graphs.bid_graph import persona_profile
    from apps.api.auth.security import create_user, default_settings, hash_pw
    persona = os.getenv("REVIEWER_PERSONA", "ai_ml")
    u = await db.q1("select * from users where email=%s", email.lower())
    if not u:
        u = await create_user(email, pw, "Reviewer")
    prof = persona_profile(persona)
    s = default_settings()
    s["hourly_floor"] = prof["hourly_floor"]
    s["saved_searches"] = [{"id": "s1", "query": os.getenv("REVIEWER_SEARCH", ""), "every_minutes": 30, "limit": 12}]
    await db.q("update users set persona=%s, freelancer_id=%s, password_hash=%s, settings=coalesce(nullif(settings,'{}'::jsonb), %s) where id=%s",
               persona, prof["freelancer_id"], hash_pw(pw), db.j(s), u["id"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.pool()
    await get_runtime()
    await seed_reviewer()
    yield
    await db.close()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_mw(request: Request, call_next):
    """One trace id flows from the UI request through the API, the graph, MCP servers and the audit log."""
    tid = request.headers.get("x-trace-id") or tracing.new_trace_id()
    tracing.set_trace(tid)
    resp = await call_next(request)
    resp.headers["x-trace-id"] = tid
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logging.getLogger("gigbid.api").exception("unhandled error")
    return JSONResponse({"detail": "internal error", "type": type(exc).__name__}, status_code=500)


for r in (auth, jobs, approvals, messages, runs, analytics, settings):
    app.include_router(r.router)

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = WEB_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
