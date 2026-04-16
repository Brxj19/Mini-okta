"""Group service: CRUD, member management, role assignment."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember, GroupRole
from app.models.application import Application
from app.models.application_group_assignment import ApplicationGroupAssignment
from app.models.user import User
from app.models.role import Role
from app.utils.pagination import encode_cursor, decode_cursor, build_pagination_response


async def create_group(db: AsyncSession, org_id: UUID, name: str, description: Optional[str] = None) -> Group:
    """Create a new group."""
    normalized_name = (name or '').strip()
    if not normalized_name:
        raise ValueError("Group name is required.")

    existing = await db.execute(
        select(Group).where(Group.org_id == org_id, Group.name == normalized_name)
    )
    if existing.scalar_one_or_none():
        raise ValueError("A group with this name already exists.")

    group = Group(org_id=org_id, name=normalized_name, description=(description.strip() if isinstance(description, str) else description))
    db.add(group)
    await db.flush()
    return group


async def get_group(db: AsyncSession, group_id: UUID) -> Optional[Group]:
    """Get group by ID."""
    result = await db.execute(select(Group).where(Group.id == group_id))
    return result.scalar_one_or_none()


async def list_groups(db: AsyncSession, org_id: UUID, limit: int = 25, cursor: Optional[str] = None) -> dict[str, Any]:
    """List groups with member_count and cursor-based pagination."""
    # Subquery for member count
    member_count_subq = (
        select(GroupMember.group_id, func.count().label("member_count"))
        .join(User, User.id == GroupMember.user_id)
        .where(User.deleted_at.is_(None))
        .group_by(GroupMember.group_id)
        .subquery()
    )

    query = (
        select(Group, func.coalesce(member_count_subq.c.member_count, 0).label("member_count"))
        .outerjoin(member_count_subq, Group.id == member_count_subq.c.group_id)
        .where(Group.org_id == org_id)
    )

    if cursor:
        cursor_data = decode_cursor(cursor)
        if cursor_data:
            from datetime import datetime as dt
            cursor_created = dt.fromisoformat(cursor_data["created_at"])
            query = query.where(Group.created_at < cursor_created)

    count_query = select(func.count()).select_from(Group).where(Group.org_id == org_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Group.created_at.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    data = []
    for row in rows:
        group = row[0]
        mc = row[1]
        data.append({
            "id": group.id,
            "org_id": group.org_id,
            "name": group.name,
            "description": group.description,
            "member_count": mc,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        })

    next_cursor = None
    if has_more and data:
        last = data[-1]
        next_cursor = encode_cursor(str(last["id"]), last["created_at"])

    return {
        "data": data,
        "pagination": build_pagination_response(data, total, limit, has_more, next_cursor),
    }


async def update_group(db: AsyncSession, group_id: UUID, name: Optional[str] = None, description: Optional[str] = None) -> Optional[Group]:
    """Update group name/description."""
    group = await get_group(db, group_id)
    if not group:
        return None
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Group name is required.")
        existing = await db.execute(
            select(Group).where(
                Group.org_id == group.org_id,
                Group.name == normalized_name,
                Group.id != group.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("A group with this name already exists.")
        group.name = normalized_name
    if description is not None:
        group.description = description.strip() or None
    group.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return group


async def delete_group(db: AsyncSession, group_id: UUID) -> bool:
    """Delete group (cascades memberships and role assignments)."""
    group = await get_group(db, group_id)
    if not group:
        return False
    await db.delete(group)
    await db.flush()
    return True


async def get_group_members(
    db: AsyncSession, group_id: UUID, limit: int = 25, cursor: Optional[str] = None
) -> dict[str, Any]:
    """List members of a group with pagination."""
    query = (
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id, User.deleted_at.is_(None))
    )

    if cursor:
        cursor_data = decode_cursor(cursor)
        if cursor_data:
            from datetime import datetime as dt
            cursor_created = dt.fromisoformat(cursor_data["created_at"])
            query = query.where(User.created_at < cursor_created)

    count_query = (
        select(func.count())
        .select_from(GroupMember)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id, User.deleted_at.is_(None))
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(User.created_at.desc()).limit(limit + 1)
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


async def add_members(db: AsyncSession, group_id: UUID, user_ids: list[UUID]) -> list[UUID]:
    """Add users to a group. Returns list of successfully added user IDs."""
    added = []
    for uid in user_ids:
        existing = await db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == uid,
            )
        )
        if existing.scalar_one_or_none() is None:
            member = GroupMember(group_id=group_id, user_id=uid)
            db.add(member)
            added.append(uid)
    await db.flush()
    return added


async def get_application_group_membership_conflicts(
    db: AsyncSession,
    group_id: UUID,
    user_ids: list[UUID],
) -> list[dict[str, Any]]:
    """Find users already present in another assigned group for the same application."""
    if not user_ids:
      return []

    target_app_ids_query = select(ApplicationGroupAssignment.application_id).where(
        ApplicationGroupAssignment.group_id == group_id
    )
    target_app_ids_result = await db.execute(target_app_ids_query)
    target_app_ids = list(target_app_ids_result.scalars().all())

    if not target_app_ids:
        return []

    conflict_query = (
        select(
            User.id.label("user_id"),
            User.email.label("user_email"),
            Group.id.label("group_id"),
            Group.name.label("group_name"),
            Application.id.label("application_id"),
            Application.name.label("application_name"),
        )
        .join(GroupMember, GroupMember.user_id == User.id)
        .join(Group, Group.id == GroupMember.group_id)
        .join(ApplicationGroupAssignment, ApplicationGroupAssignment.group_id == Group.id)
        .join(Application, Application.id == ApplicationGroupAssignment.application_id)
        .where(
            User.id.in_(user_ids),
            ApplicationGroupAssignment.application_id.in_(target_app_ids),
            Group.id != group_id,
        )
        .order_by(User.email.asc(), Application.name.asc(), Group.name.asc())
    )
    conflict_result = await db.execute(conflict_query)
    rows = conflict_result.all()

    conflicts: list[dict[str, Any]] = []
    for row in rows:
        conflicts.append(
            {
                "user_id": str(row.user_id),
                "user_email": row.user_email,
                "application_id": str(row.application_id),
                "application_name": row.application_name,
                "group_id": str(row.group_id),
                "group_name": row.group_name,
            }
        )
    return conflicts


async def remove_member(db: AsyncSession, group_id: UUID, user_id: UUID) -> bool:
    """Remove a user from a group."""
    result = await db.execute(
        sa_delete(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    )
    await db.flush()
    return result.rowcount > 0


async def assign_roles(db: AsyncSession, group_id: UUID, role_ids: list[UUID]) -> list[UUID]:
    """Assign roles to a group. Returns list of successfully assigned role IDs."""
    assigned = []
    for rid in role_ids:
        existing = await db.execute(
            select(GroupRole).where(
                GroupRole.group_id == group_id,
                GroupRole.role_id == rid,
            )
        )
        if existing.scalar_one_or_none() is None:
            gr = GroupRole(group_id=group_id, role_id=rid)
            db.add(gr)
            assigned.append(rid)
    await db.flush()
    return assigned


async def remove_role(db: AsyncSession, group_id: UUID, role_id: UUID) -> bool:
    """Remove a role from a group."""
    result = await db.execute(
        sa_delete(GroupRole).where(
            GroupRole.group_id == group_id,
            GroupRole.role_id == role_id,
        )
    )
    await db.flush()
    return result.rowcount > 0


async def get_group_roles(db: AsyncSession, group_id: UUID) -> list[Role]:
    """Get all roles assigned to a group."""
    result = await db.execute(
        select(Role)
        .join(GroupRole, GroupRole.role_id == Role.id)
        .where(GroupRole.group_id == group_id)
    )
    return list(result.scalars().all())
