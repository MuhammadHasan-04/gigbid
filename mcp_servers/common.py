"""Shared MCP-server plumbing: caller identity, bearer auth, per-user rate limit, append-only audit
log (hash-chained, PII-masked) and an idempotency store."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from agent.tracing import mask_pii

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.getenv("RUNTIME_DIR", ROOT / "data" / "runtime"))


def parse_tokens(env: str, default: str) -> dict[str, str]:
    """"tok1:user1,tok2:user2" -> {tok: user}"""
    raw = os.getenv(env, default)
    out = {}
    for pair in raw.split(","):
        if ":" in pair:
            t, u = pair.split(":", 1)
            out[t.strip()] = u.strip()
    return out


def caller(ctx) -> tuple[str, str | None]:
    """(user_id, trace_id) from the HTTP request when served over HTTP, else local."""
    try:
        req = ctx.request_context.request
        if req is not None:
            return req.headers.get("x-gigbid-user", "anonymous"), req.headers.get("x-trace-id")
    except Exception:
        pass
    return os.getenv("GIGBID_LOCAL_USER", "local"), None


class UserRateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, user: str) -> float:
        """Returns 0 if allowed, else seconds to wait."""
        with self.lock:
            now = time.time()
            q = self.hits[user]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return 60 - (now - q[0])
            q.append(now)
            return 0.0


class AuditLog:
    """Append-only JSONL; each line carries the hash of the previous line (tamper-evident)."""

    def __init__(self, name: str):
        self.path = RUNTIME / "audit" / f"{name}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def _last_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return "genesis"
        with open(self.path, "rb") as f:
            f.seek(max(0, self.path.stat().st_size - 4096))
            last = f.read().decode().strip().splitlines()[-1]
        return json.loads(last)["hash"]

    def append(self, user: str, tool: str, arguments: dict, result: dict | str, trace_id: str | None):
        with self.lock:
            rec = {"ts": time.time(), "user": user, "tool": tool,
                   "arguments": json.loads(mask_pii(json.dumps(arguments, default=str))),
                   "result": json.loads(mask_pii(json.dumps(result, default=str)))[:2000] if isinstance(result, str) else
                   json.loads(mask_pii(json.dumps(result, default=str))),
                   "trace_id": trace_id, "prev": self._last_hash()}
            rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()[:16]
            with open(self.path, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")

    def read(self, limit: int = 200) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines()[-limit:]]


class IdempotencyStore:
    def __init__(self, name: str):
        p = RUNTIME / f"{name}_idempotency.sqlite"
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(p, check_same_thread=False)
        self.db.execute("create table if not exists idem (key text primary key, result text, ts real)")
        self.lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self.lock:
            row = self.db.execute("select result from idem where key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, result: dict):
        with self.lock:
            self.db.execute("insert or ignore into idem values (?,?,?)", (key, json.dumps(result, default=str), time.time()))
            self.db.commit()


def bearer_middleware(app, tokens: dict[str, str], open_paths=("/health",)):
    """ASGI wrapper: 401 unless Authorization: Bearer <known token>; sets x-gigbid-user header."""
    async def wrapped(scope, receive, send):
        if scope["type"] != "http" or scope["path"] in open_paths:
            return await app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        tok = auth.removeprefix("Bearer ").strip()
        if tok not in tokens:
            body = b'{"error":"unauthorized"}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
            await send({"type": "http.response.body", "body": body})
            return
        new_headers = [(k, v) for k, v in scope["headers"] if k != b"x-gigbid-user"]
        new_headers.append((b"x-gigbid-user", tokens[tok].encode()))
        scope = dict(scope, headers=new_headers)
        return await app(scope, receive, send)
    return wrapped
