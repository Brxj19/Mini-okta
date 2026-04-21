"""Email delivery queue visibility and processing endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission, require_super_admin
from app.services.email_delivery_service import list_email_deliveries, process_email_queue

admin_router = APIRouter(prefix="/api/v1/admin/email-deliveries", tags=["email-deliveries"])
org_router = APIRouter(prefix="/api/v1/organizations/{org_id}/email-deliveries", tags=["email-deliveries"])


@admin_router.get("")
async def list_email_deliveries_admin(
    status: Optional[str] = Query(None),
    event_key: Optional[str] = Query(None),
    to_email: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all email deliveries across organizations (super admin only)."""
    return await list_email_deliveries(db, None, status, event_key, to_email, limit, cursor)


@admin_router.post("/process")
async def process_queue_admin(
    limit: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Manually process pending/failed email deliveries."""
    result = await process_email_queue(db, limit)
    return {
        "message": (
            f"Processed {result['queued']} queued email(s): "
            f"{result['sent']} sent, {result['failed']} failed, {result['dead']} dead."
        ),
        **result,
    }


@org_router.get("")
async def list_email_deliveries_org(
    org_id: UUID,
    status: Optional[str] = Query(None),
    event_key: Optional[str] = Query(None),
    to_email: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    """List email deliveries for an organization."""
    return await list_email_deliveries(db, org_id, status, event_key, to_email, limit, cursor)
