"""User service: CRUD, password hashing, email verification."""

from datetime import datetime, timezone, timedelta
import secrets
from urllib.parse import quote
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.group import GroupMember, Group, GroupRole
from app.models.role import Role
from app.utils.crypto_utils import hash_password, validate_password_policy
from app.utils.pagination import encode_cursor, decode_cursor, build_pagination_response
from app.config import settings


def _build_deleted_user_email(user: User) -> str:
    """Replace deleted user email with a tombstone value so the original can be reused."""
    original_email = (user.email or "user").strip() or "user"
    return f"deleted+{user.id.hex}+{quote(original_email, safe='')}@deleted.local"


async def create_user(
    db: AsyncSession,
    org_id: UUID,
    email: str,
    password: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> User:
    """Create a user with bcrypt hashed password (cost >= 12).
    
    Validates password policy before creation.
    """
    password_to_store = password or generate_temporary_password()
    valid, error = validate_password_policy(password_to_store)
    if not valid:
        raise ValueError(error)

    user = User(
        org_id=org_id,
        email=email,
        password_hash=hash_password(password_to_store),
        first_name=first_name,
        last_name=last_name,
        email_verified=False,
        must_change_password=True,
        invited_at=datetime.now(timezone.utc),
        invitation_expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.INVITATION_LINK_TTL_HOURS),
    )
    db.add(user)
    await db.flush()
    return user


def generate_temporary_password() -> str:
    """Generate a strong temporary password for invitation-only onboarding."""
    return f"TmP!{secrets.token_urlsafe(18)}9aA"


async def get_user(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Get a user by ID."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str, org_id: Optional[UUID] = None) -> Optional[User]:
    """Get a user by email, optionally scoped to an org."""
    query = select(User).where(User.email == email, User.deleted_at.is_(None))
    if org_id:
        query = query.where(User.org_id == org_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_detail(db: AsyncSession, user_id: UUID) -> Optional[dict[str, Any]]:
    """Get user detail with groups, roles, and permissions."""
    user = await get_user(db, user_id)
    if not user:
        return None

    # Get groups
    groups_query = (
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user_id)
    )
    groups_result = await db.execute(groups_query)
    groups = groups_result.scalars().all()

    # Get roles and permissions via RBAC
    roles, permissions = await resolve_rbac(db, user_id, user.org_id)

    return {
        "user": user,
        "groups": [{"id": g.id, "name": g.name, "description": g.description} for g in groups],
        "roles": roles,
        "permissions": permissions,
    }


async def get_user_groups(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    """Get all group memberships for a user."""
    groups_query = (
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user_id)
        .order_by(Group.name.asc())
    )
    groups_result = await db.execute(groups_query)
    groups = groups_result.scalars().all()
    return [{"id": g.id, "name": g.name, "description": g.description} for g in groups]


async def list_users(
    db: AsyncSession,
    org_id: UUID,
    limit: int = 25,
    cursor: Optional[str] = None,
    status_filter: Optional[str] = None,
    email_contains: Optional[str] = None,
    sort: str = "created_at:desc",
) -> dict[str, Any]:
    """List users with cursor-based pagination and filters."""
    query = select(User).where(User.org_id == org_id, User.deleted_at.is_(None))

    if status_filter:
        query = query.where(User.status == status_filter)
    if email_contains:
        query = query.where(User.email.ilike(f"%{email_contains}%"))

    # Parse sort
    sort_field, sort_dir = "created_at", "desc"
    if ":" in sort:
        sort_field, sort_dir = sort.split(":", 1)

    # Cursor pagination
    if cursor:
        cursor_data = decode_cursor(cursor)
        if cursor_data:
            from datetime import datetime as dt
            cursor_created = dt.fromisoformat(cursor_data["created_at"])
            if sort_dir == "desc":
                query = query.where(User.created_at < cursor_created)
            else:
                query = query.where(User.created_at > cursor_created)

    # Count
    count_query = select(func.count()).select_from(User).where(
        User.org_id == org_id, User.deleted_at.is_(None)
    )
    if status_filter:
        count_query = count_query.where(User.status == status_filter)
    if email_contains:
        count_query = count_query.where(User.email.ilike(f"%{email_contains}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sort and limit
    sort_col = getattr(User, sort_field, User.created_at)
    if sort_dir == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    query = query.limit(limit + 1)
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


async def update_user(db: AsyncSession, user_id: UUID, first_name: Optional[str] = None, last_name: Optional[str] = None) -> Optional[User]:
    """Update user first/last name."""
    user = await get_user(db, user_id)
    if not user:
        return None

    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    user.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return user


async def update_current_user_profile(
    db: AsyncSession,
    user_id: UUID,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    profile_image_url: Optional[str] = None,
) -> Optional[User]:
    """Update self-service profile fields for a user."""
    user = await get_user(db, user_id)
    if not user:
        return None

    user.first_name = first_name
    user.last_name = last_name
    user.profile_image_url = profile_image_url
    user.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return user


async def suspend_user(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Suspend a user."""
    user = await get_user(db, user_id)
    if not user:
        return None
    user.status = "suspended"
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def unlock_user(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Unlock a locked user account."""
    user = await get_user(db, user_id)
    if not user:
        return None
    user.status = "active"
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def soft_delete_user(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Soft delete a user."""
    user = await get_user(db, user_id)
    if not user:
        return None
    user.email = _build_deleted_user_email(user)
    user.status = "deleted"
    user.email_verified = False
    user.must_change_password = False
    user.invitation_expires_at = None
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = None
    user.mfa_recovery_codes_generated_at = None
    user.deleted_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def verify_user_email(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Set email_verified=true for user."""
    user = await get_user(db, user_id)
    if not user:
        return None
    user.email_verified = True
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def update_password(db: AsyncSession, user_id: UUID, new_password: str) -> Optional[User]:
    """Update user password with policy validation and bcrypt hashing."""
    valid, error = validate_password_policy(new_password)
    if not valid:
        raise ValueError(error)

    user = await get_user(db, user_id)
    if not user:
        return None
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    user.password_expires_at = user.password_changed_at + timedelta(days=settings.PASSWORD_MAX_AGE_DAYS)
    user.invitation_expires_at = None
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def resolve_rbac(db: AsyncSession, user_id: UUID, org_id: UUID) -> tuple[list[str], list[str]]:
    """Resolve RBAC: get distinct role names and permissions for a user.
    
    Returns (roles, permissions)
    """
    # Step 1: Get role names
    roles_query = (
        select(Role.name)
        .distinct()
        .join(GroupRole, GroupRole.role_id == Role.id)
        .join(GroupMember, GroupMember.group_id == GroupRole.group_id)
        .where(GroupMember.user_id == user_id, Role.org_id == org_id)
    )
    roles_result = await db.execute(roles_query)
    roles = [row[0] for row in roles_result.all()]

    # Step 2: Get permissions  
    permissions_query = (
        select(func.unnest(Role.permissions))
        .distinct()
        .join(GroupRole, GroupRole.role_id == Role.id)
        .join(GroupMember, GroupMember.group_id == GroupRole.group_id)
        .where(GroupMember.user_id == user_id, Role.org_id == org_id)
    )
    perms_result = await db.execute(permissions_query)
    permissions = [row[0] for row in perms_result.all()]

    return roles, permissions
