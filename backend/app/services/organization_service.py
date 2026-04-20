"""Organization service: CRUD, suspend, activate, and onboarding."""

from datetime import datetime, timezone, timedelta
import re
from urllib.parse import quote, urlparse
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember, GroupRole
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.utils.crypto_utils import hash_password, validate_password_policy
from app.utils.pagination import encode_cursor, decode_cursor, build_pagination_response
from app.config import settings
from app.services.user_service import generate_temporary_password


DEFAULT_SELF_SERVE_LIMITS = {
    "max_users": 5,
    "max_apps": 2,
}

SELF_SERVE_ALLOWED_SCOPES = {"openid", "profile", "email"}

# System roles to seed for every new organization
SYSTEM_ROLES = [
    {
        "name": "org:admin",
        "description": "Organization administrator with full access",
        "permissions": [
            "org:read", "org:update",
            "user:create", "user:read", "user:update", "user:delete", "user:reset_password",
            "app:create", "app:read", "app:update", "app:delete",
            "group:create", "group:read", "group:update", "group:delete",
            "group:member:add", "group:member:remove",
            "role:create", "role:read", "role:update",
            "audit:read",
        ],
    },
    {
        "name": "app:manager",
        "description": "Application manager",
        "permissions": ["app:create", "app:read", "app:update", "app:delete"],
    },
    {
        "name": "user:manager",
        "description": "User manager",
        "permissions": ["user:create", "user:read", "user:update", "user:delete", "user:reset_password"],
    },
    {
        "name": "group:manager",
        "description": "Group manager",
        "permissions": [
            "group:create", "group:read", "group:update", "group:delete",
            "group:member:add", "group:member:remove",
        ],
    },
    {
        "name": "viewer",
        "description": "Read-only viewer",
        "permissions": ["org:read", "user:read", "app:read", "group:read", "role:read", "audit:read"],
    },
    {
        "name": "member",
        "description": "Basic member with login access",
        "permissions": ["auth:login"],
    },
]


async def create_organization(db: AsyncSession, name: str, slug: str, display_name: Optional[str] = None, org_settings: Optional[dict] = None) -> Organization:
    """Create an organization and auto-seed 6 system roles."""
    org = Organization(
        name=name,
        slug=slug,
        display_name=display_name,
        settings=org_settings or {},
    )
    db.add(org)
    await db.flush()

    # Seed system roles
    for role_data in SYSTEM_ROLES:
        role = Role(
            org_id=org.id,
            name=role_data["name"],
            description=role_data["description"],
            permissions=role_data["permissions"],
            is_system=True,
        )
        db.add(role)

    await db.flush()
    return org


def slugify_org_name(name: str) -> str:
    """Convert organization name to a safe slug."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return cleaned or "org"


async def resolve_available_org_slug(db: AsyncSession, preferred_slug: str) -> str:
    """Return preferred slug if free, otherwise append numeric suffix."""
    candidate = preferred_slug
    suffix = 2
    while True:
        existing = await get_organization_by_slug(db, candidate)
        if not existing:
            return candidate
        candidate = f"{preferred_slug}-{suffix}"
        suffix += 1


async def create_organization_with_admin(
    db: AsyncSession,
    name: str,
    slug: str,
    admin_email: str,
    admin_password: Optional[str] = None,
    admin_first_name: Optional[str] = None,
    admin_last_name: Optional[str] = None,
    display_name: Optional[str] = None,
    org_settings: Optional[dict] = None,
) -> tuple[Organization, User, str]:
    """Create an organization and bootstrap its first org admin."""
    password_to_store = admin_password or generate_temporary_password()
    valid, error = validate_password_policy(password_to_store)
    if not valid:
        raise ValueError(error)

    merged_settings = {
        "signup_origin": "super_admin",
        "access_tier": "verified_enterprise",
        "verification_status": "approved",
        "limits": {},
    }
    if org_settings:
        merged_settings.update(org_settings)

    org = await create_organization(db, name, slug, display_name, merged_settings)

    admin_user = User(
        org_id=org.id,
        email=admin_email,
        password_hash=hash_password(password_to_store),
        first_name=admin_first_name,
        last_name=admin_last_name,
        email_verified=False,
        status="active",
        is_super_admin=False,
        must_change_password=True,
        invited_at=datetime.now(timezone.utc),
        invitation_expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.INVITATION_LINK_TTL_HOURS),
    )
    db.add(admin_user)
    await db.flush()

    admin_group = Group(
        org_id=org.id,
        name="admins",
        description="Bootstrap organization administrators",
    )
    db.add(admin_group)
    await db.flush()

    admin_role_result = await db.execute(
        select(Role).where(Role.org_id == org.id, Role.name == "org:admin")
    )
    admin_role = admin_role_result.scalar_one_or_none()
    if not admin_role:
        raise ValueError("Failed to resolve org:admin role for organization bootstrap")

    db.add(GroupMember(group_id=admin_group.id, user_id=admin_user.id))
    db.add(GroupRole(group_id=admin_group.id, role_id=admin_role.id))
    await db.flush()

    return org, admin_user, password_to_store


def get_org_access_tier(settings: Optional[dict[str, Any]]) -> str:
    """Return access tier from organization settings, defaulting to verified."""
    if not isinstance(settings, dict):
        return "verified_enterprise"
    return str(settings.get("access_tier") or "verified_enterprise")


def is_org_limited(settings: Optional[dict[str, Any]]) -> bool:
    """Whether organization is currently in limited self-serve mode."""
    return get_org_access_tier(settings) == "limited"


def get_org_limits(settings: Optional[dict[str, Any]]) -> dict[str, int]:
    """Return normalized limits object for an organization."""
    if not isinstance(settings, dict):
        return {}
    raw_limits = settings.get("limits")
    if not isinstance(raw_limits, dict):
        return {}
    normalized: dict[str, int] = {}
    for key in ("max_users", "max_apps"):
        value = raw_limits.get(key)
        if isinstance(value, int) and value > 0:
            normalized[key] = value
    return normalized


def _is_local_redirect_uri(uri: str) -> bool:
    """Whether redirect URI targets localhost/dev-only endpoints."""
    try:
        parsed = urlparse(uri)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local")


def validate_limited_org_app_policy(
    *,
    app_type: str,
    redirect_uris: list[str],
    allowed_scopes: list[str],
    refresh_token_enabled: bool,
) -> Optional[str]:
    """Return policy error string when limited-tier org app config is not allowed."""
    normalized_scopes = {str(scope).strip() for scope in (allowed_scopes or []) if str(scope).strip()}

    if app_type == "m2m":
        return "M2M applications are only available after enterprise verification."
    if refresh_token_enabled:
        return "Refresh tokens are disabled for limited self-serve organizations."
    if normalized_scopes and not normalized_scopes.issubset(SELF_SERVE_ALLOWED_SCOPES):
        disallowed = sorted(scope for scope in normalized_scopes if scope not in SELF_SERVE_ALLOWED_SCOPES)
        return f"Requested scopes are restricted in free tier: {', '.join(disallowed)}."
    if any(not _is_local_redirect_uri(uri) for uri in (redirect_uris or [])):
        return "Production/custom-domain redirect URIs are disabled in free tier. Use localhost-style URIs until verified."
    return None


def build_self_serve_settings(existing: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Return normalized self-serve limited settings payload."""
    payload: dict[str, Any] = {}
    if isinstance(existing, dict):
        payload.update(existing)
    payload.update(
        {
            "signup_origin": "self_serve",
            "access_tier": "limited",
            "verification_status": "pending",
            "limits": payload.get("limits") or DEFAULT_SELF_SERVE_LIMITS.copy(),
        }
    )
    return payload


def build_verified_enterprise_settings(existing: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Return normalized verified-enterprise settings payload."""
    payload: dict[str, Any] = {}
    if isinstance(existing, dict):
        payload.update(existing)
    payload.update(
        {
            "access_tier": "verified_enterprise",
            "verification_status": "approved",
        }
    )
    return payload


async def set_organization_access_tier(db: AsyncSession, org_id: UUID, tier: str) -> Optional[Organization]:
    """Set organization access tier to limited or verified_enterprise."""
    org = await get_organization(db, org_id)
    if not org:
        return None

    if tier == "limited":
        org.settings = build_self_serve_settings(org.settings)
    elif tier == "verified_enterprise":
        org.settings = build_verified_enterprise_settings(org.settings)
    else:
        raise ValueError("Unsupported access tier")
    org.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return org


async def get_organization(db: AsyncSession, org_id: UUID) -> Optional[Organization]:
    """Get organization by ID."""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_organization_by_slug(db: AsyncSession, slug: str) -> Optional[Organization]:
    """Get organization by slug."""
    result = await db.execute(
        select(Organization).where(Organization.slug == slug, Organization.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def list_organizations(db: AsyncSession, limit: int = 25, cursor: Optional[str] = None) -> dict[str, Any]:
    """List organizations with cursor-based pagination."""
    query = select(Organization).where(Organization.deleted_at.is_(None))

    if cursor:
        cursor_data = decode_cursor(cursor)
        if cursor_data:
            from datetime import datetime as dt
            cursor_created = dt.fromisoformat(cursor_data["created_at"])
            query = query.where(Organization.created_at < cursor_created)

    # Count total
    count_query = select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Organization.created_at.desc()).limit(limit + 1)
    result = await db.execute(query)
    records = list(result.scalars().all())

    has_more = len(records) > limit
    if has_more:
        records = records[:limit]

    next_cursor = None
    if has_more and records:
        last = records[-1]
        next_cursor = encode_cursor(str(last.id), last.created_at)

    return {
        "data": records,
        "pagination": build_pagination_response(records, total, limit, has_more, next_cursor),
    }


async def update_organization(db: AsyncSession, org_id: UUID, display_name: Optional[str] = None, org_settings: Optional[dict] = None) -> Optional[Organization]:
    """Update organization display_name and/or settings."""
    org = await get_organization(db, org_id)
    if not org:
        return None

    if display_name is not None:
        org.display_name = display_name
    if org_settings is not None:
        org.settings = org_settings
    org.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return org


async def suspend_organization(db: AsyncSession, org_id: UUID) -> Optional[Organization]:
    """Suspend an organization."""
    org = await get_organization(db, org_id)
    if not org:
        return None
    org.status = "suspended"
    org.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return org


async def activate_organization(db: AsyncSession, org_id: UUID) -> Optional[Organization]:
    """Activate an organization."""
    org = await get_organization(db, org_id)
    if not org:
        return None
    org.status = "active"
    org.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return org


def _build_deleted_organization_slug(org: Organization) -> str:
    """Create a unique tombstone slug so deleted rows don't block recreation."""
    original_slug = (org.slug or "organization").strip() or "organization"
    safe_slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in original_slug.lower()).strip("-")
    safe_slug = safe_slug or "organization"
    return f"deleted-{org.id.hex[:12]}-{safe_slug}"


def _build_deleted_organization_name(org: Organization) -> str:
    """Create a unique tombstone name that preserves traceability."""
    original_name = (org.name or "organization").strip() or "organization"
    return f"deleted+{org.id.hex}+{quote(original_name, safe='')}@deleted.local"


async def soft_delete_organization(db: AsyncSession, org_id: UUID) -> Optional[Organization]:
    """Soft delete: set deleted_at and status='deleted'."""
    org = await get_organization(db, org_id)
    if not org:
        return None
    org.name = _build_deleted_organization_name(org)
    org.slug = _build_deleted_organization_slug(org)
    org.display_name = None
    org.deleted_at = datetime.now(timezone.utc)
    org.status = "deleted"
    org.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return org
