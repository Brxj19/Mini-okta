"""Users router: full user CRUD + suspend + reset-password + revoke-sessions."""

from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select, func

from app.branding import PRODUCT_NAME
from app.dependencies import get_db, get_redis, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserDetailResponse, UserListResponse
from app.services.user_service import (
    create_user, get_user, get_user_detail, list_users,
    resolve_rbac, update_user, suspend_user, unlock_user, soft_delete_user,
)
from app.services.token_service import revoke_all_user_tokens, get_user_token_jtis
from app.services.browser_session_service import revoke_all_browser_sessions_for_user
from app.services.audit_service import write_audit_event
from app.services.email_service import send_password_reset_email, send_invitation_email
from app.services.notification_service import (
    SUPPORTED_NOTIFICATION_EVENTS,
    is_notification_enabled,
    set_notification_preference,
    send_admin_activity_notification,
    send_notification_event,
)
from app.services.session_service import revoke_provider_session
from app.utils.crypto_utils import generate_reset_token
from app.models.password_reset import PasswordResetToken
from app.config import settings
from datetime import datetime, timedelta, timezone
from app.services.organization_service import get_org_limits, is_org_limited
from app.services.group_service import get_group, get_group_roles

router = APIRouter(prefix="/api/v1/organizations/{org_id}/users", tags=["users"])

PROTECTED_ROLE_NAMES = {"org:admin", "super_admin"}


def _can_manage_protected_accounts(current_user: dict) -> bool:
    return bool(current_user.get("is_super_admin") or "org:admin" in (current_user.get("roles") or []))


async def _get_org_user_or_404(db: AsyncSession, org_id: UUID, user_id: UUID) -> User:
    user = await get_user(db, user_id)
    if not user or user.org_id != org_id:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "User not found"})
    return user


async def _group_has_protected_role(db: AsyncSession, group_id: UUID) -> bool:
    group_roles = await get_group_roles(db, group_id)
    return any(role.name in PROTECTED_ROLE_NAMES for role in group_roles)


async def _ensure_group_assignments_allowed(
    db: AsyncSession,
    org_id: UUID,
    group_ids: list[UUID] | None,
    current_user: dict,
) -> None:
    if not group_ids:
        return

    if not current_user.get("is_super_admin") and "group:member:add" not in (current_user.get("permissions") or []):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_permissions",
                "error_description": "Adding a user to groups requires group membership management permission.",
            },
        )

    for group_id in group_ids:
        group = await get_group(db, group_id)
        if not group or group.org_id != org_id:
            raise HTTPException(404, detail={"error": "not_found", "error_description": "Group not found"})
        if await _group_has_protected_role(db, group_id) and not _can_manage_protected_accounts(current_user):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "protected_group_forbidden",
                    "error_description": "Only organization admins can assign users into protected admin groups.",
                },
            )


async def _ensure_target_user_manageable(
    db: AsyncSession,
    current_user: dict,
    target_user: User,
) -> None:
    if target_user.id == current_user["user_id"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "self_management_forbidden",
                "error_description": "You cannot perform this administrative action on your own account.",
            },
        )

    if target_user.is_super_admin and not current_user.get("is_super_admin"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "protected_user_forbidden",
                "error_description": "Only a super admin can manage another super admin account.",
            },
        )

    target_roles, _ = await resolve_rbac(db, target_user.id, target_user.org_id)
    target_has_protected_access = bool(target_user.is_super_admin or any(role in PROTECTED_ROLE_NAMES for role in target_roles))
    if target_has_protected_access and not _can_manage_protected_accounts(current_user):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "protected_user_forbidden",
                "error_description": "Only organization admins can manage administrator accounts.",
            },
        )


async def invalidate_active_reset_tokens(db: AsyncSession, user_id: UUID) -> None:
    """Expire any outstanding password reset tokens for the user."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.purpose == "reset",
            PasswordResetToken.used.is_(False),
            PasswordResetToken.expires_at > now,
        )
        .values(expires_at=now)
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user_endpoint(
    org_id: UUID,
    body: UserCreate,
    current_user: dict = Depends(require_permission("user:create")),
    db: AsyncSession = Depends(get_db),
):
    """Create a user and send onboarding invitation email."""
    await _ensure_group_assignments_allowed(db, org_id, body.group_ids, current_user)

    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if org and is_org_limited(org.settings):
        limits = get_org_limits(org.settings)
        max_users = limits.get("max_users")
        if max_users:
            current_users_result = await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.org_id == org_id, User.deleted_at.is_(None))
            )
            current_users = current_users_result.scalar() or 0
            if current_users >= max_users:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "self_serve_limit_reached",
                        "error_description": f"Self-serve organizations can have up to {max_users} users until verified by a super admin.",
                    },
                )

    try:
        user = await create_user(db, org_id, body.email, body.password, body.first_name, body.last_name)
    except ValueError as e:
        raise HTTPException(400, detail={"error": "invalid_password", "error_description": str(e)})

    setup_token = generate_reset_token()
    token_record = PasswordResetToken(
        token=setup_token,
        user_id=user.id,
        purpose="onboarding",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_SETUP_TOKEN_TTL_HOURS),
    )
    db.add(token_record)
    await db.flush()
    await send_invitation_email(db, user.email, setup_token, org_id=user.org_id, user_id=user.id)

    # Add to groups if specified
    if body.group_ids:
        from app.services.group_service import add_members
        for gid in body.group_ids:
            await add_members(db, gid, [user.id])

    await write_audit_event(
        db, "user.created", "user", str(user.id),
        org_id=org_id, actor_id=current_user["user_id"],
        metadata={
            "actor_id": str(current_user["user_id"]),
            "new_user_id": str(user.id),
            "onboarding_expires_at": token_record.expires_at.isoformat(),
        }
    )
    await send_notification_event(
        db=db,
        user=user,
        event_key="account.created",
        title=f"Welcome to {PRODUCT_NAME}",
        message="An administrator created your account. Complete setup using the invitation link sent to your email.",
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="User created",
        message=f"{current_user.get('email', 'An admin')} created user {user.email}.",
    )

    return UserResponse.model_validate(user)


@router.get("", response_model=UserListResponse)
async def list_users_endpoint(
    org_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    sort: str = Query("created_at:desc"),
    filter_status: Optional[str] = Query(None, alias="filter[status]"),
    filter_email: Optional[str] = Query(None, alias="filter[email_contains]"),
    current_user: dict = Depends(require_permission("user:read")),
    db: AsyncSession = Depends(get_db),
):
    """List users with cursor-based pagination and filters."""
    result = await list_users(db, org_id, limit, cursor, filter_status, filter_email, sort)
    return UserListResponse(
        data=[UserResponse.model_validate(u) for u in result["data"]],
        pagination=result["pagination"],
    )


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user_endpoint(
    org_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(require_permission("user:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get user detail with group memberships and effective roles."""
    detail = await get_user_detail(db, user_id)
    if not detail or detail["user"].org_id != org_id:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "User not found"})

    user = detail["user"]
    return UserDetailResponse(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        profile_image_url=user.profile_image_url,
        status=user.status,
        email_verified=user.email_verified,
        mfa_enabled=user.mfa_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
        groups=detail["groups"],
        roles=detail["roles"],
        permissions=detail["permissions"],
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_endpoint(
    org_id: UUID,
    user_id: UUID,
    body: UserUpdate,
    current_user: dict = Depends(require_permission("user:update")),
    db: AsyncSession = Depends(get_db),
):
    """Update user first_name, last_name."""
    target_user = await _get_org_user_or_404(db, org_id, user_id)
    await _ensure_target_user_manageable(db, current_user, target_user)
    user = await update_user(db, user_id, body.first_name, body.last_name)
    return UserResponse.model_validate(user)


@router.post("/{user_id}/suspend")
async def suspend_user_endpoint(
    org_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(require_permission("user:update")),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Suspend a user and revoke all their tokens."""
    await _ensure_target_user_manageable(db, current_user, await _get_org_user_or_404(db, org_id, user_id))
    user = await suspend_user(db, user_id)

    # Revoke tokens
    jtis = await get_user_token_jtis(db, user_id)
    await revoke_all_user_tokens(db, user_id, reason="user_suspended")
    await revoke_all_browser_sessions_for_user(redis, str(user_id))
    for jti in jtis:
        await revoke_provider_session(db=db, redis=redis, jti=jti, reason="user_suspended")

    await write_audit_event(
        db, "user.suspended", "user", str(user_id),
        org_id=org_id, actor_id=current_user["user_id"],
        metadata={"actor_id": str(current_user["user_id"]), "reason": "admin_action"}
    )
    await send_notification_event(
        db=db,
        user=user,
        event_key="account.suspended",
        title="Your account was suspended",
        message="An administrator suspended your account. Contact your organization administrator for assistance.",
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="User suspended",
        message=f"{current_user.get('email', 'An admin')} suspended user {user.email}.",
    )

    return UserResponse.model_validate(user)


@router.post("/{user_id}/unlock")
async def unlock_user_endpoint(
    org_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(require_permission("user:update")),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Unlock or reactivate a user account and notify the user."""
    await _ensure_target_user_manageable(db, current_user, await _get_org_user_or_404(db, org_id, user_id))
    user = await unlock_user(db, user_id)

    await redis.delete(f"login_fail:{user.id}")
    await write_audit_event(
        db, "user.unlocked", "user", str(user_id),
        org_id=org_id, actor_id=current_user["user_id"],
        metadata={"actor_id": str(current_user["user_id"])}
    )
    await send_notification_event(
        db=db,
        user=user,
        event_key="account.unlocked",
        title="Your account was unlocked",
        message="An administrator unlocked your account. You can sign in again.",
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="User unlocked",
        message=f"{current_user.get('email', 'An admin')} unlocked user {user.email}.",
    )
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reset-password")
async def reset_password_endpoint(
    org_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(require_permission("user:reset_password")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger password reset email for a user."""
    user = await _get_org_user_or_404(db, org_id, user_id)
    await _ensure_target_user_manageable(db, current_user, user)

    await invalidate_active_reset_tokens(db, user.id)
    reset_token = generate_reset_token()
    token_record = PasswordResetToken(
        token=reset_token,
        user_id=user.id,
        purpose="reset",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(token_record)
    await db.flush()
    await send_password_reset_email(db, user.email, reset_token, org_id=user.org_id, user_id=user.id)
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Password reset initiated",
        message=f"{current_user.get('email', 'An admin')} sent a password reset link to {user.email}.",
    )

    return {"message": "Password reset email sent"}


@router.delete("/{user_id}")
async def delete_user_endpoint(
    org_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(require_permission("user:delete")),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Soft delete a user and revoke all tokens."""
    user = await _get_org_user_or_404(db, org_id, user_id)
    await _ensure_target_user_manageable(db, current_user, user)

    jtis = await get_user_token_jtis(db, user_id)
    await revoke_all_user_tokens(db, user_id, reason="user_deleted")
    await revoke_all_browser_sessions_for_user(redis, str(user_id))
    for jti in jtis:
        await revoke_provider_session(db=db, redis=redis, jti=jti, reason="user_deleted")

    await soft_delete_user(db, user_id)
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="User deleted",
        message=f"{current_user.get('email', 'An admin')} deleted user {user.email}.",
    )
    return {"message": "User deleted"}


@router.post("/{user_id}/revoke-sessions")
async def revoke_sessions_endpoint(
    org_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(require_permission("user:update")),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Revoke all tokens and clear all sessions for a user."""
    user = await _get_org_user_or_404(db, org_id, user_id)
    await _ensure_target_user_manageable(db, current_user, user)

    jtis = await get_user_token_jtis(db, user_id)
    await revoke_all_user_tokens(db, user_id, reason="sessions_revoked")
    await revoke_all_browser_sessions_for_user(redis, str(user_id))
    for jti in jtis:
        await revoke_provider_session(db=db, redis=redis, jti=jti, reason="sessions_revoked")

    return {"message": f"Revoked {len(jtis)} sessions"}


@router.get("/{user_id}/notification-preferences")
async def get_notification_preferences_endpoint(
    org_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(require_permission("user:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get effective notification preferences for a user."""
    user = await get_user(db, user_id)
    if not user or user.org_id != org_id:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "User not found"})

    preferences = []
    for event_key in sorted(SUPPORTED_NOTIFICATION_EVENTS):
        enabled = await is_notification_enabled(db, user.id, event_key)
        preferences.append({"event_key": event_key, "enabled": enabled})
    return {"user_id": str(user.id), "preferences": preferences}


@router.put("/{user_id}/notification-preferences")
async def update_notification_preferences_endpoint(
    org_id: UUID,
    user_id: UUID,
    body: dict,
    current_user: dict = Depends(require_permission("user:update")),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences for a user."""
    user = await get_user(db, user_id)
    if not user or user.org_id != org_id:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "User not found"})

    updates = body.get("preferences", [])
    if not isinstance(updates, list):
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": "preferences must be a list"})

    normalized = []
    for item in updates:
        event_key = item.get("event_key")
        enabled = item.get("enabled")
        if event_key not in SUPPORTED_NOTIFICATION_EVENTS or not isinstance(enabled, bool):
            raise HTTPException(400, detail={"error": "invalid_request", "error_description": "Invalid preference payload"})
        pref = await set_notification_preference(db, user.id, event_key, enabled)
        normalized.append({"event_key": pref.event_key, "enabled": pref.enabled})

    await write_audit_event(
        db, "user.notification_preferences.updated", "user", str(user_id),
        org_id=org_id, actor_id=current_user["user_id"],
        metadata={"user_id": str(user_id), "updated": normalized}
    )
    return {"user_id": str(user.id), "preferences": normalized}
