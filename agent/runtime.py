"""Graph runtime: Postgres checkpointer + Postgres store (durability, C6), thread ids, streaming,
resume after approval, replay from any checkpoint, dead-letter handling (C7)."""
from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any, AsyncIterator

from langgraph.types import Command

from agent import tracing
from agent.graphs import bid_graph, conversation_graph
from agent.mcp_client import ToolUnavailable
from agent.memory.store import set_store

DB_URL = os.getenv("DATABASE_URL", "postgresql://gigbid:gigbid@localhost:5432/gigbid").replace("+psycopg", "")


class Runtime:
    def __init__(self):
        self.stack = AsyncExitStack()
        self.bid = None
        self.conv = None
        self.checkpointer = None
        self.store = None
        self.backend = None

    async def start(self, backend: str | None = None):
        backend = backend or os.getenv("CHECKPOINT_BACKEND", "postgres")
        if backend == "postgres":
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from langgraph.store.postgres.aio import AsyncPostgresStore
            self.checkpointer = await self.stack.enter_async_context(AsyncPostgresSaver.from_conn_string(DB_URL))
            await self.checkpointer.setup()
            self.store = await self.stack.enter_async_context(AsyncPostgresStore.from_conn_string(DB_URL))
            await self.store.setup()
        else:
            from langgraph.checkpoint.memory import InMemorySaver
            from langgraph.store.memory import InMemoryStore
            self.checkpointer, self.store = InMemorySaver(), InMemoryStore()
        self.backend = backend
        set_store(self.store)
        self.bid = bid_graph.build(self.checkpointer, self.store)
        self.conv = conversation_graph.build(self.checkpointer, self.store)
        return self

    async def stop(self):
        await self.stack.aclose()

    @staticmethod
    def bid_thread(user: str, job_id: str) -> str:
        return f"bid:{user}:{job_id}"

    @staticmethod
    def conv_thread(user: str, thread_id: str) -> str:
        return f"conv:{user}:{thread_id}"

    def graph_for(self, thread_id: str):
        return self.bid if thread_id.startswith("bid:") else self.conv

    def config(self, thread_id: str, user: str, trace_id: str, **extra) -> dict:
        return {"configurable": {"thread_id": thread_id, "user_id": user, "trace_id": trace_id, **extra},
                "recursion_limit": 60}

    async def stream(self, thread_id: str, user: str, inputs: Any, trace_id: str, **extra) -> AsyncIterator[dict]:
        """Yields UI events: node updates, interrupts, final status. Final failure -> dead_letter."""
        g = self.graph_for(thread_id)
        cfg = self.config(thread_id, user, trace_id, **extra)
        tracing.set_trace(trace_id)
        try:
            async for mode, chunk in g.astream(inputs, cfg, stream_mode=["updates", "custom"]):
                if mode == "updates":
                    for node_name, upd in chunk.items():
                        if node_name == "__interrupt__":
                            yield {"type": "interrupt", "payload": upd[0].value}
                        else:
                            upd = upd or {}
                            yield {"type": "node", "node": node_name, "status": upd.get("status"),
                                   "log": (upd.get("log") or [{}])[-1]}
                else:
                    yield {"type": "custom", "data": chunk}
        except (ToolUnavailable, asyncio.TimeoutError) as e:
            await g.aupdate_state(cfg, {"status": "dead_letter", "attention_reason": f"marketplace unavailable: {e}",
                                        "errors": [{"node": "runtime", "error": str(e)[:300]}]})
            yield {"type": "error", "degraded": True, "error": str(e)[:300]}
        state = await g.aget_state(cfg)
        yield {"type": "done", "status": state.values.get("status"), "next": list(state.next),
               "attention_reason": state.values.get("attention_reason")}

    async def run_bid(self, user: str, persona: str, freelancer_id: str, job_id: str, autonomy: str = "suggest",
                      job: dict | None = None, trace_id: str | None = None, **extra) -> dict:
        tid = trace_id or tracing.new_trace_id()
        thread = self.bid_thread(user, job_id)
        inputs = {"user_id": user, "persona": persona, "freelancer_id": freelancer_id, "job_id": job_id,
                  "trace_id": tid, "autonomy": autonomy}
        if job:
            inputs["job"] = job
        events = [e async for e in self.stream(thread, user, inputs, tid, **extra)]
        return {"thread_id": thread, "trace_id": tid, "events": events}

    async def resume(self, thread_id: str, user: str, decision: dict, trace_id: str | None = None) -> list[dict]:
        state = await self.graph_for(thread_id).aget_state(self.config(thread_id, user, trace_id or ""))
        tid = trace_id or state.values.get("trace_id") or tracing.new_trace_id()
        return [e async for e in self.stream(thread_id, user, Command(resume=decision), tid)]

    async def retry(self, thread_id: str, user: str) -> list[dict]:
        """Re-run from the last checkpoint (dead-letter recovery, crash recovery)."""
        state = await self.graph_for(thread_id).aget_state(self.config(thread_id, user, ""))
        return [e async for e in self.stream(thread_id, user, None, state.values.get("trace_id") or tracing.new_trace_id())]

    async def state(self, thread_id: str, user: str) -> dict:
        s = await self.graph_for(thread_id).aget_state(self.config(thread_id, user, ""))
        interrupts = [i.value for t in s.tasks for i in (t.interrupts or [])]
        return {"values": s.values, "next": list(s.next), "interrupts": interrupts,
                "checkpoint_id": s.config["configurable"].get("checkpoint_id")}

    async def history(self, thread_id: str, user: str) -> list[dict]:
        out = []
        async for s in self.graph_for(thread_id).aget_state_history(self.config(thread_id, user, "")):
            out.append({"checkpoint_id": s.config["configurable"]["checkpoint_id"], "next": list(s.next),
                        "status": s.values.get("status"), "step": s.metadata.get("step"),
                        "created_at": s.created_at})
        return out

    async def replay(self, thread_id: str, user: str, checkpoint_id: str) -> list[dict]:
        """Replay (fork) the job from any checkpoint."""
        g = self.graph_for(thread_id)
        cfg = self.config(thread_id, user, tracing.new_trace_id())
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
        return [e async for e in self._astream_cfg(g, cfg)]

    async def _astream_cfg(self, g, cfg):
        async for upd in g.astream(None, cfg, stream_mode="updates"):
            for n, u in upd.items():
                yield {"type": "node", "node": n, "status": (u or {}).get("status") if isinstance(u, dict) else None}


_rt: Runtime | None = None


async def get_runtime() -> Runtime:
    global _rt
    if _rt is None:
        _rt = await Runtime().start()
    return _rt
