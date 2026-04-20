"""Sessions router: GET /me/sessions, DELETE /me/sessions/:jti."""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_redis, get_current_user
from app.services.session_service import list_provider_sessions, revoke_provider_session

router = APIRouter(prefix="/api/v1/me/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """List all active sessions for the current user."""
    user_id = str(current_user["user_id"])
    current_jti = str(current_user.get("jti") or "")
    sessions = await list_provider_sessions(redis=redis, user_id=user_id, current_jti=current_jti)
    return {"data": [s.model_dump() for s in sessions]}


@router.delete("/{jti}")
async def revoke_session(
    jti: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Revoke a specific session. Verify ownership."""
    sessions = await list_provider_sessions(
        redis=redis,
        user_id=str(current_user["user_id"]),
        current_jti=str(current_user.get("jti") or ""),
    )
    if not any(session.jti == jti for session in sessions):
        raise HTTPException(403, detail={"error": "forbidden", "error_description": "Session does not belong to you"})

    await revoke_provider_session(db=db, redis=redis, jti=jti, reason="session_revoked")

    return {"message": "Session revoked"}
