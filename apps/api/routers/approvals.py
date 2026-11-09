"""Pending human approvals (LangGraph interrupts) and decisions that resume the graph thread."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent.runtime import get_runtime
from apps.api import db
from apps.api.auth.security import User
from apps.api.jobqueue import enqueue
from apps.api.schemas.models import Accepted, Approval, DecisionIn

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[Approval])
async def pending(u: dict = User):
    """Read from the checkpointer, so a page refresh (or an API restart) never loses a pending approval."""
    rt = await get_runtime()
    out = []
    rows = await db.q("select job_id, title, thread_id, updated_at from jobs_seen where user_id=%s and status in ('awaiting_approval','needs_attention')",
                      u["id"])
    for r in rows:
        st = await rt.state(r["thread_id"], u["id"])
        if st["interrupts"]:
            out.append(Approval(thread_id=r["thread_id"], kind="proposal", title=r["title"], created=r["updated_at"], payload=st["interrupts"][0]))
    for c in await db.q("select * from conversations where user_id=%s and graph_thread is not null", u["id"]):
        st = await rt.state(c["graph_thread"], u["id"])
        if st["interrupts"]:
            out.append(Approval(thread_id=c["graph_thread"], kind="message", title=c["thread_id"], created=c["updated_at"], payload=st["interrupts"][0]))
    return out


@router.post("/{thread_id:path}/decision", response_model=Accepted)
async def decide(thread_id: str, body: DecisionIn, u: dict = User):
    if not thread_id.startswith((f"bid:{u['id']}:", f"conv:{u['id']}:")):
        raise HTTPException(403, "not your thread")
    rt = await get_runtime()
    st = await rt.state(thread_id, u["id"])
    if not st["interrupts"]:
        raise HTTPException(409, "nothing is waiting for approval on this thread")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    decision = body.model_dump(exclude_none=True)
    await enqueue("resume_job", u["id"], thread_id, decision)
    return Accepted(thread_id=thread_id, detail=f"{body.action} queued")


class RegenIn(BaseModel):
    sentence_index: int = Field(ge=0, le=40)
    text: str = Field(max_length=5000)


class RegenOut(BaseModel):
    text: str
    sentence: str


@router.post("/{thread_id:path}/regenerate", response_model=RegenOut)
async def regenerate(thread_id: str, body: RegenIn, u: dict = User):
    """Regenerate one sentence/paragraph of the draft, grounded in evidence the writer has not used yet."""
    if not thread_id.startswith(f"bid:{u['id']}:"):
        raise HTTPException(403, "not your thread")
    from agent import llm
    from rag.verify import CITE, split_sentences
    rt = await get_runtime()
    st = await rt.state(thread_id, u["id"])
    ev = (st["values"].get("evidence") or {})
    sents = split_sentences(body.text)
    if body.sentence_index >= len(sents):
        raise HTTPException(422, "no such sentence")
    used = set(x for s in sents for c in CITE.findall(s) for x in c.split(","))
    spare = [k for k in ev if k not in used]

    def heuristic() -> str:
        if spare:
            k = spare[0]
            title = ev[k].split(" (", 1)[0]
            return f"Another relevant example is \"{title}\" [E:{k}]."
        return sents[body.sentence_index]
    new = llm.text("writer", "regenerate", heuristic, max_tokens=200, sentence=sents[body.sentence_index],
                   evidence="\n".join(f"{k}: {ev[k][:300]}" for k in spare[:4]) or "none",
                   draft=body.text)
    sents[body.sentence_index] = new.strip()
    return RegenOut(text=" ".join(sents), sentence=new.strip())
