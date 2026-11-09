"""One trace id from the UI request through the API, the graph, every MCP call and the audit log.

Spans are written (PII-masked) to data/runtime/traces/<trace_id>.jsonl, which the Agent run viewer
reads, and mirrored to Langfuse when LANGFUSE_PUBLIC_KEY/SECRET_KEY are set.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = Path(os.getenv("TRACE_DIR", ROOT / "data" / "runtime" / "traces"))
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_node: contextvars.ContextVar[str | None] = contextvars.ContextVar("node", default=None)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+\d[\d\s-]{7,}\d|\b\d{3}[\s.-]\d{3,4}[\s.-]\d{3,4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")


SECRET_KEYS = {"token", "access_token", "refresh_token", "api_key", "authorization", "approval_id", "ciphertext"}


def mask_pii(text: str) -> str:
    text = EMAIL.sub("[EMAIL]", text)
    text = CARD.sub("[CARD]", text)
    text = IBAN.sub("[IBAN]", text)
    text = PHONE.sub("[PHONE]", text)
    return text


def _mask(obj):
    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in SECRET_KEYS or "secret" in k.lower() or "password" in k.lower() else _mask(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(x) for x in obj]
    return obj


def new_trace_id() -> str:
    return "tr-" + uuid.uuid4().hex[:16]


def current_trace_id() -> str:
    t = _trace_id.get()
    if not t:
        t = new_trace_id()
        _trace_id.set(t)
    return t


@contextmanager
def trace(trace_id: str | None = None):
    tok = _trace_id.set(trace_id or new_trace_id())
    try:
        yield _trace_id.get()
    finally:
        _trace_id.reset(tok)


def set_trace(trace_id: str):
    _trace_id.set(trace_id)


@contextmanager
def node_scope(name: str):
    tok = _node.set(name)
    try:
        yield
    finally:
        _node.reset(tok)


def current_node() -> str | None:
    return _node.get()


_langfuse = None


def _lf():
    global _langfuse
    if _langfuse is None and os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            from langfuse import Langfuse
            _langfuse = Langfuse()
        except Exception:
            _langfuse = False
    return _langfuse or None


def emit(kind: str, name: str, **data) -> dict:
    span = {"ts": time.time(), "trace_id": current_trace_id(), "node": current_node(), "kind": kind, "name": name,
            **_mask(data)}
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRACE_DIR / f"{span['trace_id']}.jsonl", "a") as f:
        f.write(json.dumps(span, default=str) + "\n")
    lf = _lf()
    if lf:
        try:
            lf.create_event(trace_context={"trace_id": span["trace_id"].replace("tr-", "").ljust(32, "0")},
                            name=f"{kind}:{name}", metadata=span)
        except Exception:
            pass
    return span


def read_trace(trace_id: str) -> list[dict]:
    f = TRACE_DIR / f"{trace_id}.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def summarize(trace_id: str) -> dict:
    spans = read_trace(trace_id)
    by_node: dict[str, dict] = {}
    for s in spans:
        if s["kind"] != "llm":
            continue
        n = by_node.setdefault(s.get("node") or "?", {"tokens_in": 0, "tokens_out": 0, "usd": 0.0, "calls": 0, "latency_s": 0.0})
        n["tokens_in"] += s.get("tokens_in", 0)
        n["tokens_out"] += s.get("tokens_out", 0)
        n["usd"] += s.get("usd", 0.0)
        n["calls"] += 1
        n["latency_s"] += s.get("latency_s", 0.0)
    return {"trace_id": trace_id, "spans": len(spans), "by_node": by_node,
            "tokens": sum(v["tokens_in"] + v["tokens_out"] for v in by_node.values()),
            "usd": round(sum(v["usd"] for v in by_node.values()), 6)}
