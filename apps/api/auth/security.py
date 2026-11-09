"""Users, passwords (bcrypt), sessions (JWT bearer)."""
from __future__ import annotations

import os
import time
import uuid

import bcrypt
from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt

from apps.api import db

SECRET = os.getenv("APP_SECRET_KEY", "dev-secret-change-me")
ALGO = "HS256"
TTL = 60 * 60 * 24 * 7


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def make_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": int(time.time()) + TTL}, SECRET, algorithm=ALGO)


async def create_user(email: str, password: str, name: str = "", persona: str | None = None) -> dict:
    uid = "u-" + uuid.uuid4().hex[:10]
    await db.q("insert into users (id, email, password_hash, name, persona, freelancer_id, settings) values (%s,%s,%s,%s,%s,%s,%s)",
               uid, email.lower(), hash_pw(password), name, persona, None, db.j(default_settings()))
    return await db.q1("select * from users where id=%s", uid)


def default_settings() -> dict:
    return {"autonomy": "suggest", "hourly_floor": None, "weekly_connects_budget": 80, "marketplace": "gigsim",
            "saved_searches": [{"id": "s1", "query": "", "every_minutes": 30}], "filters": {"min_budget": 0}}


async def current_user(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    tok = auth.removeprefix("Bearer ").strip() or request.query_params.get("token", "")
    if not tok:
        raise HTTPException(401, "not signed in")
    try:
        sub = jwt.decode(tok, SECRET, algorithms=[ALGO])["sub"]
    except JWTError:
        raise HTTPException(401, "invalid session")
    u = await db.q1("select * from users where id=%s", sub)
    if not u:
        raise HTTPException(401, "unknown user")
    return u


User = Depends(current_user)
