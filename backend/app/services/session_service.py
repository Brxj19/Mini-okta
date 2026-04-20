"""Provider session registry helpers for Redis-backed active sessions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.token import SessionResponse
from app.services.token_service import revoke_token

SESSION_KEY_PREFIX = "session"
SESSION_DEVICE_KEY_PREFIX = "session_device"


def _session_key(jti: str) -> str:
    return f"{SESSION_KEY_PREFIX}:{jti}"


def _browser_fingerprint(client_id: str, user_agent: str) -> str:
    source = f"{client_id or 'unknown'}|{user_agent or 'unknown'}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _device_key(user_id: str, client_id: str, fingerprint: str) -> str:
    return f"{SESSION_DEVICE_KEY_PREFIX}:{user_id}:{client_id or 'unknown'}:{fingerprint}"


def _decode_session_payload(raw_value: Any) -> Optional[dict[str, Any]]:
    if not raw_value:
        return None
    try:
        value = raw_value.decode("utf-8") if isinstance(raw_value, bytes) else str(raw_value)
        return json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


async def register_provider_session(
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    jti: str,
    user_id: str,
    client_id: str,
    ip_address: str = "",
    user_agent: str = "",
    expires_in: int,
    created_at: Optional[datetime] = None,
) -> None:
    """Register one active provider session and replace prior same-browser session for the same client."""
    created = created_at or datetime.now(timezone.utc)
    fingerprint = _browser_fingerprint(client_id, user_agent)
    device_key = _device_key(user_id, client_id, fingerprint)
    previous_jti = await redis.get(device_key)
    if previous_jti:
        previous_jti_value = previous_jti.decode("utf-8") if isinstance(previous_jti, bytes) else str(previous_jti)
        if previous_jti_value and previous_jti_value != jti:
            await revoke_provider_session(
                db=db,
                redis=redis,
                jti=previous_jti_value,
                reason="session_replaced",
            )

    payload = {
        "jti": jti,
        "user_id": user_id,
        "client_id": client_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "browser_fingerprint": fingerprint,
        "created_at": created.isoformat(),
    }
    await redis.set(_session_key(jti), json.dumps(payload), ex=expires_in)
    await redis.set(device_key, jti, ex=expires_in)


async def revoke_provider_session(
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    jti: str,
    reason: str = "session_revoked",
) -> bool:
    """Revoke one provider session and clear its Redis indexes."""
    payload = _decode_session_payload(await redis.get(_session_key(jti)))

    revoked = False
    if hasattr(db, "execute"):
        revoked = await revoke_token(db, jti, reason=reason)
    await redis.delete(_session_key(jti))

    if payload:
        user_id = str(payload.get("user_id") or "")
        client_id = str(payload.get("client_id") or "")
        fingerprint = str(payload.get("browser_fingerprint") or _browser_fingerprint(client_id, str(payload.get("user_agent") or "")))
        device_key = _device_key(user_id, client_id, fingerprint)
        mapped_jti = await redis.get(device_key)
        mapped_jti_value = mapped_jti.decode("utf-8") if isinstance(mapped_jti, bytes) else (str(mapped_jti) if mapped_jti else "")
        if mapped_jti_value == jti:
            await redis.delete(device_key)

    return revoked or payload is not None


async def list_provider_sessions(
    *,
    redis: aioredis.Redis,
    user_id: str,
    current_jti: Optional[str] = None,
) -> list[SessionResponse]:
    """List deduplicated active provider sessions for a user."""
    newest_by_device: dict[str, dict[str, Any]] = {}

    async for key in redis.scan_iter(match=f"{SESSION_KEY_PREFIX}:*"):
        payload = _decode_session_payload(await redis.get(key))
        if not payload or str(payload.get("user_id") or "") != user_id:
            continue

        client_id = str(payload.get("client_id") or "")
        fingerprint = str(payload.get("browser_fingerprint") or _browser_fingerprint(client_id, str(payload.get("user_agent") or "")))
        dedupe_key = f"{client_id}:{fingerprint}"
        existing = newest_by_device.get(dedupe_key)
        created_at = str(payload.get("created_at") or "")

        if not existing or created_at > str(existing.get("created_at") or ""):
            newest_by_device[dedupe_key] = payload

    sessions = [
        SessionResponse(
            jti=str(payload.get("jti") or ""),
            user_id=str(payload.get("user_id") or ""),
            client_id=str(payload.get("client_id") or ""),
            ip_address=payload.get("ip_address"),
            user_agent=payload.get("user_agent"),
            created_at=payload.get("created_at"),
            current=bool(current_jti and str(payload.get("jti") or "") == str(current_jti)),
        )
        for payload in newest_by_device.values()
    ]
    sessions.sort(key=lambda session: session.created_at or "", reverse=True)
    return sessions
