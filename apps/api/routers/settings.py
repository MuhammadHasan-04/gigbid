"""Settings, memory viewer (see / delete what GigBid learned), portfolio uploads, health."""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter

from agent import settings as cfg
from agent.marketplace_port import get_adapter
from agent.memory.store import delete_memory, list_memory
from apps.api import db
from apps.api.auth.security import User
from apps.api.schemas.models import Accepted, Health, MemoryOut, SettingsModel, UploadIn
from rag.ingest.loaders import UPLOAD_DIR

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsModel)
async def get_settings(u: dict = User):
    return SettingsModel(**u["settings"])


@router.put("/settings", response_model=SettingsModel)
async def put_settings(body: SettingsModel, u: dict = User):
    await db.q("update users set settings=%s where id=%s", db.j(body.model_dump()), u["id"])
    return body


@router.get("/memory", response_model=MemoryOut)
async def memory(u: dict = User):
    return MemoryOut(**await list_memory(u["id"]))


@router.delete("/memory/{namespace}/{key}", response_model=Accepted)
async def forget(namespace: str, key: str, u: dict = User):
    if namespace not in ("style", "style_candidates", "outcome", "edits"):
        return Accepted(queued=False, detail="unknown namespace")
    await delete_memory(u["id"], namespace, key)
    return Accepted(queued=False, detail=f"deleted {namespace}/{key}")


@router.post("/portfolio/upload", response_model=Accepted)
async def upload(body: UploadIn, u: dict = User):
    """Add work to the portfolio; the Portfolio MCP server re-indexes this persona incrementally."""
    d = UPLOAD_DIR / u["persona"]
    d.mkdir(parents=True, exist_ok=True)
    eid = f"{u['persona']}:upload:{uuid.uuid4().hex[:8]}"
    (d / f"{eid.split(':')[-1]}.json").write_text(json.dumps({"evidence_id": eid, "title": body.title, "text": body.text,
                                                               "industry": body.industry, "date": body.date or time.strftime("%Y"),
                                                               "project_id": eid.split(":")[-1], "user": u["id"]}))
    from mcp_servers.portfolio.server import bump_version
    bump_version(u["persona"])
    return Accepted(queued=False, detail=f"indexed as {eid}")


@router.get("/health", response_model=Health)
async def health():
    return Health(marketplace=get_adapter().health(), model_profile=cfg.get("models.profile"),
                  policy_version=int(cfg.get("policy.version", 1)))
