"""GigSim adapter: HTTP client with a client-side rate limiter, bounded retries with backoff,
Retry-After handling for 429 and a circuit breaker that turns repeated failures into
MarketplaceUnavailable (degraded mode)."""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any

import httpx

from agent import settings
from agent.marketplace_port import MarketplaceUnavailable


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            while self.hits and now - self.hits[0] > 60:
                self.hits.popleft()
            if len(self.hits) >= self.per_minute:
                time.sleep(60 - (now - self.hits[0]) + 0.05)
            self.hits.append(time.time())


_limiters: dict[str, RateLimiter] = {}


class GigSimAdapter:
    mode = "gigsim"

    def __init__(self, base_url: str | None = None, token: str | None = None, transport: httpx.BaseTransport | None = None,
                 max_retries: int = 3):
        self.base = (base_url or os.getenv("GIGSIM_BASE_URL", "http://localhost:8081")).rstrip("/")
        self.token = token or os.getenv("GIGSIM_API_TOKEN", "gigsim-dev-token")
        self.client = httpx.Client(base_url=self.base, timeout=15, transport=transport,
                                   headers={"Authorization": f"Bearer {self.token}"})
        self.max_retries = max_retries
        self.limiter = _limiters.setdefault(self.token, RateLimiter(settings.get("marketplace.max_requests_per_minute", 40)))
        self.failures = 0
        self.open_until = 0.0

    def _req(self, method: str, path: str, **kw) -> dict[str, Any]:
        if time.time() < self.open_until:
            raise MarketplaceUnavailable("circuit open: GigSim failed repeatedly, retrying shortly")
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            try:
                r = self.client.request(method, path, **kw)
            except httpx.HTTPError as e:
                last = e
                time.sleep(min(0.5 * 2 ** attempt, 4))
                continue
            if r.status_code == 429:
                time.sleep(min(float(r.headers.get("Retry-After", 2)), 10))
                last = RuntimeError("rate limited")
                continue
            if r.status_code >= 500:
                last = RuntimeError(f"GigSim {r.status_code}")
                time.sleep(min(0.5 * 2 ** attempt, 4))
                continue
            self.failures = 0
            if r.status_code >= 400:
                return {"error": r.json().get("detail") or r.json().get("error") or r.text, "status": r.status_code}
            return r.json()
        self.failures += 1
        if self.failures >= 3:
            self.open_until = time.time() + 30
        raise MarketplaceUnavailable(f"GigSim unavailable after retries: {last}")

    # ---- reads
    def search_jobs(self, query="", limit=20, posted_within_min=None, ids_prefix=None, offset=0):
        params = {"q": query, "limit": limit, "offset": offset}
        if posted_within_min is not None:
            params["posted_within_min"] = posted_within_min
        if ids_prefix:
            params["ids_prefix"] = ids_prefix
        return self._req("GET", "/v1/jobs", params=params)

    def get_job(self, job_id):
        return self._req("GET", f"/v1/jobs/{job_id}")

    def get_client(self, client_id):
        return self._req("GET", f"/v1/clients/{client_id}")

    def market_stats(self, category):
        return self._req("GET", "/v1/market/stats", params={"category": category})

    def connects_balance(self, freelancer_id):
        return self._req("GET", f"/v1/freelancers/{freelancer_id}/connects")

    def list_threads(self, freelancer_id):
        return self._req("GET", "/v1/threads", params={"freelancer_id": freelancer_id})

    def get_thread(self, thread_id):
        return self._req("GET", f"/v1/threads/{thread_id}")

    def list_proposals(self, freelancer_id):
        return self._req("GET", "/v1/proposals", params={"freelancer_id": freelancer_id})

    # ---- writes (idempotent by key)
    def create_proposal_draft(self, freelancer_id, job_id, cover_letter, bid_amount, screening_answers, idempotency_key):
        return self._req("POST", "/v1/proposals", headers={"Idempotency-Key": idempotency_key},
                         json={"freelancer_id": freelancer_id, "job_id": job_id, "cover_letter": cover_letter,
                               "bid_amount": bid_amount, "screening_answers": screening_answers})

    def submit_proposal(self, proposal_id, idempotency_key):
        return self._req("POST", f"/v1/proposals/{proposal_id}/submit", headers={"Idempotency-Key": idempotency_key})

    def send_message(self, thread_id, body, idempotency_key):
        return self._req("POST", f"/v1/threads/{thread_id}/messages", headers={"Idempotency-Key": idempotency_key},
                         json={"body": body})

    def health(self):
        try:
            r = self.client.get("/health", timeout=3)
            return {"ok": r.status_code == 200, "mode": self.mode, **(r.json() if r.status_code == 200 else {})}
        except httpx.HTTPError as e:
            return {"ok": False, "mode": self.mode, "error": str(e)}
