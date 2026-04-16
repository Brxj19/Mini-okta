"""Application service: CRUD, secret generation/rotation, group assignments, and user app directory helpers."""

from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.application_group_assignment import ApplicationGroupAssignment
from app.models.application_role_mapping import ApplicationRoleMapping
from app.models.group import Group, GroupMember
from app.models.user import User
from app.utils.crypto_utils import generate_client_id, generate_client_secret, hash_password
from app.utils.pagination import encode_cursor, decode_cursor, build_pagination_response


def _dedupe_uris(values: list[str]) -> list[str]:
    return list(dict.fromkeys([value for value in values if value]))


def _build_default_post_logout_redirect_uris(redirect_uris: list[str]) -> list[str]:
    candidates: list[str] = []
    for redirect_uri in redirect_uris or []:
        candidates.append(redirect_uri)
        parsed = urlsplit(redirect_uri)
        if parsed.scheme and parsed.netloc:
            candidates.append(f"{parsed.scheme}://{parsed.netloc}")
    return _dedupe_uris(candidates)


async def create_application(
    db: AsyncSession,
    org_id: UUID,
    name: str,
    app_type: str,
    redirect_uris: list[str],
    post_logout_redirect_uris: list[str],
    allowed_scopes: list[str],
    id_token_lifetime: int = 3600,
    access_token_lifetime: int = 3600,
    refresh_token_enabled: bool = False,
    logo_url: Optional[str] = None,
) -> tuple[Application, Optional[str]]:
    """Create an OAuth application.
    
    For web/m2m: generates client_secret, stores bcrypt hash, returns raw value ONCE.
    For spa/native: client_secret = NULL.
    
    Returns (application, raw_client_secret_or_None)
    """
    client_id = generate_client_id()
    raw_secret = None
    hashed_secret = None

    if app_type in ("web", "m2m"):
        raw_secret = generate_client_secret()
        hashed_secret = hash_password(raw_secret)

    normalized_redirect_uris = _dedupe_uris(redirect_uris)
    normalized_post_logout_redirect_uris = _dedupe_uris(
        post_logout_redirect_uris or _build_default_post_logout_redirect_uris(normalized_redirect_uris)
    )

    app = Application(
        org_id=org_id,
        name=name,
        client_id=client_id,
        client_secret=hashed_secret,
        app_type=app_type,
        redirect_uris=normalized_redirect_uris,
        post_logout_redirect_uris=normalized_post_logout_redirect_uris,
        allowed_scopes=allowed_scopes,
        id_token_lifetime=id_token_lifetime,
        access_token_lifetime=access_token_lifetime,
        refresh_token_enabled=refresh_token_enabled,
        logo_url=logo_url,
    )
    db.add(app)
    await db.flush()

    return app, raw_secret


async def get_application(db: AsyncSession, app_id: UUID) -> Optional[Application]:
    """Get application by ID."""
    result = await db.execute(
        select(Application)
        .options(
            selectinload(Application.group_assignments)
            .selectinload(ApplicationGroupAssignment.group)
        )
        .where(Application.id == app_id, Application.status != "deleted")
    )
    return result.scalar_one_or_none()


async def get_application_by_client_id(db: AsyncSession, client_id: str) -> Optional[Application]:
    """Get application by client_id."""
    result = await db.execute(select(Application).where(Application.client_id == client_id))
    return result.scalar_one_or_none()


async def list_applications(
    db: AsyncSession,
    org_id: UUID,
    limit: int = 25,
    cursor: Optional[str] = None,
) -> dict[str, Any]:
    """List applications with cursor-based pagination."""
    query = select(Application).where(Application.org_id == org_id, Application.status != "deleted")

    if cursor:
        cursor_data = decode_cursor(cursor)
        if cursor_data:
            from datetime import datetime as dt
            cursor_created = dt.fromisoformat(cursor_data["created_at"])
            query = query.where(Application.created_at < cursor_created)

    count_query = (
        select(func.count())
        .select_from(Application)
        .where(Application.org_id == org_id, Application.status != "deleted")
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Application.created_at.desc()).limit(limit + 1)
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


async def update_application(
    db: AsyncSession,
    app_id: UUID,
    name: Optional[str] = None,
    redirect_uris: Optional[list[str]] = None,
    post_logout_redirect_uris: Optional[list[str]] = None,
    allowed_scopes: Optional[list[str]] = None,
    id_token_lifetime: Optional[int] = None,
    access_token_lifetime: Optional[int] = None,
    refresh_token_enabled: Optional[bool] = None,
    logo_url: Optional[str] = None,
) -> Optional[Application]:
    """Update application fields."""
    app = await get_application(db, app_id)
    if not app:
        return None

    if name is not None:
        app.name = name
    if redirect_uris is not None:
        app.redirect_uris = _dedupe_uris(redirect_uris)
    if post_logout_redirect_uris is not None:
        app.post_logout_redirect_uris = _dedupe_uris(post_logout_redirect_uris)
    if allowed_scopes is not None:
        app.allowed_scopes = allowed_scopes
    if id_token_lifetime is not None:
        app.id_token_lifetime = id_token_lifetime
    if access_token_lifetime is not None:
        app.access_token_lifetime = access_token_lifetime
    if refresh_token_enabled is not None:
        app.refresh_token_enabled = refresh_token_enabled
    if logo_url is not None:
        app.logo_url = logo_url

    app.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return app


async def rotate_secret(db: AsyncSession, app_id: UUID) -> tuple[Optional[Application], Optional[str]]:
    """Rotate client secret. Returns (app, raw_new_secret) — shown ONCE."""
    app = await get_application(db, app_id)
    if not app:
        return None, None

    if app.app_type in ("spa", "native"):
        return app, None

    raw_secret = generate_client_secret()
    app.client_secret = hash_password(raw_secret)
    app.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return app, raw_secret


async def disable_application(db: AsyncSession, app_id: UUID) -> Optional[Application]:
    """Disable an application."""
    app = await get_application(db, app_id)
    if not app:
        return None
    app.status = "disabled"
    app.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return app


async def delete_application(db: AsyncSession, app_id: UUID) -> Optional[Application]:
    """Soft-delete an application by setting status to deleted."""
    app = await get_application(db, app_id)
    if not app:
        return None
    app.status = "deleted"
    app.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return app


async def list_application_groups(db: AsyncSession, app_id: UUID) -> list[Group]:
    """List groups assigned to an application."""
    result = await db.execute(
        select(Group)
        .join(ApplicationGroupAssignment, ApplicationGroupAssignment.group_id == Group.id)
        .where(ApplicationGroupAssignment.application_id == app_id)
        .order_by(Group.name.asc())
    )
    return list(result.scalars().all())


async def list_user_assigned_applications(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
) -> list[Application]:
    """List active applications reachable through the user's assigned groups."""
    result = await db.execute(
        select(Application)
        .distinct()
        .join(ApplicationGroupAssignment, ApplicationGroupAssignment.application_id == Application.id)
        .join(GroupMember, GroupMember.group_id == ApplicationGroupAssignment.group_id)
        .where(
            Application.org_id == org_id,
            Application.status == "active",
            GroupMember.user_id == user_id,
        )
        .order_by(Application.name.asc())
    )
    return list(result.scalars().all())


async def assign_groups_to_application(db: AsyncSession, app_id: UUID, group_ids: list[UUID]) -> list[UUID]:
    """Assign org groups to an application."""
    assigned: list[UUID] = []
    for group_id in group_ids:
        existing = await db.execute(
            select(ApplicationGroupAssignment).where(
                ApplicationGroupAssignment.application_id == app_id,
                ApplicationGroupAssignment.group_id == group_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(ApplicationGroupAssignment(application_id=app_id, group_id=group_id))
            assigned.append(group_id)

    await db.flush()
    return assigned


async def list_group_users(db: AsyncSession, group_id: UUID) -> list[User]:
    """List active users in a group."""
    result = await db.execute(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(
            GroupMember.group_id == group_id,
            User.deleted_at.is_(None),
            User.status == "active",
        )
        .order_by(User.email.asc())
    )
    return list(result.scalars().all())


async def remove_group_from_application(db: AsyncSession, app_id: UUID, group_id: UUID) -> bool:
    """Remove a group assignment from an application."""
    result = await db.execute(
        sa_delete(ApplicationGroupAssignment).where(
            ApplicationGroupAssignment.application_id == app_id,
            ApplicationGroupAssignment.group_id == group_id,
        )
    )
    await db.flush()
    return result.rowcount > 0


async def list_application_role_mappings(db: AsyncSession, app_id: UUID) -> list[ApplicationRoleMapping]:
    """List role mappings configured for an application."""
    result = await db.execute(
        select(ApplicationRoleMapping)
        .where(ApplicationRoleMapping.application_id == app_id)
        .order_by(
            ApplicationRoleMapping.source_type.asc(),
            ApplicationRoleMapping.source_value.asc(),
            ApplicationRoleMapping.app_role.asc(),
        )
    )
    return list(result.scalars().all())


async def create_application_role_mapping(
    db: AsyncSession,
    app_id: UUID,
    source_type: str,
    source_value: str,
    app_role: str,
) -> ApplicationRoleMapping:
    """Create or return an application role mapping."""
    normalized_source_type = source_type.strip().lower()
    normalized_source_value = source_value.strip().lower()
    normalized_app_role = app_role.strip().lower()

    existing = await db.execute(
        select(ApplicationRoleMapping).where(
            ApplicationRoleMapping.application_id == app_id,
            ApplicationRoleMapping.source_type == normalized_source_type,
            ApplicationRoleMapping.source_value == normalized_source_value,
            ApplicationRoleMapping.app_role == normalized_app_role,
        )
    )
    mapping = existing.scalar_one_or_none()
    if mapping:
        return mapping

    mapping = ApplicationRoleMapping(
        application_id=app_id,
        source_type=normalized_source_type,
        source_value=normalized_source_value,
        app_role=normalized_app_role,
    )
    db.add(mapping)
    await db.flush()
    return mapping


async def delete_application_role_mapping(
    db: AsyncSession,
    app_id: UUID,
    mapping_id: UUID,
) -> bool:
    """Delete one application role mapping by ID."""
    result = await db.execute(
        sa_delete(ApplicationRoleMapping).where(
            ApplicationRoleMapping.application_id == app_id,
            ApplicationRoleMapping.id == mapping_id,
        )
    )
    await db.flush()
    return result.rowcount > 0
