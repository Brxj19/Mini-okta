"""FastAPI dependencies: auth/session helpers and permission enforcement."""

from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.redis_client import get_redis_pool
from app.utils.jwt_utils import verify_token
from app.services.browser_session_service import get_browser_session, read_browser_session_id, revoke_browser_session, touch_browser_session
from app.services.token_service import get_token_by_jti
from app.services.user_service import get_user, resolve_rbac
from app.services.organization_service import get_organization, is_org_limited

security = HTTPBearer(auto_error=False)

LIMITED_ORG_BLOCKED_PERMISSIONS = {
    "org:update",
    "user:delete",
    "user:reset_password",
    "app:update",
    "app:delete",
    "app:group:assign",
    "app:group:update",
    "group:create",
    "group:update",
    "group:delete",
    "group:member:add",
    "group:member:remove",
    "group:role:assign",
    "group:role:update",
    "role:create",
    "role:update",
}


async def get_db():
    """Provide an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis() -> aioredis.Redis:
    """Provide a Redis connection."""
    return await get_redis_pool()


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Extract and verify the current user from the Bearer token.
    
    Returns dict with: user_id, email, org_id, is_super_admin, roles, permissions, jti, claims
    """
    claims = {}
    jti = None
    user_id = None
    cookie_session_id = None

    if credentials:
        token = credentials.credentials
        try:
            claims = verify_token(token)
        except JWTError as e:
            raise HTTPException(status_code=401, detail={"error": "invalid_token", "error_description": f"Invalid token: {str(e)}"})

        jti = claims.get("jti")
        if jti:
            token_record = await get_token_by_jti(db, jti)
            if token_record and token_record.revoked:
                raise HTTPException(status_code=401, detail={"error": "token_revoked", "error_description": "Token has been revoked"})

        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail={"error": "invalid_token", "error_description": "Token missing sub claim"})
    else:
        cookie_session_id = read_browser_session_id(request)
        browser_session = await get_browser_session(redis, cookie_session_id)
        if not browser_session:
            raise HTTPException(status_code=401, detail={"error": "unauthorized", "error_description": "Missing authorization"})

        user_id = browser_session.get("user_id")
        if not user_id:
            await revoke_browser_session(redis, cookie_session_id)
            raise HTTPException(status_code=401, detail={"error": "invalid_session", "error_description": "Session is invalid"})
        jti = browser_session.get("jti") or None
        claims = {
            "sub": user_id,
            "email": browser_session.get("email", ""),
            "org_id": browser_session.get("org_id", ""),
            "aud": browser_session.get("client_id", "admin-console"),
        }

    user = await get_user(db, UUID(user_id))
    if not user:
        raise HTTPException(status_code=401, detail={"error": "user_not_found", "error_description": "User not found"})

    if user.status != "active":
        if cookie_session_id:
            await revoke_browser_session(redis, cookie_session_id)
        raise HTTPException(status_code=403, detail={"error": "account_inactive", "error_description": f"Account is {user.status}"})

    if cookie_session_id:
        browser_session["user_id"] = str(user.id)
        browser_session["org_id"] = str(user.org_id)
        browser_session["email"] = user.email
        browser_session["client_id"] = claims.get("aud", "admin-console")
        browser_session["jti"] = jti or ""
        browser_session["user_agent"] = request.headers.get("user-agent", "")
        browser_session["ip_address"] = request.client.host if request.client else ""
        await touch_browser_session(redis, cookie_session_id, browser_session)

    return {
        "user_id": UUID(user_id),
        "email": claims.get("email", "") or user.email,
        "org_id": UUID(str(claims.get("org_id") or user.org_id)),
        "is_super_admin": bool(claims.get("is_super_admin", False) or getattr(user, "is_super_admin", False)),
        "roles": claims.get("roles", []),
        "permissions": claims.get("permissions", []),
        "jti": jti,
        "claims": claims,
        "user": user,
    }


def require_permission(*required_permissions: str):
    """Dependency factory: require the current user to have ALL specified permissions."""
    async def checker(
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        request_org_id_raw = request.path_params.get("org_id")
        request_org_id = UUID(request_org_id_raw) if request_org_id_raw else None

        if request_org_id and not current_user["is_super_admin"] and request_org_id != current_user["org_id"]:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "cross_tenant_forbidden",
                    "error_description": "You do not have access to this organization",
                },
            )

        if current_user["is_super_admin"]:
            current_user["roles"] = ["super_admin"]
            current_user["permissions"] = ["*"]
            current_user["effective_org_id"] = request_org_id or current_user["org_id"]
            return current_user

        effective_org_id = request_org_id or current_user["org_id"]
        roles, permissions = await resolve_rbac(db, current_user["user_id"], effective_org_id)

        org = await get_organization(db, effective_org_id)
        if org and is_org_limited(org.settings):
            blocked = [perm for perm in required_permissions if perm in LIMITED_ORG_BLOCKED_PERMISSIONS]
            if blocked:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "organization_verification_required",
                        "error_description": "This organization is on the free self-serve tier. Upgrade to a paid plan to unlock this capability.",
                    },
                )

        for perm in required_permissions:
            if perm not in permissions:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "insufficient_permissions",
                        "error_description": f"Missing required permission: {perm}",
                    },
                )
        current_user["roles"] = roles
        current_user["permissions"] = permissions
        current_user["effective_org_id"] = effective_org_id
        return current_user
    return checker


async def require_super_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Allow access only to platform-level administrators."""
    if not current_user["is_super_admin"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "super_admin_required",
                "error_description": "This action requires a super admin account",
            },
        )
    current_user["roles"] = ["super_admin"]
    current_user["permissions"] = ["*"]
    current_user["effective_org_id"] = current_user["org_id"]
    return current_user
