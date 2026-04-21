"""Email delivery queue and retry service."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_delivery import EmailDelivery
from app.utils.pagination import encode_cursor, decode_cursor, build_pagination_response


async def queue_email(
    db: AsyncSession,
    to_email: str,
    subject: str,
    html_body: str,
    event_key: str,
    org_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
) -> EmailDelivery:
    """Queue an email for delivery."""
    delivery = EmailDelivery(
        org_id=org_id,
        user_id=user_id,
        event_key=event_key,
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        status="pending",
        attempt_count=0,
        max_attempts=settings.EMAIL_MAX_ATTEMPTS,
        next_retry_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    await db.flush()
    return delivery


async def process_email_queue(db: AsyncSession, limit: int = 20) -> dict[str, int]:
    """Process pending/failed queued emails and return aggregate counters."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EmailDelivery)
        .where(
            EmailDelivery.status.in_(["pending", "failed"]),
            (EmailDelivery.next_retry_at.is_(None) | (EmailDelivery.next_retry_at <= now)),
        )
        .order_by(EmailDelivery.created_at.asc())
        .limit(limit)
    )
    deliveries = list(result.scalars().all())

    sent = 0
    failed = 0
    dead = 0
    for delivery in deliveries:
        ok, err = await _send_smtp(delivery.to_email, delivery.subject, delivery.html_body)
        delivery.attempt_count += 1
        delivery.updated_at = now

        if ok:
            delivery.status = "sent"
            delivery.sent_at = now
            delivery.last_error = None
            sent += 1
            continue

        delivery.last_error = err
        if delivery.attempt_count >= delivery.max_attempts:
            delivery.status = "dead"
            dead += 1
        else:
            delivery.status = "failed"
            delay_seconds = settings.EMAIL_RETRY_BACKOFF_SECONDS * max(1, delivery.attempt_count)
            delivery.next_retry_at = now + timedelta(seconds=delay_seconds)
            failed += 1

    await db.flush()
    return {"queued": len(deliveries), "sent": sent, "failed": failed, "dead": dead}


async def list_email_deliveries(
    db: AsyncSession,
    org_id: Optional[UUID] = None,
    status: Optional[str] = None,
    event_key: Optional[str] = None,
    to_email: Optional[str] = None,
    limit: int = 25,
    cursor: Optional[str] = None,
) -> dict:
    """List queued/sent emails with cursor pagination."""
    query = select(EmailDelivery)
    count_query = select(func.count()).select_from(EmailDelivery)

    if org_id:
        query = query.where(EmailDelivery.org_id == org_id)
        count_query = count_query.where(EmailDelivery.org_id == org_id)
    if status:
        query = query.where(EmailDelivery.status == status)
        count_query = count_query.where(EmailDelivery.status == status)
    if event_key:
        query = query.where(EmailDelivery.event_key.ilike(f"%{event_key}%"))
        count_query = count_query.where(EmailDelivery.event_key.ilike(f"%{event_key}%"))
    if to_email:
        query = query.where(EmailDelivery.to_email.ilike(f"%{to_email}%"))
        count_query = count_query.where(EmailDelivery.to_email.ilike(f"%{to_email}%"))

    if cursor:
        cursor_data = decode_cursor(cursor)
        if cursor_data:
            cursor_created = datetime.fromisoformat(cursor_data["created_at"])
            query = query.where(EmailDelivery.created_at < cursor_created)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(EmailDelivery.created_at.desc()).limit(limit + 1)
    records = list((await db.execute(query)).scalars().all())

    has_more = len(records) > limit
    if has_more:
        records = records[:limit]

    next_cursor = None
    if has_more and records:
        last = records[-1]
        next_cursor = encode_cursor(str(last.id), last.created_at)

    data = [
        {
            "id": str(row.id),
            "org_id": str(row.org_id) if row.org_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "event_key": row.event_key,
            "to_email": row.to_email,
            "subject": row.subject,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "max_attempts": row.max_attempts,
            "next_retry_at": row.next_retry_at,
            "last_error": row.last_error,
            "sent_at": row.sent_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in records
    ]
    return {
        "data": data,
        "pagination": build_pagination_response(data, total, limit, has_more, next_cursor),
    }


async def _send_smtp(to: str, subject: str, html_body: str) -> tuple[bool, Optional[str]]:
    """Send an email via SMTP and return success/error tuple."""
    message = MIMEMultipart("alternative")
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.attach(MIMEText(html_body, "html"))

    password = settings.SMTP_PASS or settings.SMTP_PASSWORD or None
    use_tls = bool(settings.SMTP_USE_TLS)
    start_tls = bool(settings.SMTP_STARTTLS and not use_tls)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=password,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        )
        return True, None
    except Exception as exc:
        return False, str(exc)
