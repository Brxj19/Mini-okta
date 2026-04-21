"""Hard-delete soft-deleted applications, users, and organizations older than the retention window."""

import asyncio
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import async_session_factory
from app.models.application import Application
from app.models.application_group_assignment import ApplicationGroupAssignment
from app.models.application_role_mapping import ApplicationRoleMapping
from app.models.audit_log import AuditLog
from app.models.email_delivery import EmailDelivery
from app.models.group import Group, GroupMember, GroupRole
from app.models.notification import Notification
from app.models.notification_preference import NotificationPreference
from app.models.organization import Organization
from app.models.password_reset import PasswordResetToken
from app.models.role import Role
from app.models.token import Token
from app.models.user import User
from app.config import settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Purge soft-deleted records older than the retention window.")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=settings.SOFT_DELETE_RETENTION_DAYS,
        help="Delete soft-deleted records older than this many days.",
    )
    return parser.parse_args()


async def purge_deleted_users(db, user_ids):
    if not user_ids:
        return 0

    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids)))
    await db.execute(delete(NotificationPreference).where(NotificationPreference.user_id.in_(user_ids)))
    await db.execute(delete(Notification).where(Notification.user_id.in_(user_ids)))
    await db.execute(delete(EmailDelivery).where(EmailDelivery.user_id.in_(user_ids)))
    await db.execute(delete(Token).where(Token.user_id.in_(user_ids)))
    await db.execute(delete(GroupMember).where(GroupMember.user_id.in_(user_ids)))
    await db.execute(delete(AuditLog).where(AuditLog.actor_id.in_(user_ids)))
    await db.execute(
        delete(AuditLog).where(
            AuditLog.resource_type == "user",
            AuditLog.resource_id.in_([str(user_id) for user_id in user_ids]),
        )
    )
    await db.execute(delete(User).where(User.id.in_(user_ids)))
    return len(user_ids)


async def purge_deleted_applications(db, app_ids):
    if not app_ids:
        return 0

    app_id_strings = [str(app_id) for app_id in app_ids]
    client_rows = await db.execute(select(Application.client_id).where(Application.id.in_(app_ids)))
    client_ids = [row[0] for row in client_rows.all()]

    await db.execute(delete(ApplicationGroupAssignment).where(ApplicationGroupAssignment.application_id.in_(app_ids)))
    await db.execute(delete(ApplicationRoleMapping).where(ApplicationRoleMapping.application_id.in_(app_ids)))
    if client_ids:
        await db.execute(delete(Token).where(Token.client_id.in_(client_ids)))
    await db.execute(
        delete(AuditLog).where(
            AuditLog.resource_type == "application",
            AuditLog.resource_id.in_(app_id_strings),
        )
    )
    await db.execute(delete(Application).where(Application.id.in_(app_ids)))
    return len(app_ids)


async def purge_deleted_organizations(db, org_ids):
    if not org_ids:
        return 0

    user_rows = await db.execute(select(User.id).where(User.org_id.in_(org_ids)))
    org_user_ids = [row[0] for row in user_rows.all()]
    await purge_deleted_users(db, org_user_ids)

    app_rows = await db.execute(select(Application.id).where(Application.org_id.in_(org_ids)))
    app_ids = [row[0] for row in app_rows.all()]
    await purge_deleted_applications(db, app_ids)

    group_rows = await db.execute(select(Group.id).where(Group.org_id.in_(org_ids)))
    group_ids = [row[0] for row in group_rows.all()]
    if group_ids:
        await db.execute(delete(GroupMember).where(GroupMember.group_id.in_(group_ids)))
        await db.execute(delete(GroupRole).where(GroupRole.group_id.in_(group_ids)))
        await db.execute(delete(ApplicationGroupAssignment).where(ApplicationGroupAssignment.group_id.in_(group_ids)))
        await db.execute(delete(Group).where(Group.id.in_(group_ids)))

    role_rows = await db.execute(select(Role.id).where(Role.org_id.in_(org_ids)))
    role_ids = [row[0] for row in role_rows.all()]
    if role_ids:
        await db.execute(delete(GroupRole).where(GroupRole.role_id.in_(role_ids)))
        await db.execute(delete(Role).where(Role.id.in_(role_ids)))

    await db.execute(delete(EmailDelivery).where(EmailDelivery.org_id.in_(org_ids)))
    await db.execute(delete(Token).where(Token.org_id.in_(org_ids)))
    await db.execute(delete(AuditLog).where(AuditLog.org_id.in_(org_ids)))
    await db.execute(delete(Organization).where(Organization.id.in_(org_ids)))
    return len(org_ids)


async def main() -> None:
    args = _parse_args()
    retention_days = max(0, int(args.retention_days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with async_session_factory() as db:
        deleted_org_rows = await db.execute(
            select(Organization.id).where(
                Organization.deleted_at.is_not(None),
                Organization.deleted_at <= cutoff,
            )
        )
        deleted_org_ids = [row[0] for row in deleted_org_rows.all()]

        deleted_app_query = select(Application.id).where(
            Application.deleted_at.is_not(None),
            Application.deleted_at <= cutoff,
        )
        if deleted_org_ids:
            deleted_app_query = deleted_app_query.where(Application.org_id.not_in(deleted_org_ids))

        deleted_app_rows = await db.execute(deleted_app_query)
        deleted_app_ids = [row[0] for row in deleted_app_rows.all()]

        deleted_user_query = select(User.id).where(
            User.deleted_at.is_not(None),
            User.deleted_at <= cutoff,
        )
        if deleted_org_ids:
            deleted_user_query = deleted_user_query.where(User.org_id.not_in(deleted_org_ids))

        deleted_user_rows = await db.execute(deleted_user_query)
        deleted_user_ids = [row[0] for row in deleted_user_rows.all()]

        purged_apps = await purge_deleted_applications(db, deleted_app_ids)
        purged_users = await purge_deleted_users(db, deleted_user_ids)
        purged_orgs = await purge_deleted_organizations(db, deleted_org_ids)
        await db.commit()

    print(
        "Soft delete purge complete. "
        f"retention_days={retention_days} purged_applications={purged_apps} "
        f"purged_users={purged_users} purged_organizations={purged_orgs}"
    )


if __name__ == "__main__":
    asyncio.run(main())
