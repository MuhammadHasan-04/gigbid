"""Workspace MCP server (A3): calendar slots, tentative interview holds, email drafts.

Backed by a local mock (JSON file per user under data/runtime/workspace). The agent sees MCP
tools only; swapping in Google Calendar / Gmail means re-implementing `Backend`, nothing else.
Run: python -m mcp_servers.workspace.server [--http --port 8103]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import threading
import uuid
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common import RUNTIME, AuditLog, IdempotencyStore, caller

mcp = FastMCP("gigbid-workspace", instructions="Calendar and email-draft tools for a freelancer. Nothing here sends email.")
audit = AuditLog("workspace")
idem = IdempotencyStore("workspace")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class Backend:
    """Local mock calendar: working hours 09:00-17:00 (user TZ), weekdays, some busy blocks."""

    def __init__(self):
        self.lock = threading.Lock()

    def _path(self, user: str):
        p = RUNTIME / "workspace" / f"{user}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def load(self, user: str) -> dict:
        p = self._path(user)
        if p.exists():
            return json.loads(p.read_text())
        return {"busy": [], "holds": [], "drafts": [], "timezone": "Asia/Karachi"}

    def save(self, user: str, d: dict):
        self._path(user).write_text(json.dumps(d, indent=1))


backend = Backend()


class Slot(BaseModel):
    start: str
    end: str
    timezone: str


class Hold(BaseModel):
    hold_id: str
    start: str
    end: str
    title: str
    status: str = "tentative"


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str = "draft"


@mcp.tool(annotations=READ)
def free_slots(ctx: Context, days_ahead: Annotated[int, Field(ge=1, le=14)] = 5,
               duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30,
               max_slots: Annotated[int, Field(ge=1, le=10)] = 3,
               start_date: Annotated[str | None, Field(description="YYYY-MM-DD; default tomorrow")] = None) -> list[Slot]:
    """Free calendar slots in working hours over the next N days (excludes busy blocks and holds)."""
    user, tid = caller(ctx)
    d = backend.load(user)
    taken = [(h["start"], h["end"]) for h in d["holds"]] + [(b["start"], b["end"]) for b in d["busy"]]
    day = dt.date.fromisoformat(start_date) if start_date else dt.date.today() + dt.timedelta(days=1)
    out = []
    for i in range(days_ahead * 2):
        cur = day + dt.timedelta(days=i)
        if cur.weekday() >= 5:
            continue
        for hour in (10, 14, 16):
            s = dt.datetime.combine(cur, dt.time(hour, 0))
            e = s + dt.timedelta(minutes=duration_minutes)
            if any(not (e.isoformat() <= a or s.isoformat() >= b) for a, b in taken):
                continue
            out.append(Slot(start=s.isoformat(timespec="minutes"), end=e.isoformat(timespec="minutes"), timezone=d["timezone"]))
            break  # at most one slot per day, spreads options across days
        if len(out) >= max_slots:
            break
    audit.append(user, "free_slots", {"days_ahead": days_ahead}, {"n": len(out)}, tid)
    return out


@mcp.tool(annotations=WRITE)
def create_tentative_hold(ctx: Context, start: Annotated[str, Field(description="ISO datetime")],
                          end: Annotated[str, Field(description="ISO datetime")],
                          title: Annotated[str, Field(min_length=3, max_length=120)],
                          idempotency_key: Annotated[str, Field(min_length=8, max_length=80)]) -> Hold:
    """Place a tentative calendar hold for a proposed interview slot (no invite is sent)."""
    user, tid = caller(ctx)
    key = f"{user}:hold:{idempotency_key}"
    if (prev := idem.get(key)):
        return Hold(**prev)
    with backend.lock:
        d = backend.load(user)
        h = Hold(hold_id="hold-" + uuid.uuid4().hex[:8], start=start, end=end, title=title)
        d["holds"].append(h.model_dump())
        backend.save(user, d)
    idem.put(key, h.model_dump())
    audit.append(user, "create_tentative_hold", {"start": start, "title": title}, h.model_dump(), tid)
    return h


@mcp.tool(annotations=WRITE)
def create_email_draft(ctx: Context, to: Annotated[str, Field(max_length=200)],
                       subject: Annotated[str, Field(min_length=1, max_length=200)],
                       body: Annotated[str, Field(min_length=1, max_length=8000)],
                       idempotency_key: Annotated[str, Field(min_length=8, max_length=80)]) -> EmailDraft:
    """Save an email draft in the freelancer's mailbox (never sends)."""
    user, tid = caller(ctx)
    key = f"{user}:draft:{idempotency_key}"
    if (prev := idem.get(key)):
        return EmailDraft(**prev)
    with backend.lock:
        d = backend.load(user)
        e = EmailDraft(draft_id="draft-" + uuid.uuid4().hex[:8], to=to, subject=subject, body=body)
        d["drafts"].append(e.model_dump())
        backend.save(user, d)
    idem.put(key, e.model_dump())
    audit.append(user, "create_email_draft", {"to": to, "subject": subject}, {"draft_id": e.draft_id}, tid)
    return e


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"server": "workspace", "ok": True})


def http_app():
    from mcp_servers.common import bearer_middleware, parse_tokens
    return bearer_middleware(mcp.streamable_http_app(), parse_tokens("WORKSPACE_MCP_TOKENS", "dev-workspace-token:demo"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--port", type=int, default=8103)
    a = ap.parse_args()
    if a.http:
        import uvicorn
        uvicorn.run(http_app(), host="0.0.0.0", port=a.port)
    else:
        mcp.run()
