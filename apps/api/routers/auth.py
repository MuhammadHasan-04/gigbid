"""Sign-in, onboarding, Upwork OAuth connect."""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from agent.graphs.bid_graph import persona_profile
from apps.api import db
from apps.api.auth.security import User, check_pw, create_user, make_token
from apps.api.auth.token_store import connected, put_token
from apps.api.schemas.models import LoginIn, OnboardIn, RegisterIn, SettingsModel, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def user_out(u: dict) -> UserOut:
    return UserOut(id=u["id"], email=u["email"], name=u.get("name"), persona=u.get("persona"),
                   freelancer_id=u.get("freelancer_id"), settings=SettingsModel(**u["settings"]),
                   upwork_connected=await connected(u["id"], "upwork"))


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn):
    if await db.q1("select 1 as x from users where email=%s", body.email.lower()):
        raise HTTPException(409, "email already registered")
    u = await create_user(body.email, body.password, body.name)
    return TokenOut(token=make_token(u["id"]), user=await user_out(u))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn):
    u = await db.q1("select * from users where email=%s", body.email.lower())
    if not u or not check_pw(body.password, u["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    return TokenOut(token=make_token(u["id"]), user=await user_out(u))


@router.get("/me", response_model=UserOut)
async def me(u: dict = User):
    return await user_out(u)


@router.post("/onboard", response_model=UserOut)
async def onboard(body: OnboardIn, u: dict = User):
    prof = persona_profile(body.persona)
    s = dict(u["settings"])
    s.update({"marketplace": body.marketplace, "hourly_floor": body.hourly_floor or prof["hourly_floor"],
              "weekly_connects_budget": body.weekly_connects_budget,
              "saved_searches": [{"id": "s1", "query": body.saved_search_query, "every_minutes": 30, "limit": 15}],
              "filters": {"min_budget": body.min_budget}})
    await db.q("update users set persona=%s, freelancer_id=%s, name=coalesce(nullif(name,''),%s), settings=%s where id=%s",
               body.persona, prof["freelancer_id"], prof["name"], db.j(s), u["id"])
    return await user_out(await db.q1("select * from users where id=%s", u["id"]))


# ---------------- Upwork OAuth 2.1 (authorization code + PKCE) ----------------
_pending: dict[str, dict] = {}


@router.get("/upwork/start")
async def upwork_start(u: dict = User):
    """Starts OAuth against the Upwork MCP authorization server. Requires UPWORK_CLIENT_ID."""
    import base64
    import hashlib
    cid = os.getenv("UPWORK_CLIENT_ID")
    if not cid:
        raise HTTPException(501, "Upwork live mode is not configured on this deployment (UPWORK_CLIENT_ID missing)")
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _pending[state] = {"user": u["id"], "verifier": verifier}
    auth_url = os.getenv("UPWORK_AUTH_URL", "https://www.upwork.com/ab/account-security/oauth2/authorize")
    redirect = os.getenv("UPWORK_REDIRECT_URI", "http://localhost:8000/api/auth/upwork/callback")
    return {"url": f"{auth_url}?response_type=code&client_id={cid}&redirect_uri={redirect}&state={state}"
                   f"&code_challenge={challenge}&code_challenge_method=S256"}


@router.get("/upwork/callback")
async def upwork_callback(code: str, state: str):
    import httpx
    p = _pending.pop(state, None)
    if not p:
        raise HTTPException(400, "unknown OAuth state")
    token_url = os.getenv("UPWORK_TOKEN_URL", "https://www.upwork.com/api/v3/oauth2/token")
    async with httpx.AsyncClient() as c:
        r = await c.post(token_url, data={"grant_type": "authorization_code", "code": code, "code_verifier": p["verifier"],
                                          "client_id": os.getenv("UPWORK_CLIENT_ID"), "client_secret": os.getenv("UPWORK_CLIENT_SECRET", ""),
                                          "redirect_uri": os.getenv("UPWORK_REDIRECT_URI", "")})
    if r.status_code != 200:
        raise HTTPException(502, "token exchange failed")
    await put_token(p["user"], "upwork", r.json())  # encrypted at rest, never logged
    return RedirectResponse(os.getenv("WEB_URL", "/") + "settings?upwork=connected")
