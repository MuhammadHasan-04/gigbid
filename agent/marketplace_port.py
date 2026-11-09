"""R1: the single marketplace interface. Two adapters implement it (GigSim, live Upwork via its
official MCP server); `marketplace.mode` in config picks one. Only the Marketplace MCP server
holds an adapter; agents see MCP tools, so the graph cannot tell which marketplace it is using.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent import settings


class MarketplaceUnavailable(RuntimeError):
    """Raised after retries are exhausted; the UI shows the degraded-mode banner."""


@runtime_checkable
class MarketplacePort(Protocol):
    mode: str

    def search_jobs(self, query: str = "", limit: int = 20, posted_within_min: int | None = None,
                    ids_prefix: str | None = None, offset: int = 0) -> dict[str, Any]: ...
    def get_job(self, job_id: str) -> dict[str, Any]: ...
    def get_client(self, client_id: str) -> dict[str, Any]: ...
    def market_stats(self, category: str) -> dict[str, Any]: ...
    def connects_balance(self, freelancer_id: str) -> dict[str, Any]: ...
    def list_threads(self, freelancer_id: str) -> dict[str, Any]: ...
    def get_thread(self, thread_id: str) -> dict[str, Any]: ...
    def list_proposals(self, freelancer_id: str) -> dict[str, Any]: ...
    def create_proposal_draft(self, freelancer_id: str, job_id: str, cover_letter: str, bid_amount: float,
                              screening_answers: list[str], idempotency_key: str) -> dict[str, Any]: ...
    def submit_proposal(self, proposal_id: str, idempotency_key: str) -> dict[str, Any]: ...
    def send_message(self, thread_id: str, body: str, idempotency_key: str) -> dict[str, Any]: ...
    def health(self) -> dict[str, Any]: ...


def get_adapter(mode: str | None = None, **kw) -> MarketplacePort:
    mode = mode or settings.get("marketplace.mode", "gigsim")
    if mode == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
        return GigSimAdapter(**kw)
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter
        return UpworkLiveAdapter(**kw)
    raise ValueError(f"unknown marketplace mode {mode}")
