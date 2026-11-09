"""Long-term memory on the LangGraph store (Postgres in production, in-memory in tests).

Namespaces (all per user = tenant scoping):
  ("style", user)              promoted style rules learned from the user's edits
  ("style_candidates", user)   observed edit patterns waiting for promotion
  ("outcome", user)            per job category: proposals sent, replies, hires, winning exemplars
  ("edits", user)              raw edit diffs (kept for the memory viewer and the promotion rule)
Only agent/memory/promotion_rules.py writes to "style" and "outcome".
"""
from __future__ import annotations

import os

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

_store: BaseStore | None = None


def set_store(s: BaseStore):
    global _store
    _store = s


def get_store() -> BaseStore:
    global _store
    if _store is None:
        _store = InMemoryStore()
    return _store


async def style_rules(user: str) -> list[str]:
    items = await get_store().asearch(("style", user), limit=50)
    return [i.value["rule"] for i in items if i.value.get("promoted")]


async def exemplars(user: str, category: str | None, limit: int = 2) -> list[str]:
    if not category:
        return []
    item = await get_store().aget(("outcome", user), category)
    if not item:
        return []
    return item.value.get("exemplars", [])[-limit:]


async def outcome_stats(user: str, category: str | None) -> dict:
    if not category:
        return {}
    item = await get_store().aget(("outcome", user), category)
    return item.value if item else {}


async def list_memory(user: str) -> dict:
    s = get_store()
    out = {}
    for ns in ("style", "style_candidates", "outcome", "edits"):
        out[ns] = [{"key": i.key, **i.value} for i in await s.asearch((ns, user), limit=200)]
    return out


async def delete_memory(user: str, namespace: str, key: str):
    await get_store().adelete((namespace, user), key)
