"""Node wrapper: trace scope, usage accounting, step/token budgets, timeouts and error capture."""
from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Awaitable, Callable

from langgraph.errors import GraphInterrupt
from langgraph.types import RetryPolicy

from agent import llm, settings, tracing
from agent.mcp_client import MCPTools, ToolUnavailable

NODE_TIMEOUT_S = {"writer": 120, "critic": 90, "verifier": 90, "client_liaison": 90}
RETRY = RetryPolicy(max_attempts=2, initial_interval=0.5, backoff_factor=2.0,
                    retry_on=lambda e: isinstance(e, (ToolUnavailable, asyncio.TimeoutError, ConnectionError)))


def tools_from(config: dict) -> MCPTools:
    c = (config or {}).get("configurable", {})
    t = c.get("tools")
    if t is None:
        t = MCPTools(user=c.get("user_id", "demo"), trace_id=c.get("trace_id"))
        c["tools"] = t
    return t


def over_budget(state: dict) -> str | None:
    b = settings.get("budgets")
    if state.get("steps", 0) >= b["max_graph_steps"]:
        return f"step budget exceeded ({state.get('steps')} >= {b['max_graph_steps']})"
    if state.get("tokens", 0) >= b["max_tokens_per_job"]:
        return f"token budget exceeded ({state.get('tokens')} >= {b['max_tokens_per_job']})"
    return None


def node(name: str):
    def deco(fn: Callable[[dict, dict], Awaitable[dict]]):
        @functools.wraps(fn)
        async def wrapped(state: dict, config: dict | None = None) -> dict:
            if state.get("trace_id"):
                tracing.set_trace(state["trace_id"])
            reason = over_budget(state)
            if reason:
                tracing.emit("budget", name, reason=reason)
                return {"status": "needs_attention", "attention_reason": reason, "steps": 1,
                        "log": [{"node": name, "msg": reason}]}
            usage = llm.start_usage()
            t0 = time.time()
            with tracing.node_scope(name):
                tracing.emit("node_start", name)
                try:
                    out = await asyncio.wait_for(fn(state, config or {}), NODE_TIMEOUT_S.get(name, 60))
                except GraphInterrupt:
                    raise
                except (ToolUnavailable, asyncio.TimeoutError, ConnectionError):
                    raise  # RetryPolicy retries; graph runner turns final failure into dead_letter
                dt = round(time.time() - t0, 3)
                tracing.emit("node_end", name, latency_s=dt, tokens=usage["tokens"], usd=usage["usd"],
                             providers=sorted(set(usage["providers"])))
            out = dict(out or {})
            out["steps"] = 1
            out["tokens"] = usage["tokens"]
            out["usd"] = usage["usd"]
            msg = out.pop("_log", None)
            out["log"] = [{"node": name, "latency_s": dt, "tokens": usage["tokens"], "msg": msg or "",
                           "providers": sorted(set(usage["providers"]))}]
            return out
        wrapped.node_name = name
        return wrapped
    return deco
