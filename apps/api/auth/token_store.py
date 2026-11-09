"""Encrypted per-user OAuth token store (Fernet). Tokens are never logged or returned to the UI."""
from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet

from apps.api import db


def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENC_KEY")
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256((os.getenv("APP_SECRET_KEY", "dev") + "|tokens").encode()).digest()).decode()
    return Fernet(key)


async def put_token(user_id: str, provider: str, token: dict):
    ct = _fernet().encrypt(json.dumps(token).encode())
    await db.q("insert into oauth_tokens (user_id, provider, ciphertext) values (%s,%s,%s) "
               "on conflict (user_id, provider) do update set ciphertext=excluded.ciphertext, updated_at=now()",
               user_id, provider, ct)


async def get_token_async(user_id: str, provider: str) -> dict | None:
    row = await db.q1("select ciphertext from oauth_tokens where user_id=%s and provider=%s", user_id, provider)
    if not row:
        return None
    return json.loads(_fernet().decrypt(bytes(row["ciphertext"])).decode())


def get_token(user_id: str, provider: str) -> str | None:
    import asyncio
    try:
        tok = asyncio.run(get_token_async(user_id, provider))
    except RuntimeError:
        return None
    return (tok or {}).get("access_token")


async def connected(user_id: str, provider: str) -> bool:
    return bool(await db.q1("select 1 as x from oauth_tokens where user_id=%s and provider=%s", user_id, provider))
