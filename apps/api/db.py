"""Postgres access (psycopg async pool). Every query is scoped by user_id (tenant)."""
from __future__ import annotations

import json
import os
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DB_URL = os.getenv("DATABASE_URL", "postgresql://gigbid:gigbid@localhost:5432/gigbid").replace("+psycopg", "")
_pool: AsyncConnectionPool | None = None

SCHEMA = """
create table if not exists users (
  id text primary key, email text unique not null, password_hash text not null, name text,
  persona text, freelancer_id text, settings jsonb not null default '{}'::jsonb,
  created_at timestamptz default now());
create table if not exists oauth_tokens (
  user_id text references users(id) on delete cascade, provider text, ciphertext bytea,
  updated_at timestamptz default now(), primary key (user_id, provider));
create table if not exists jobs_seen (
  user_id text references users(id) on delete cascade, job_id text, content_hash text,
  title text, category text, posted jsonb, status text default 'queued', action text,
  fit_score real, risk_score real, is_scam boolean, flags jsonb, price real, connects_cost int,
  thread_id text, trace_id text, reasons jsonb, attention_reason text, tokens int, usd real, latency_s real,
  first_seen timestamptz default now(), updated_at timestamptz default now(),
  primary key (user_id, job_id));
create index if not exists jobs_seen_hash on jobs_seen(user_id, content_hash);
create table if not exists run_events (
  id bigserial primary key, user_id text, thread_id text, trace_id text, event jsonb, ts timestamptz default now());
create index if not exists run_events_thread on run_events(user_id, thread_id, id);
create table if not exists conversations (
  user_id text, thread_id text, job_id text, status text, intent text, last_client_msg text, graph_thread text,
  updated_at timestamptz default now(), primary key (user_id, thread_id));
create table if not exists pipeline (
  user_id text, proposal_id text, job_id text, title text, category text, status text, bid real,
  connects int, cover_letter text, events jsonb, updated_at timestamptz default now(), primary key (user_id, proposal_id));
create table if not exists rejections (
  id bigserial primary key, user_id text, job_id text, reason text, ts timestamptz default now());
"""


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(DB_URL, min_size=1, max_size=int(os.getenv("DB_POOL_MAX", "8")), open=False,
                                    kwargs={"autocommit": True, "row_factory": dict_row})
        await _pool.open()
        async with _pool.connection() as c:
            await c.execute(SCHEMA)
    return _pool


async def q(sql: str, *args: Any) -> list[dict]:
    p = await pool()
    async with p.connection() as c:
        cur = await c.execute(sql, args)
        try:
            return await cur.fetchall()
        except Exception:
            return []


async def q1(sql: str, *args: Any) -> dict | None:
    rows = await q(sql, *args)
    return rows[0] if rows else None


def j(x: Any) -> str:
    return json.dumps(x, default=str)


async def close():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
