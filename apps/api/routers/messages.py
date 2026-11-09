"""Client conversations and the proposal pipeline board."""
from __future__ import annotations

from fastapi import APIRouter

from agent.mcp_client import MCPTools, ToolUnavailable
from agent.runtime import get_runtime
from apps.api import db
from apps.api.auth.security import User
from apps.api.jobqueue import enqueue
from apps.api.schemas.models import Accepted, Conversation, PipelineCard

router = APIRouter(prefix="/api", tags=["messages"])
ORDER = ["draft", "submitted", "viewed", "replied", "interview", "hired", "lost"]


@router.get("/messages", response_model=list[Conversation])
async def conversations(u: dict = User):
    rt = await get_runtime()
    tools = MCPTools(user=u["id"])
    threads = {}
    try:
        for t in (await tools.call("ui", "marketplace.list_messages", freelancer_id=u["freelancer_id"]))["data"].get("threads", []):
            threads[t["thread_id"]] = t
    except ToolUnavailable:
        pass
    out = []
    for c in await db.q("select * from conversations where user_id=%s order by updated_at desc", u["id"]):
        pending = None
        if c["graph_thread"]:
            st = await rt.state(c["graph_thread"], u["id"])
            pending = st["interrupts"][0] if st["interrupts"] else None
        out.append(Conversation(**{k: c.get(k) for k in Conversation.model_fields if k in c},
                                messages=threads.get(c["thread_id"], {}).get("messages", []), pending=pending))
    return out


@router.post("/messages/sync", response_model=Accepted)
async def sync(u: dict = User):
    await enqueue("sync_job", u["id"])
    return Accepted(detail="sync queued")


@router.post("/messages/{thread_id}/draft", response_model=Accepted)
async def draft(thread_id: str, u: dict = User):
    await enqueue("converse_job", u["id"], thread_id)
    return Accepted(thread_id=thread_id)


@router.get("/pipeline", response_model=list[PipelineCard])
async def pipeline(u: dict = User):
    rows = await db.q("select * from pipeline where user_id=%s order by updated_at desc", u["id"])
    drafted = await db.q("select job_id, title, category, price, connects_cost, updated_at from jobs_seen where user_id=%s and status='awaiting_approval'", u["id"])
    cards = [PipelineCard(proposal_id="pending-" + d["job_id"], job_id=d["job_id"], title=d["title"], category=d["category"],
                          status="drafted", bid=d["price"], connects=d["connects_cost"], updated_at=d["updated_at"]) for d in drafted]
    cards += [PipelineCard(**{k: r.get(k) for k in PipelineCard.model_fields if k in r}) for r in rows]
    return cards
