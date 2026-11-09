"""MCP client discipline (A6): each agent gets only the tools it needs, filtered by name; every call
has a timeout, bounded retries with backoff, a trace span, and a clear degraded mode.

Transports (env MCP_TRANSPORT):
  http   - MultiServerMCPClient over Streamable HTTP to the three GigBid servers (+ GitHub MCP)
  inproc - the same FastMCP server objects called in-process (same schemas and validation, no
           network); used by evals and CI so 600-job runs are fast. Protocol-level behaviour is
           covered by tests/contract using a real in-memory MCP client session.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from agent import tracing

ALLOWLIST: dict[str, set[str]] = {
    "scout": {"marketplace.search_jobs", "marketplace.get_job"},
    "analyst": set(),
    "risk_assessor": {"marketplace.get_client_history", "marketplace.get_job"},
    "fit_matcher": {"portfolio.search_evidence", "portfolio.list_skills"},
    "pricing": {"marketplace.get_market_stats", "marketplace.get_client_history", "marketplace.get_connects_balance"},
    "writer": {"portfolio.search_evidence", "portfolio.get_case_study"},
    "critic": {"portfolio.search_evidence"},
    "verifier": {"portfolio.search_evidence"},
    "compliance": set(),
    "client_liaison": {"marketplace.list_messages", "marketplace.get_thread", "marketplace.send_message",
                       "workspace.free_slots", "workspace.create_tentative_hold", "workspace.create_email_draft"},
    # the approval executor is not an LLM agent: it runs only after a human approved in the UI
    "executor": {"marketplace.create_proposal_draft", "marketplace.submit_proposal", "marketplace.send_message",
                 "marketplace.get_connects_balance", "workspace.create_tentative_hold"},
    "ui": {"marketplace.list_proposals", "marketplace.list_messages", "marketplace.get_connects_balance",
           "marketplace.get_job", "marketplace.search_jobs", "marketplace.get_thread",
           "marketplace.create_proposal_draft", "marketplace.submit_proposal", "marketplace.send_message",
           "portfolio.search_evidence", "portfolio.list_skills", "workspace.free_slots"},
}

SERVER_URLS = {
    "portfolio": os.getenv("PORTFOLIO_MCP_URL", "http://localhost:8101/mcp"),
    "marketplace": os.getenv("MARKETPLACE_MCP_URL", "http://localhost:8102/mcp"),
    "workspace": os.getenv("WORKSPACE_MCP_URL", "http://localhost:8103/mcp"),
}
SERVER_TOKENS = {
    "portfolio": os.getenv("PORTFOLIO_MCP_TOKEN", "dev-portfolio-token"),
    "marketplace": os.getenv("MARKETPLACE_MCP_TOKEN", "dev-marketplace-token"),
    "workspace": os.getenv("WORKSPACE_MCP_TOKEN", "dev-workspace-token"),
}


class ToolNotAllowed(PermissionError):
    pass


class ToolUnavailable(RuntimeError):
    """The server is down or kept failing; callers switch to degraded mode (queue + banner)."""


def _inproc_server(server: str):
    if server == "portfolio":
        from mcp_servers.portfolio.server import mcp
    elif server == "marketplace":
        from mcp_servers.marketplace.server import mcp
    elif server == "workspace":
        from mcp_servers.workspace.server import mcp
    else:
        raise ToolUnavailable(f"unknown server {server}")
    return mcp


def _unwrap(result) -> Any:
    # FastMCP.call_tool returns (content_blocks, structured) or a list of content blocks
    if isinstance(result, tuple) and len(result) == 2:
        content, structured = result
        if structured is not None:
            return structured.get("result", structured) if isinstance(structured, dict) and set(structured) == {"result"} else structured
        result = content
    texts = [getattr(c, "text", "") for c in (result or [])]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


class MCPTools:
    def __init__(self, transport: str | None = None, user: str = "demo", trace_id: str | None = None,
                 timeout: float = 20.0, retries: int = 2):
        self.transport = transport or os.getenv("MCP_TRANSPORT", "inproc")
        self.user, self.trace_id = user, trace_id
        self.timeout, self.retries = timeout, retries
        self._http_tools: dict[str, Any] | None = None
        self.degraded: dict[str, str] = {}

    async def _http(self):
        if self._http_tools is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            conns = {name: {"transport": "streamable_http", "url": url,
                            "headers": {"Authorization": f"Bearer {SERVER_TOKENS[name]}",
                                        "x-trace-id": self.trace_id or tracing.current_trace_id()}}
                     for name, url in SERVER_URLS.items()}
            client = MultiServerMCPClient(conns)
            tools = {}
            for name in conns:
                try:
                    for t in await client.get_tools(server_name=name):
                        tools[f"{name}.{t.name}"] = t
                except Exception as e:
                    self.degraded[name] = f"{type(e).__name__}: {e}"[:200]
            self._http_tools = tools
        return self._http_tools

    async def call(self, agent: str, qualified: str, **args) -> Any:
        if qualified not in ALLOWLIST.get(agent, set()):
            raise ToolNotAllowed(f"agent '{agent}' may not call {qualified}")
        server, tool = qualified.split(".", 1)
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            t0 = time.time()
            try:
                if self.transport == "http":
                    tools = await self._http()
                    if qualified not in tools:
                        raise ToolUnavailable(f"{server} server unavailable: {self.degraded.get(server, 'tool missing')}")
                    raw = await asyncio.wait_for(tools[qualified].ainvoke(args), self.timeout)
                    out = json.loads(raw) if isinstance(raw, str) and raw[:1] in "[{" else raw
                    if isinstance(out, list) and out and isinstance(out[0], dict) and "text" in out[0]:
                        out = json.loads(out[0]["text"])
                else:
                    srv = _inproc_server(server)
                    out = _unwrap(await asyncio.wait_for(srv.call_tool(tool, args), self.timeout))
                if isinstance(out, dict) and out.get("error") == "marketplace_unavailable":
                    raise ToolUnavailable(out.get("detail", "marketplace unavailable"))
                if isinstance(out, dict) and isinstance(out.get("error"), str) and "marketplace_unavailable" in out["error"]:
                    raise ToolUnavailable(out["error"])
                tracing.emit("tool", qualified, agent=agent, args=args, ok=True, latency_s=round(time.time() - t0, 3),
                             result_preview=str(out)[:300])
                return out
            except ToolNotAllowed:
                raise
            except (ToolUnavailable, asyncio.TimeoutError, ConnectionError, OSError) as e:
                last = e
            except Exception as e:  # tool raised (validation, rate limit) -> retry once, then surface
                last = e
                if "validation" in str(e).lower():
                    break
            tracing.emit("tool_error", qualified, agent=agent, args=args, error=str(last)[:300], attempt=attempt)
            await asyncio.sleep(min(0.4 * 2 ** attempt, 3))
        raise ToolUnavailable(f"{qualified} failed after retries: {last}")
