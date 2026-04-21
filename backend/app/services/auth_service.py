"""Auth service: login logic, lockout, RBAC resolution, token issuance."""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services.session_service import register_provider_session
from app.services.user_service import get_user_by_email, resolve_rbac, get_user_groups
from app.services.application_service import (
    get_application_by_client_id,
    list_application_groups,
    list_application_role_mappings,
)
from app.services.organization_service import get_organization
from app.services.token_service import issue_id_token, issue_access_token, issue_refresh_token
from app.services.audit_service import write_audit_event
from app.services.notification_service import send_admin_activity_notification, send_notification_event
from app.utils.crypto_utils import verify_password

MAX_LOGIN_FAILURES = 5
LOCKOUT_TTL = 900  # 15 minutes


def derive_app_roles(
    global_roles: list[str],
    app_groups: list[str],
    role_mappings: Optional[list[dict[str, str]]] = None,
) -> list[str]:
    """Derive app-scoped roles from explicit application role mappings only."""
    normalized_global_roles = {str(role).lower() for role in (global_roles or [])}
    normalized_groups = {str(group).lower() for group in (app_groups or [])}

    configured_mappings = role_mappings or []
    mapped_roles: set[str] = set()
    for mapping in configured_mappings:
        source_type = str(mapping.get("source_type", "")).lower()
        source_value = str(mapping.get("source_value", "")).lower()
        app_role = str(mapping.get("app_role", "")).lower().strip()
        if not source_value or not app_role:
            continue
        if source_type == "group" and source_value in normalized_groups:
            mapped_roles.add(app_role)
        if source_type == "role" and source_value in normalized_global_roles:
            mapped_roles.add(app_role)
    return sorted(mapped_roles)


def _is_app_admin(user: User, global_roles: list[str]) -> bool:
    normalized_roles = {str(role).lower() for role in (global_roles or [])}
    return bool(user.is_super_admin or "org:admin" in normalized_roles or "super_admin" in normalized_roles)


async def resolve_application_access(
    db: AsyncSession,
    user: User,
    client_id: str,
    global_roles: list[str],
    user_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve app assignment and app roles for a user against a client application.

    Rules:
    - super admins and org admins may access any application in their organization
    - regular users must belong to at least one group assigned to the application
    - app role derivation is explicit only
    - applications that require explicit role mappings will block sign-in until one mapping matches
    """
    app_group_assignments: list[dict[str, Any]] = []
    role_mappings: list[dict[str, str]] = []
    app = await get_application_by_client_id(db, client_id)

    if app:
        assigned_groups = await list_application_groups(db, app.id)
        app_group_assignments = [
            {"id": group.id, "name": group.name, "description": group.description}
            for group in assigned_groups
        ]
        configured_mappings = await list_application_role_mappings(db, app.id)
        role_mappings = [
            {
                "source_type": mapping.source_type,
                "source_value": mapping.source_value,
                "app_role": mapping.app_role,
            }
            for mapping in configured_mappings
        ]

    user_group_ids = {str(group["id"]) for group in user_groups}
    authorized_app_groups = [
        group for group in app_group_assignments
        if str(group["id"]) in user_group_ids
    ]
    app_roles = derive_app_roles(
        global_roles,
        [group["name"] for group in authorized_app_groups],
        role_mappings,
    )

    is_admin = _is_app_admin(user, global_roles)
    if is_admin:
        return {
            "app": app,
            "app_group_assignments": app_group_assignments,
            "authorized_app_groups": authorized_app_groups,
            "role_mappings": role_mappings,
            "app_roles": app_roles,
            "access_allowed": True,
            "access_error": None,
            "admin_bypass": True,
        }

    if not app_group_assignments:
        return {
            "app": app,
            "app_group_assignments": app_group_assignments,
            "authorized_app_groups": authorized_app_groups,
            "role_mappings": role_mappings,
            "app_roles": app_roles,
            "access_allowed": False,
            "access_error": "This application is not assigned to any groups yet. Ask your organization admin to configure access.",
            "admin_bypass": False,
        }

    if not authorized_app_groups:
        return {
            "app": app,
            "app_group_assignments": app_group_assignments,
            "authorized_app_groups": authorized_app_groups,
            "role_mappings": role_mappings,
            "app_roles": app_roles,
            "access_allowed": False,
            "access_error": "You are not assigned to any groups authorized for this application",
            "admin_bypass": False,
        }

    if bool(app and getattr(app, "require_explicit_role_mappings", False)) and not app_roles:
        return {
            "app": app,
            "app_group_assignments": app_group_assignments,
            "authorized_app_groups": authorized_app_groups,
            "role_mappings": role_mappings,
            "app_roles": app_roles,
            "access_allowed": False,
            "access_error": "This application requires explicit app role mappings. Ask your organization admin to configure a matching application role mapping for your assigned group or role.",
            "admin_bypass": False,
        }

    return {
        "app": app,
        "app_group_assignments": app_group_assignments,
        "authorized_app_groups": authorized_app_groups,
        "role_mappings": role_mappings,
        "app_roles": app_roles,
        "access_allowed": True,
        "access_error": None,
        "admin_bypass": False,
    }


async def login(
    db: AsyncSession,
    redis: aioredis.Redis,
    email: str,
    password: str,
    ip_address: str = "",
    user_agent: str = "",
    client_id: str = "admin-console",
) -> dict[str, Any]:
    """Authenticate user and return tokens."""
    user = await authenticate_primary_credentials(
        db=db,
        redis=redis,
        email=email,
        password=password,
        ip_address=ip_address,
        user_agent=user_agent,
        client_id=client_id,
    )
    return await issue_login_success(
        db=db,
        redis=redis,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        client_id=client_id,
    )


async def authenticate_primary_credentials(
    db: AsyncSession,
    redis: aioredis.Redis,
    email: str,
    password: str,
    ip_address: str = "",
    user_agent: str = "",
    client_id: str = "admin-console",
) -> User:
    """Validate email/password and account status without issuing tokens yet."""
    user = await get_user_by_email(db, email)
    if not user:
        await write_audit_event(
            db, "user.login.failure", "user", None,
            metadata={"ip_address": ip_address, "attempted_email": email}
        )
        await send_admin_activity_notification(
            db=db,
            org_id=None,
            title="Failed sign-in attempt",
            message=f"Unknown account login attempt for {email} from IP {ip_address or 'unknown'}.",
            event_key="security.login_failure",
        )
        await db.commit()
        raise AuthError("invalid_credentials", "Invalid email or password", 401)

    org = await get_organization(db, user.org_id)
    if not org or org.status != "active":
        raise AuthError("account_unavailable", "Your organization is no longer available for sign-in.", 403)

    # Check status
    if user.status == "suspended":
        raise AuthError("account_suspended", "Account is suspended", 423)

    if user.status == "locked":
        raise AuthError("account_locked", "Account is locked due to too many failed login attempts. Try again later.", 423)

    if user.must_change_password:
        raise AuthError(
            "password_setup_required",
            "You must complete password setup before signing in. Check your invitation email.",
            403,
        )

    if user.password_expires_at and user.password_expires_at < datetime.now(timezone.utc):
        grace_until = user.password_expires_at + timedelta(days=settings.PASSWORD_EXPIRY_GRACE_DAYS)
        if datetime.now(timezone.utc) > grace_until:
            raise AuthError(
                "password_expired_hard",
                "Your password expired and the grace period has ended. Reset your password to continue.",
                403,
            )
        raise AuthError(
            "password_expired",
            f"Your password has expired. Reset it before {grace_until.isoformat()} to continue.",
            403,
        )

    # Check lockout counter
    lockout_key = f"login_fail:{user.id}"
    fail_count = await redis.get(lockout_key)
    if fail_count and int(fail_count) >= MAX_LOGIN_FAILURES:
        user.status = "locked"
        await db.flush()
        raise AuthError("account_locked", "Account is locked due to too many failed login attempts", 423)

    # Verify password
    if not verify_password(password, user.password_hash):
        # Increment failure counter
        pipe = redis.pipeline()
        await pipe.incr(lockout_key)
        await pipe.expire(lockout_key, LOCKOUT_TTL)
        await pipe.execute()

        current_fails = await redis.get(lockout_key)
        if current_fails and int(current_fails) >= MAX_LOGIN_FAILURES:
            user.status = "locked"
            await db.flush()

        await write_audit_event(
            db, "user.login.failure", "user", str(user.id),
            org_id=user.org_id, actor_id=user.id,
            metadata={"ip_address": ip_address, "attempted_email": email}
        )
        await send_admin_activity_notification(
            db=db,
            org_id=user.org_id,
            actor_user_id=user.id,
            title="Failed sign-in attempt",
            message=f"Failed login for {email} from IP {ip_address or 'unknown'}.",
            event_key="security.login_failure",
        )
        await db.commit()
        raise AuthError("invalid_credentials", "Invalid email or password", 401)

    # Success: clear lockout
    await redis.delete(lockout_key)
    return user


async def issue_login_success(
    db: AsyncSession,
    redis: aioredis.Redis,
    user: User,
    ip_address: str = "",
    user_agent: str = "",
    client_id: str = "admin-console",
) -> dict[str, Any]:
    """Issue tokens and create a full admin-console session after successful auth."""
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    # Resolve RBAC
    roles, permissions = await resolve_rbac(db, user.id, user.org_id)
    if user.is_super_admin:
        roles = ["super_admin"]
        permissions = ["*"]
    user_groups = await get_user_groups(db, user.id)
    app_roles = ["app:admin"] if (user.is_super_admin or "org:admin" in roles) else []

    # Build user name
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email

    # Issue ID Token
    id_token_str, jti, expires_in = await issue_id_token(
        db=db,
        user_id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        name=name,
        given_name=user.first_name or "",
        family_name=user.last_name or "",
        org_id=user.org_id,
        is_super_admin=user.is_super_admin,
        client_id=client_id,
        roles=roles,
        permissions=permissions,
        groups=[group["name"] for group in user_groups],
        group_ids=[str(group["id"]) for group in user_groups],
        app_groups=[],
        app_group_ids=[],
        app_roles=app_roles,
        scopes=["openid", "profile", "email"],
    )

    await register_provider_session(
        db=db,
        redis=redis,
        jti=jti,
        user_id=str(user.id),
        client_id=client_id,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_in=expires_in,
    )

    browser_fingerprint = hashlib.sha256(f"{client_id}|{user_agent}".encode("utf-8")).hexdigest()
    known_browser_key = f"known_browsers:{user.id}"
    already_known = bool(await redis.sismember(known_browser_key, browser_fingerprint))
    if not already_known:
        known_count = int(await redis.scard(known_browser_key) or 0)
        await redis.sadd(known_browser_key, browser_fingerprint)
        if known_count > 0:
            await send_notification_event(
                db=db,
                user=user,
                event_key="security.new_browser_login",
                title="New browser sign-in detected",
                message=f"A new browser or device signed in to your account from IP {ip_address or 'unknown'}.",
            )

    # Audit event
    await write_audit_event(
        db, "user.login.success", "user", str(user.id),
        org_id=user.org_id, actor_id=user.id,
        metadata={"ip_address": ip_address, "user_agent": user_agent, "client_id": client_id}
    )

    result = {
        "id_token": id_token_str,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "session_jti": jti,
    }

    return result


async def authorize_and_issue_tokens(
    db: AsyncSession,
    redis: aioredis.Redis,
    user: User,
    client_id: str,
    scopes: list[str],
    nonce: Optional[str] = None,
    id_token_lifetime: Optional[int] = None,
    access_token_lifetime: Optional[int] = None,
    refresh_token_enabled: bool = False,
    ip_address: str = "",
    user_agent: str = "",
) -> dict[str, Any]:
    """Issue ID Token (always), Access Token (if enabled), Refresh Token (if enabled).
    
    Used after authorization code exchange.
    """
    roles, permissions = await resolve_rbac(db, user.id, user.org_id)
    if user.is_super_admin:
        roles = ["super_admin"]
        permissions = ["*"]
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
    user_groups = await get_user_groups(db, user.id)
    access = await resolve_application_access(db, user, client_id, roles, user_groups)
    authorized_app_groups = access["authorized_app_groups"]
    app_roles = access["app_roles"]
    if not access["access_allowed"]:
        raise AuthError("access_denied", access["access_error"], 403)

    # ID Token (always)
    id_token_str, jti, expires_in = await issue_id_token(
        db=db,
        user_id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        name=name,
        given_name=user.first_name or "",
        family_name=user.last_name or "",
        org_id=user.org_id,
        is_super_admin=user.is_super_admin,
        client_id=client_id,
        roles=roles,
        permissions=permissions,
        groups=[group["name"] for group in user_groups],
        group_ids=[str(group["id"]) for group in user_groups],
        app_groups=[group["name"] for group in authorized_app_groups],
        app_group_ids=[str(group["id"]) for group in authorized_app_groups],
        app_roles=app_roles,
        scopes=scopes,
        nonce=nonce,
        lifetime=id_token_lifetime,
    )

    await register_provider_session(
        db=db,
        redis=redis,
        jti=jti,
        user_id=str(user.id),
        client_id=client_id,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_in=expires_in,
    )

    # Audit
    await write_audit_event(
        db, "id_token.issued", "token", jti,
        org_id=user.org_id, actor_id=user.id,
        metadata={"jti": jti, "client_id": client_id, "scopes": scopes}
    )

    result: dict[str, Any] = {
        "id_token": id_token_str,
        "token_type": "Bearer",
        "expires_in": expires_in,
    }

    # Access Token (if enabled)
    if settings.ACCESS_TOKENS_ENABLED:
        at_str, at_jti, at_exp = await issue_access_token(
            db=db,
            sub=str(user.id),
            org_id=user.org_id,
            is_super_admin=user.is_super_admin,
            client_id=client_id,
            email=user.email,
            email_verified=user.email_verified,
            name=name,
            given_name=user.first_name or "",
            family_name=user.last_name or "",
            scopes=scopes,
            roles=roles,
            permissions=permissions,
            groups=[group["name"] for group in user_groups],
            group_ids=[str(group["id"]) for group in user_groups],
            app_groups=[group["name"] for group in authorized_app_groups],
            app_group_ids=[str(group["id"]) for group in authorized_app_groups],
            app_roles=app_roles,
            lifetime=access_token_lifetime,
        )
        result["access_token"] = at_str

    # Refresh Token (if enabled)
    if settings.REFRESH_TOKENS_ENABLED and refresh_token_enabled:
        rt = await issue_refresh_token(
            db=db,
            user_id=user.id,
            org_id=user.org_id,
            client_id=client_id,
            scopes=scopes,
        )
        result["refresh_token"] = rt

    return result


class AuthError(Exception):
    """Authentication error with error code, message, and HTTP status."""
    def __init__(self, error: str, description: str, status_code: int = 401):
        self.error = error
        self.description = description
        self.status_code = status_code
        super().__init__(description)
