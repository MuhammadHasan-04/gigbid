"""Live Upwork adapter (A4): the official Upwork MCP server over Streamable HTTP with OAuth 2.1.

* Transport: langchain-mcp-adapters MultiServerMCPClient -> https://mcp.upwork.com/mcp
* Auth: OAuth 2.1 + PKCE via the MCP SDK's OAuthClientProvider; tokens are stored encrypted per
  user (apps/api/auth/token_store.py) and never logged.
* Tool mapping: Upwork's tool names are discovered at connect time and mapped onto this port by
  `UPWORK_TOOL_MAP` (override in config.yaml `marketplace.upwork_tool_map`).
* Writes: Upwork creates drafts that the user confirms on Upwork. `submit_proposal` therefore
  returns status "awaiting_platform_confirmation"; GigBid never auto-confirms.
* No scraping, no browser automation, no session cookies. Read polling is limited by
  marketplace.live_poll_interval_minutes (see docs/RUNBOOK.md).

Status: implemented against the MCP protocol; it has NOT been exercised against a real Upwork
account in this repository (no account was available). See docs/TOOLS.md.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from agent import settings
from agent.marketplace_port import MarketplaceUnavailable

UPWORK_MCP_URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")

# port method -> candidate Upwork MCP tool names (first one that exists wins)
UPWORK_TOOL_MAP: dict[str, list[str]] = {
    "search_jobs": ["search_jobs", "job_search", "find_jobs"],
    "get_job": ["get_job", "get_job_details", "job_details"],
    "get_client": ["get_client", "get_client_details", "client_info"],
    "connects_balance": ["get_connects_balance", "connects_balance"],
    "list_threads": ["list_rooms", "list_conversations", "list_messages"],
    "get_thread": ["get_room", "get_conversation", "get_messages"],
    "list_proposals": ["list_proposals", "get_proposals"],
    "create_proposal_draft": ["create_proposal_draft", "draft_proposal", "create_proposal"],
    "send_message": ["create_message_draft", "draft_message", "send_message"],
}


class UpworkLiveAdapter:
    mode = "upwork_live"

    def __init__(self, user_id: str = "default", access_token: str | None = None):
        self.user_id = user_id
        self.access_token = access_token or self._load_token(user_id)
        self._tools: dict[str, Any] | None = None
        mapping = settings.get("marketplace.upwork_tool_map") or {}
        self.map = {**UPWORK_TOOL_MAP, **mapping}

    @staticmethod
    def _load_token(user_id: str) -> str | None:
        try:
            from apps.api.auth.token_store import get_token
            return get_token(user_id, "upwork")
        except Exception:
            return None

    def _client(self):
        from langchain_mcp_adapters.client import MultiServerMCPClient
        if not self.access_token:
            raise MarketplaceUnavailable("Upwork is not connected: complete the OAuth flow in Settings")
        return MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": UPWORK_MCP_URL,
                                                "headers": {"Authorization": f"Bearer {self.access_token}"}}})

    async def _call(self, method: str, args: dict) -> Any:
        client = self._client()
        if self._tools is None:
            self._tools = {t.name: t for t in await client.get_tools()}
        name = next((n for n in self.map.get(method, []) if n in self._tools), None)
        if not name:
            raise MarketplaceUnavailable(f"Upwork MCP exposes no tool for {method}; update marketplace.upwork_tool_map")
        out = await self._tools[name].ainvoke(args)
        if isinstance(out, str):
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return {"text": out}
        return out

    def _run(self, method: str, **args) -> Any:
        try:
            return asyncio.run(self._call(method, {k: v for k, v in args.items() if v is not None}))
        except MarketplaceUnavailable:
            raise
        except Exception as e:  # network, auth expiry, tool errors
            raise MarketplaceUnavailable(f"Upwork MCP error: {type(e).__name__}: {e}") from e

    def search_jobs(self, query="", limit=20, posted_within_min=None, ids_prefix=None, offset=0):
        r = self._run("search_jobs", query=query, limit=limit)
        jobs = r.get("jobs", r if isinstance(r, list) else [])
        return {"total": len(jobs), "jobs": jobs}

    def get_job(self, job_id):
        return self._run("get_job", job_id=job_id)

    def get_client(self, client_id):
        return self._run("get_client", client_id=client_id)

    def market_stats(self, category):
        # Upwork exposes no market statistics tool; pricing falls back to the job budget and the floor.
        return {"category": category, "n": 0, "note": "not available in live mode"}

    def connects_balance(self, freelancer_id):
        return self._run("connects_balance")

    def list_threads(self, freelancer_id):
        r = self._run("list_threads")
        return {"threads": r.get("rooms", r if isinstance(r, list) else [])}

    def get_thread(self, thread_id):
        return self._run("get_thread", room_id=thread_id)

    def list_proposals(self, freelancer_id):
        return {"proposals": self._run("list_proposals")}

    def create_proposal_draft(self, freelancer_id, job_id, cover_letter, bid_amount, screening_answers, idempotency_key):
        r = self._run("create_proposal_draft", job_id=job_id, cover_letter=cover_letter, amount=bid_amount,
                      answers=screening_answers)
        return {"proposal_id": r.get("id") or r.get("proposal_id") or idempotency_key, "status": "draft", "platform": r}

    def submit_proposal(self, proposal_id, idempotency_key):
        # Upwork requires the user to confirm the draft on Upwork itself.
        return {"proposal_id": proposal_id, "status": "awaiting_platform_confirmation",
                "note": "Open Upwork to confirm this draft; GigBid never confirms on your behalf."}

    def send_message(self, thread_id, body, idempotency_key):
        r = self._run("send_message", room_id=thread_id, message=body)
        return {"status": "draft_on_platform", "platform": r}

    def health(self):
        return {"ok": bool(self.access_token), "mode": self.mode,
                "error": None if self.access_token else "Upwork not connected"}
