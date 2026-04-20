"""Browser SSO session helpers for SigAuth authorize flow."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import Request, Response

from app.config import settings


BROWSER_SESSION_COOKIE_NAME = "sigauth_sso"
BROWSER_SESSION_KEY_PREFIX = "browser_session"
BROWSER_SESSION_USER_SET_PREFIX = "browser_sessions"


def _browser_session_key(session_id: str) -> str:
    return f"{BROWSER_SESSION_KEY_PREFIX}:{session_id}"


def _browser_session_user_key(user_id: str) -> str:
    return f"{BROWSER_SESSION_USER_SET_PREFIX}:{user_id}"


def read_browser_session_id(request: Request) -> Optional[str]:
    return request.cookies.get(BROWSER_SESSION_COOKIE_NAME)


def _cookie_secure() -> bool:
    return settings.ISSUER_URL.startswith("https://")


def attach_browser_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=BROWSER_SESSION_COOKIE_NAME,
        value=session_id,
        max_age=settings.BROWSER_SSO_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_browser_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=BROWSER_SESSION_COOKIE_NAME,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


async def create_browser_session(
    redis: aioredis.Redis,
    *,
    user_id: str,
    org_id: str,
    email: str,
    client_id: str = "admin-console",
    token_jti: str = "",
    user_agent: str = "",
    ip_address: str = "",
) -> str:
    session_id = secrets.token_urlsafe(32)
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "org_id": org_id,
        "email": email,
        "client_id": client_id,
        "jti": token_jti,
        "user_agent": user_agent,
        "ip_address": ip_address,
        "created_at": now_iso,
        "last_seen_at": now_iso,
    }

    await redis.set(_browser_session_key(session_id), json.dumps(payload), ex=settings.BROWSER_SSO_TTL_SECONDS)
    await redis.sadd(_browser_session_user_key(user_id), session_id)
    await redis.expire(_browser_session_user_key(user_id), settings.BROWSER_SSO_TTL_SECONDS)
    return session_id


async def get_browser_session(redis: aioredis.Redis, session_id: str | None) -> Optional[dict[str, Any]]:
    if not session_id:
        return None

    payload = await redis.get(_browser_session_key(session_id))
    if not payload:
        return None

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        await redis.delete(_browser_session_key(session_id))
        return None


async def touch_browser_session(redis: aioredis.Redis, session_id: str, payload: dict[str, Any]) -> None:
    if not session_id or not payload:
        return

    next_payload = dict(payload)
    next_payload["last_seen_at"] = datetime.now(timezone.utc).isoformat()
    await redis.set(_browser_session_key(session_id), json.dumps(next_payload), ex=settings.BROWSER_SSO_TTL_SECONDS)
    user_id = str(next_payload.get("user_id") or "")
    if user_id:
        await redis.expire(_browser_session_user_key(user_id), settings.BROWSER_SSO_TTL_SECONDS)


async def revoke_browser_session(redis: aioredis.Redis, session_id: str | None) -> int:
    if not session_id:
        return 0

    payload = await get_browser_session(redis, session_id)
    deleted = int(await redis.delete(_browser_session_key(session_id)) or 0)
    if payload and payload.get("user_id"):
        await redis.srem(_browser_session_user_key(str(payload["user_id"])), session_id)
    return deleted


async def revoke_all_browser_sessions_for_user(redis: aioredis.Redis, user_id: str) -> int:
    user_key = _browser_session_user_key(user_id)
    session_ids = await redis.smembers(user_key)
    deleted = 0

    for raw_session_id in session_ids or []:
        session_id = raw_session_id.decode("utf-8") if isinstance(raw_session_id, bytes) else str(raw_session_id)
        deleted += int(await redis.delete(_browser_session_key(session_id)) or 0)
        await redis.srem(user_key, session_id)

    await redis.delete(user_key)
    return deleted
