"""Notification preference, in-app feed, and event dispatch service."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.branding import PRODUCT_NAME
from app.models.email_delivery import EmailDelivery
from app.models.group import GroupMember, GroupRole
from app.models.notification import Notification
from app.models.notification_preference import NotificationPreference
from app.models.role import Role
from app.models.user import User
from app.services.email_delivery_service import process_email_queue, queue_email
from app.services.email_templates import account_notification_html, weekly_summary_email_html

SECURITY_ALERT_EVENT_KEYS = (
    "security.password_reset",
    "security.password_expired",
    "security.login_failure",
    "security.mfa_enabled",
    "security.mfa_disabled",
    "security.new_browser_login",
)

WEEKLY_SUMMARY_EVENT = "summary.weekly_digest"

DEFAULT_NOTIFICATION_EVENTS = {
    "account.created",
    "account.suspended",
    "account.activated",
    "account.unlocked",
    "account.role_changed",
    "account.invitation_accepted",
    "app.assignment",
    "billing.payment_success",
    "billing.renewal_reminder",
    "billing.subscription_expired",
    "billing.cancel_scheduled",
    "billing.cancel_reminder",
    *SECURITY_ALERT_EVENT_KEYS,
    "admin.activity",
}

SUPPORTED_NOTIFICATION_EVENTS = {
    *DEFAULT_NOTIFICATION_EVENTS,
    WEEKLY_SUMMARY_EVENT,
}


def _preference_event_key(event_key: str) -> str:
    """Map custom admin/org activity events onto preference-aware categories."""
    normalized = str(event_key or "").strip()
    if normalized in SUPPORTED_NOTIFICATION_EVENTS:
        return normalized
    if normalized.startswith(("org.", "app.", "group.", "user.")):
        return "admin.activity"
    return normalized


async def create_in_app_notification(
    db: AsyncSession,
    user: User,
    event_key: str,
    title: str,
    message: str,
) -> Notification:
    """Create an in-app notification row."""
    notification = Notification(
        org_id=user.org_id,
        user_id=user.id,
        event_key=event_key,
        title=title,
        message=message,
    )
    db.add(notification)
    await db.flush()
    return notification


async def list_user_notifications(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    unread_only: bool = False,
) -> tuple[list[Notification], int]:
    """Return newest notifications and unread count for a user."""
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read.is_(False))
    query = query.order_by(Notification.created_at.desc()).limit(limit)

    result = await db.execute(query)
    notifications = list(result.scalars().all())

    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read.is_(False),
        )
    )
    unread_count = int(unread_result.scalar() or 0)
    return notifications, unread_count


async def mark_notification_read(
    db: AsyncSession,
    user_id: UUID,
    notification_id: UUID,
) -> Optional[Notification]:
    """Mark a single notification as read for the user."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        return None

    if not notification.read:
        notification.read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.flush()
    return notification


async def mark_all_notifications_read(db: AsyncSession, user_id: UUID) -> int:
    """Mark all unread notifications as read for a user."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read.is_(False),
        )
        .values(read=True, read_at=now, updated_at=now)
    )
    await db.flush()
    return result.rowcount or 0


async def delete_notification(
    db: AsyncSession,
    user_id: UUID,
    notification_id: UUID,
) -> bool:
    """Delete one notification if it belongs to the user."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        return False

    await db.delete(notification)
    await db.flush()
    return True


async def clear_user_notifications(db: AsyncSession, user_id: UUID) -> int:
    """Delete all notifications for a user."""
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    notifications = list(result.scalars().all())
    for notification in notifications:
        await db.delete(notification)
    await db.flush()
    return len(notifications)


async def is_notification_enabled(
    db: AsyncSession,
    user_id: UUID,
    event_key: str,
) -> bool:
    """Resolve preference for event; defaults to enabled for known events."""
    preference_key = _preference_event_key(event_key)
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.event_key == preference_key,
        )
    )
    pref = result.scalar_one_or_none()
    if pref is None:
        return preference_key in DEFAULT_NOTIFICATION_EVENTS
    return bool(pref.enabled)


async def set_notification_preference(
    db: AsyncSession,
    user_id: UUID,
    event_key: str,
    enabled: bool,
) -> NotificationPreference:
    """Create/update a per-user preference row."""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.event_key == event_key,
        )
    )
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = NotificationPreference(user_id=user_id, event_key=event_key, enabled=enabled)
        db.add(pref)
    else:
        pref.enabled = enabled
    await db.flush()
    return pref


async def send_notification_event(
    db: AsyncSession,
    user: User,
    event_key: str,
    title: str,
    message: str,
) -> bool:
    """Create an in-app notification and email only when the event is enabled."""
    if not await is_notification_enabled(db, user.id, event_key):
        return False

    await create_in_app_notification(db, user, event_key, title, message)

    html = account_notification_html(title, message)
    await queue_email(
        db=db,
        to_email=user.email,
        subject=title,
        html_body=html,
        event_key=event_key,
        org_id=user.org_id,
        user_id=user.id,
    )
    await process_email_queue(db, limit=10)
    return True


def _weekly_summary_label(event_key: str) -> str:
    labels = {
        "account.created": "New accounts created",
        "account.suspended": "Accounts suspended",
        "account.activated": "Accounts activated",
        "account.unlocked": "Accounts unlocked",
        "account.role_changed": "Role changes",
        "security.password_reset": "Password resets",
        "security.password_expired": "Password expirations",
        "security.login_failure": "Failed sign-in attempts",
        "security.mfa_enabled": "MFA enabled",
        "security.mfa_disabled": "MFA disabled",
        "security.new_browser_login": "New browser sign-ins",
        "billing.payment_success": "Successful subscription payments",
        "billing.renewal_reminder": "Subscription renewal reminders",
        "billing.subscription_expired": "Subscription expirations",
        "billing.cancel_scheduled": "Subscription cancellations scheduled",
        "billing.cancel_reminder": "Upcoming subscription cancellations",
        "app.assignment": "New application assignments",
        "account.invitation_accepted": "Accepted invitations",
        "admin.activity": "Admin activity",
        "org.self_serve_signup": "Self-serve organization signups",
        "org.billing.checkout.started": "Billing checkouts started",
        "org.billing.checkout.completed": "Billing checkouts completed",
        "org.subscription.cancel_at_period_end": "Subscription cancellations scheduled",
        "org.subscription.resumed": "Subscription renewals resumed",
    }
    return labels.get(event_key, event_key.replace(".", " ").replace("_", " ").title())


async def send_weekly_summary_email(
    db: AsyncSession,
    user: User,
    window_end: Optional[datetime] = None,
    window_days: int = 7,
    ignore_recent_digest: bool = False,
) -> bool:
    """Queue/send a weekly summary email when enabled and there is recent activity."""
    if not await is_notification_enabled(db, user.id, WEEKLY_SUMMARY_EVENT):
        return False

    end_at = window_end or datetime.now(timezone.utc)
    start_at = end_at - timedelta(days=window_days)

    if not ignore_recent_digest:
        existing_digest = await db.execute(
            select(EmailDelivery.id).where(
                EmailDelivery.user_id == user.id,
                EmailDelivery.event_key == WEEKLY_SUMMARY_EVENT,
                EmailDelivery.status == "sent",
                EmailDelivery.sent_at.is_not(None),
                EmailDelivery.sent_at >= start_at,
            )
        )
        if existing_digest.scalar_one_or_none():
            return False

    summary_result = await db.execute(
        select(Notification.event_key, func.count(Notification.id))
        .where(
            Notification.user_id == user.id,
            Notification.created_at >= start_at,
            Notification.created_at < end_at,
        )
        .group_by(Notification.event_key)
        .order_by(func.count(Notification.id).desc(), Notification.event_key.asc())
    )
    event_counts = list(summary_result.all())

    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.read.is_(False),
        )
    )
    unread_count = int(unread_result.scalar() or 0)

    if not event_counts and unread_count == 0:
        return False

    summary_items = [
        {"label": _weekly_summary_label(event_key), "count": int(count)}
        for event_key, count in event_counts[:6]
    ]
    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
    period_label = f"{start_at.strftime('%b %d')} to {end_at.strftime('%b %d')}"

    await queue_email(
        db=db,
        to_email=user.email,
        subject=f"Your {PRODUCT_NAME} weekly summary",
        html_body=weekly_summary_email_html(user_name, period_label, summary_items, unread_count),
        event_key=WEEKLY_SUMMARY_EVENT,
        org_id=user.org_id,
        user_id=user.id,
    )
    await process_email_queue(db, limit=10)
    return True


async def list_admin_recipients(
    db: AsyncSession,
    org_id: Optional[UUID],
    actor_user_id: Optional[UUID] = None,
) -> list[User]:
    """Get platform and org-level admin recipients, excluding actor if provided."""
    recipients: dict[UUID, User] = {}

    super_admin_result = await db.execute(
        select(User).where(
            User.is_super_admin.is_(True),
            User.deleted_at.is_(None),
        )
    )
    for user in super_admin_result.scalars().all():
        if actor_user_id and user.id == actor_user_id:
            continue
        recipients[user.id] = user

    if org_id:
        org_admin_result = await db.execute(
            select(User)
            .distinct()
            .join(GroupMember, GroupMember.user_id == User.id)
            .join(GroupRole, GroupRole.group_id == GroupMember.group_id)
            .join(Role, Role.id == GroupRole.role_id)
            .where(
                User.org_id == org_id,
                User.deleted_at.is_(None),
                Role.name == "org:admin",
            )
        )
        for user in org_admin_result.scalars().all():
            if actor_user_id and user.id == actor_user_id:
                continue
            recipients[user.id] = user

    return list(recipients.values())


async def list_org_admin_recipients(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: Optional[UUID] = None,
) -> list[User]:
    """Get organization admin recipients only, excluding actor if provided."""
    org_admin_result = await db.execute(
        select(User)
        .distinct()
        .join(GroupMember, GroupMember.user_id == User.id)
        .join(GroupRole, GroupRole.group_id == GroupMember.group_id)
        .join(Role, Role.id == GroupRole.role_id)
        .where(
            User.org_id == org_id,
            User.deleted_at.is_(None),
            Role.name == "org:admin",
        )
    )
    recipients: list[User] = []
    for user in org_admin_result.scalars().all():
        if actor_user_id and user.id == actor_user_id:
            continue
        recipients.append(user)
    return recipients


async def send_admin_activity_notification(
    db: AsyncSession,
    org_id: Optional[UUID],
    title: str,
    message: str,
    event_key: str = "admin.activity",
    actor_user_id: Optional[UUID] = None,
) -> int:
    """Send an in-app/email event to platform admins and org admins."""
    recipients = await list_admin_recipients(db=db, org_id=org_id, actor_user_id=actor_user_id)
    for recipient in recipients:
        await send_notification_event(
            db=db,
            user=recipient,
            event_key=event_key,
            title=title,
            message=message,
        )
    return len(recipients)


async def send_org_admin_notification(
    db: AsyncSession,
    org_id: UUID,
    title: str,
    message: str,
    event_key: str,
    actor_user_id: Optional[UUID] = None,
) -> int:
    """Send an in-app/email event to organization admins only."""
    recipients = await list_org_admin_recipients(db=db, org_id=org_id, actor_user_id=actor_user_id)
    for recipient in recipients:
        await send_notification_event(
            db=db,
            user=recipient,
            event_key=event_key,
            title=title,
            message=message,
        )
    return len(recipients)
