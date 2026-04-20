"""Email service for verification, reset, and onboarding invitations."""

from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.branding import PRODUCT_NAME
from app.config import settings
from app.utils.crypto_utils import generate_email_verification_token
from app.services.email_templates import (
    verification_email_html,
    password_reset_email_html,
    invitation_email_html,
)
from app.services.email_delivery_service import queue_email, process_email_queue


async def send_verification_email(
    db: AsyncSession,
    user_id: str,
    email: str,
    org_id: Optional[UUID] = None,
) -> None:
    """Queue/send email verification link to user."""
    token = generate_email_verification_token(user_id, settings.ADMIN_SECRET)
    verify_url = f"{settings.ISSUER_URL}/api/v1/verify-email?token={token}"
    html_body = verification_email_html(verify_url)

    await queue_email(
        db=db,
        to_email=email,
        subject="Verify your email address",
        html_body=html_body,
        event_key="security.email_verification",
        org_id=org_id,
        user_id=UUID(user_id) if user_id else None,
    )
    await process_email_queue(db, limit=10)


async def send_password_reset_email(
    db: AsyncSession,
    email: str,
    reset_token: str,
    org_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
) -> None:
    """Queue/send password reset link to user."""
    reset_url = f"{settings.ADMIN_CONSOLE_URL}/password-reset/confirm?token={reset_token}"
    html_body = password_reset_email_html(reset_url)

    await queue_email(
        db=db,
        to_email=email,
        subject="Password Reset Request",
        html_body=html_body,
        event_key="security.password_reset",
        org_id=org_id,
        user_id=user_id,
    )
    await process_email_queue(db, limit=10)


async def send_invitation_email(
    db: AsyncSession,
    email: str,
    setup_token: str,
    org_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    temporary_password: Optional[str] = None,
) -> None:
    """Queue/send first-time onboarding invitation email."""
    setup_url = f"{settings.ADMIN_CONSOLE_URL}/setup-password?token={setup_token}"
    html_body = invitation_email_html(setup_url, settings.INVITATION_LINK_TTL_HOURS, temporary_password)

    await queue_email(
        db=db,
        to_email=email,
        subject=f"You're invited to {PRODUCT_NAME}",
        html_body=html_body,
        event_key="account.created",
        org_id=org_id,
        user_id=user_id,
    )
    await process_email_queue(db, limit=10)
