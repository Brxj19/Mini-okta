"""Organizations router: full org CRUD + suspend/activate."""

from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.organization import Organization
from app.models.password_reset import PasswordResetToken

from app.dependencies import get_db, get_redis, require_super_admin, require_permission
from app.schemas.organization import (
    OrganizationCreate, OrganizationUpdate, OrganizationResponse, OrganizationListResponse,
    OrganizationCreateResponse, BootstrapAdminResponse,
    UpgradeRequestCreate, PlanStatusResponse, PendingUpgradeRequestListResponse, PendingUpgradeRequestItem,
    BillingCheckoutCreate, BillingCheckoutComplete, BillingCheckoutSessionResponse,
)
from app.services.billing_service import (
    build_plan_status_payload,
    complete_demo_checkout,
    complete_razorpay_checkout,
    get_billing_provider_info,
    mark_cancel_at_period_end,
    start_demo_checkout,
    start_razorpay_checkout,
)
from app.services.organization_service import (
    create_organization_with_admin, get_organization, list_organizations,
    update_organization, suspend_organization, activate_organization, soft_delete_organization,
    set_organization_access_tier, get_org_access_tier, get_org_limits, slugify_org_name, resolve_available_org_slug,
)
from app.services.user_service import soft_delete_user
from app.services.token_service import revoke_all_user_tokens, get_user_token_jtis
from app.services.browser_session_service import revoke_all_browser_sessions_for_user
from app.services.session_service import revoke_provider_session
from app.models.user import User
import redis.asyncio as aioredis
from app.services.audit_service import write_audit_event
from app.services.notification_service import send_admin_activity_notification, send_notification_event
from app.services.email_service import send_invitation_email
from app.utils.crypto_utils import generate_reset_token
from app.config import settings

router = APIRouter(prefix="/api/v1/admin/organizations", tags=["organizations"])
org_router = APIRouter(prefix="/api/v1/organizations/{org_id}", tags=["organizations"])


def _require_org_admin(current_user: dict) -> None:
    if current_user.get("is_super_admin"):
        return
    normalized_roles = {str(role).lower() for role in (current_user.get("roles") or [])}
    if "org:admin" not in normalized_roles:
        raise HTTPException(
            status_code=403,
            detail={"error": "org_admin_required", "error_description": "Only organization admins can manage billing for this organization."},
        )


@router.post("", response_model=OrganizationCreateResponse, status_code=201)
async def create_org(
    body: OrganizationCreate,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create organization, seed roles, and bootstrap the first org admin."""
    preferred_slug = (body.slug or slugify_org_name(body.name)).strip().lower()
    preferred_slug = preferred_slug.strip("-")
    if not preferred_slug:
        preferred_slug = "org"
    slug = await resolve_available_org_slug(db, preferred_slug)

    try:
        org, bootstrap_admin, temporary_password = await create_organization_with_admin(
            db,
            name=body.name,
            slug=slug,
            admin_email=body.bootstrap_admin.email,
            admin_password=body.bootstrap_admin.password,
            admin_first_name=body.bootstrap_admin.first_name,
            admin_last_name=body.bootstrap_admin.last_name,
            display_name=body.display_name,
            org_settings=body.settings,
        )
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": str(exc)})

    setup_token = generate_reset_token()
    token_record = PasswordResetToken(
        token=setup_token,
        user_id=bootstrap_admin.id,
        purpose="onboarding",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_SETUP_TOKEN_TTL_HOURS),
    )
    db.add(token_record)
    await db.flush()
    await send_invitation_email(
        db,
        bootstrap_admin.email,
        setup_token,
        org_id=org.id,
        user_id=bootstrap_admin.id,
        temporary_password=temporary_password,
    )

    await write_audit_event(
        db, "org.created", "organization", str(org.id),
        org_id=org.id, actor_id=current_user["user_id"],
        metadata={
            "name": org.name,
            "slug": org.slug,
            "bootstrap_admin_email": bootstrap_admin.email,
            "bootstrap_admin_id": str(bootstrap_admin.id),
            "bootstrap_admin_invitation_expires_at": token_record.expires_at.isoformat(),
        }
    )

    return OrganizationCreateResponse(
        **OrganizationResponse.model_validate(org).model_dump(),
        bootstrap_admin=BootstrapAdminResponse.model_validate(bootstrap_admin),
    )


@router.get("", response_model=OrganizationListResponse)
async def list_orgs(
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all organizations (paginated)."""
    result = await list_organizations(db, limit, cursor)
    return OrganizationListResponse(
        data=[OrganizationResponse.model_validate(org) for org in result["data"]],
        pagination=result["pagination"],
    )


@router.get("/pending-upgrade-requests", response_model=PendingUpgradeRequestListResponse)
async def list_pending_upgrade_requests(
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """List pending free-tier upgrade requests submitted by organization admins."""
    org_rows = await db.execute(select(Organization).where(Organization.deleted_at.is_(None)))
    organizations = org_rows.scalars().all()
    items: list[PendingUpgradeRequestItem] = []
    for org in organizations:
        settings = org.settings or {}
        request = settings.get("upgrade_request") if isinstance(settings, dict) else None
        if not isinstance(request, dict):
            continue
        if str(request.get("status")) != "submitted":
            continue
        submitted_at_raw = request.get("submitted_at")
        submitted_at = None
        if isinstance(submitted_at_raw, str):
            try:
                submitted_at = datetime.fromisoformat(submitted_at_raw)
            except ValueError:
                submitted_at = None
        items.append(
            PendingUpgradeRequestItem(
                org_id=org.id,
                org_name=org.display_name or org.name,
                org_slug=org.slug,
                access_tier=get_org_access_tier(settings),
                verification_status=str(settings.get("verification_status") or "pending"),
                submitted_at=submitted_at,
                submitted_by_email=request.get("submitted_by_email"),
                payload=request.get("payload") if isinstance(request.get("payload"), dict) else {},
            )
        )
    items.sort(key=lambda row: row.submitted_at or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return PendingUpgradeRequestListResponse(data=items)


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_org(
    org_id: UUID,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get organization details."""
    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})
    return OrganizationResponse.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_org(
    org_id: UUID,
    body: OrganizationUpdate,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update organization display_name and/or settings."""
    org = await update_organization(db, org_id, body.display_name, body.settings)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})
    return OrganizationResponse.model_validate(org)


@router.post("/{org_id}/suspend", response_model=OrganizationResponse)
async def suspend_org(
    org_id: UUID,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Suspend an organization."""
    org = await suspend_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    await write_audit_event(
        db, "org.suspended", "organization", str(org.id),
        org_id=org.id, actor_id=current_user["user_id"],
        metadata={"org_name": org.name}
    )

    return OrganizationResponse.model_validate(org)


@router.post("/{org_id}/activate", response_model=OrganizationResponse)
async def activate_org(
    org_id: UUID,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Activate an organization."""
    org = await activate_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})
    return OrganizationResponse.model_validate(org)


@router.delete("/{org_id}", status_code=200)
async def delete_org(
    org_id: UUID,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Soft delete an organization."""
    user_rows = await db.execute(
        select(User).where(User.org_id == org_id, User.deleted_at.is_(None))
    )
    users = user_rows.scalars().all()
    for user in users:
        jtis = await get_user_token_jtis(db, user.id)
        await revoke_all_user_tokens(db, user.id, reason="organization_deleted")
        await revoke_all_browser_sessions_for_user(redis, str(user.id))
        for jti in jtis:
            await revoke_provider_session(db=db, redis=redis, jti=jti, reason="organization_deleted")
        await soft_delete_user(db, user.id)

    org = await soft_delete_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})
    return {"message": "Organization deleted"}


@router.post("/{org_id}/verify-enterprise", response_model=OrganizationResponse)
async def verify_organization_enterprise(
    org_id: UUID,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Promote a self-serve organization to verified enterprise access."""
    try:
        org = await set_organization_access_tier(db, org_id, "verified_enterprise")
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": str(exc)})

    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    await write_audit_event(
        db,
        "org.access_tier.verified",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={"org_name": org.name, "access_tier": "verified_enterprise"},
    )
    return OrganizationResponse.model_validate(org)


@router.post("/{org_id}/approve-upgrade-request", response_model=OrganizationResponse)
async def approve_upgrade_request(
    org_id: UUID,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve pending upgrade request and grant full verified enterprise access."""
    try:
        org = await set_organization_access_tier(db, org_id, "verified_enterprise")
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": str(exc)})
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    settings = dict(org.settings or {})
    existing_request = settings.get("upgrade_request")
    if isinstance(existing_request, dict):
        existing_request.update(
            {
                "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "approved_by_user_id": str(current_user["user_id"]),
            }
        )
        settings["upgrade_request"] = existing_request
    settings["verification_status"] = "approved"
    org.settings = settings
    org.updated_at = datetime.now(timezone.utc)

    await write_audit_event(
        db,
        "org.upgrade_request.approved",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={"org_name": org.name, "access_tier": "verified_enterprise"},
    )
    return OrganizationResponse.model_validate(org)


@router.post("/{org_id}/set-limited", response_model=OrganizationResponse)
async def set_organization_limited(
    org_id: UUID,
    current_user: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set an organization back to limited self-serve mode."""
    try:
        org = await set_organization_access_tier(db, org_id, "limited")
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": str(exc)})

    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    await write_audit_event(
        db,
        "org.access_tier.limited",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={"org_name": org.name, "access_tier": "limited"},
    )
    return OrganizationResponse.model_validate(org)


@org_router.get("/plan-status", response_model=PlanStatusResponse)
async def get_plan_status(
    org_id: UUID,
    current_user: dict = Depends(require_permission("org:read")),
    db: AsyncSession = Depends(get_db),
):
    """Return current organization tier and upgrade request status for in-app display."""
    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})
    return PlanStatusResponse(**build_plan_status_payload(org))


@org_router.post("/billing/checkout-session", response_model=BillingCheckoutSessionResponse)
async def create_billing_checkout_session(
    org_id: UUID,
    body: BillingCheckoutCreate,
    current_user: dict = Depends(require_permission("org:read")),
    db: AsyncSession = Depends(get_db),
):
    """Start a paid plan checkout session for an organization admin."""
    _require_org_admin(current_user)
    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    provider = str(get_billing_provider_info()["provider"]).strip().lower()
    if provider == "razorpay":
        try:
            next_settings, checkout = await start_razorpay_checkout(
                org.settings,
                org=org,
                plan_code=body.plan_code,
                payment_method=body.payment_method,
                actor_email=str(current_user.get("email") or ""),
            )
        except ValueError as exc:
            raise HTTPException(400, detail={"error": "checkout_failed", "error_description": str(exc)})
    else:
        try:
            next_settings, checkout = start_demo_checkout(
                org.settings,
                plan_code=body.plan_code,
                payment_method=body.payment_method,
            )
        except ValueError as exc:
            raise HTTPException(400, detail={"error": "checkout_failed", "error_description": str(exc)})

    org.settings = next_settings
    org.updated_at = datetime.now(timezone.utc)
    await write_audit_event(
        db,
        "org.billing.checkout.started",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={"org_name": org.name, "plan_code": body.plan_code, "provider": checkout.get("provider")},
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org.id,
        actor_user_id=current_user["user_id"],
        title="Billing checkout started",
        message=f"{current_user.get('email', 'An admin')} started checkout for the {str(body.plan_code).title()} plan.",
        event_key="org.billing.checkout.started",
    )
    return BillingCheckoutSessionResponse(
        checkout=checkout,
        plan_status=PlanStatusResponse(**build_plan_status_payload(org)),
    )


@org_router.post("/billing/checkout-complete", response_model=PlanStatusResponse)
async def complete_billing_checkout(
    org_id: UUID,
    body: BillingCheckoutComplete,
    current_user: dict = Depends(require_permission("org:read")),
    db: AsyncSession = Depends(get_db),
):
    """Finalize a billing checkout and activate the paid organization plan."""
    _require_org_admin(current_user)
    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    provider = str(body.provider or "").strip().lower()
    try:
        if provider == "razorpay":
            next_settings = complete_razorpay_checkout(
                org.settings,
                session_id=body.session_id,
                razorpay_order_id=str(body.razorpay_order_id or ""),
                razorpay_payment_id=str(body.razorpay_payment_id or ""),
                razorpay_signature=str(body.razorpay_signature or ""),
                payment_method=body.payment_method,
            )
        else:
            next_settings = complete_demo_checkout(
                org.settings,
                session_id=body.session_id,
                payment_method=body.payment_method,
            )
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "payment_verification_failed", "error_description": str(exc)})

    org.settings = next_settings
    org.updated_at = datetime.now(timezone.utc)
    plan_status = build_plan_status_payload(org)
    await write_audit_event(
        db,
        "org.billing.checkout.completed",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={
            "org_name": org.name,
            "plan_code": plan_status["current_plan_code"],
            "provider": provider or "demo",
        },
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org.id,
        actor_user_id=current_user["user_id"],
        title="Subscription activated",
        message=f"{current_user.get('email', 'An admin')} activated the {plan_status['current_plan']['name']} plan for {org.display_name or org.name}.",
        event_key="org.billing.checkout.completed",
    )
    await send_notification_event(
        db=db,
        user=current_user["user"],
        event_key="billing.payment_success",
        title="Subscription payment successful",
        message=f"Your payment was received and the {plan_status['current_plan']['name']} plan is now active for {org.display_name or org.name}.",
    )
    return PlanStatusResponse(**plan_status)


@org_router.post("/billing/cancel-at-period-end", response_model=PlanStatusResponse)
async def cancel_subscription_at_period_end(
    org_id: UUID,
    current_user: dict = Depends(require_permission("org:read")),
    db: AsyncSession = Depends(get_db),
):
    """Mark the current paid subscription to end after the current billing cycle."""
    _require_org_admin(current_user)
    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})
    try:
        org.settings = mark_cancel_at_period_end(org.settings, cancel=True)
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "subscription_not_active", "error_description": str(exc)})
    org.updated_at = datetime.now(timezone.utc)
    await write_audit_event(
        db,
        "org.subscription.cancel_at_period_end",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={"org_name": org.name},
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org.id,
        actor_user_id=current_user["user_id"],
        title="Subscription set to cancel",
        message=f"{current_user.get('email', 'An admin')} scheduled the current subscription to end at the close of this billing cycle.",
        event_key="org.subscription.cancel_at_period_end",
    )
    await send_notification_event(
        db=db,
        user=current_user["user"],
        event_key="billing.cancel_scheduled",
        title="Subscription will end at period close",
        message="Your subscription is now set to cancel at the end of the current billing cycle.",
    )
    return PlanStatusResponse(**build_plan_status_payload(org))


@org_router.post("/billing/resume", response_model=PlanStatusResponse)
async def resume_subscription(
    org_id: UUID,
    current_user: dict = Depends(require_permission("org:read")),
    db: AsyncSession = Depends(get_db),
):
    """Resume the current subscription and clear cancel-at-period-end."""
    _require_org_admin(current_user)
    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})
    try:
        org.settings = mark_cancel_at_period_end(org.settings, cancel=False)
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "subscription_not_active", "error_description": str(exc)})
    org.updated_at = datetime.now(timezone.utc)
    await write_audit_event(
        db,
        "org.subscription.resumed",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={"org_name": org.name},
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org.id,
        actor_user_id=current_user["user_id"],
        title="Subscription resumed",
        message=f"{current_user.get('email', 'An admin')} resumed the organization's subscription renewal.",
        event_key="org.subscription.resumed",
    )
    return PlanStatusResponse(**build_plan_status_payload(org))


@org_router.post("/upgrade-request", response_model=PlanStatusResponse)
async def submit_upgrade_request(
    org_id: UUID,
    body: UpgradeRequestCreate,
    current_user: dict = Depends(require_permission("org:read")),
    db: AsyncSession = Depends(get_db),
):
    """Submit a free-tier upgrade request form for super-admin verification."""
    if not current_user.get("is_super_admin"):
        normalized_roles = {str(role).lower() for role in (current_user.get("roles") or [])}
        if "org:admin" not in normalized_roles:
            raise HTTPException(
                status_code=403,
                detail={"error": "org_admin_required", "error_description": "Only organization admins can submit upgrade requests."},
            )

    if not body.agree_to_terms:
        raise HTTPException(
            status_code=400,
            detail={"error": "terms_required", "error_description": "Please confirm the declaration to submit the request."},
        )

    org = await get_organization(db, org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    settings = dict(org.settings or {})
    if get_org_access_tier(settings) == "verified_enterprise":
        raise HTTPException(
            status_code=400,
            detail={"error": "already_verified", "error_description": "Organization already has verified enterprise access."},
        )

    settings["verification_status"] = "pending_review"
    settings["upgrade_request"] = {
        "status": "submitted",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "submitted_by_user_id": str(current_user["user_id"]),
        "submitted_by_email": current_user.get("email"),
        "payload": {
            "company_name": body.company_name,
            "company_website": body.company_website,
            "company_size": body.company_size,
            "primary_use_case": body.primary_use_case,
            "expected_monthly_users": body.expected_monthly_users,
            "requested_features": body.requested_features,
            "billing_contact_name": body.billing_contact_name,
            "billing_contact_email": body.billing_contact_email,
            "notes": body.notes,
            "agreed_to_terms": body.agree_to_terms,
        },
    }
    org.settings = settings
    org.updated_at = datetime.now(timezone.utc)

    await write_audit_event(
        db,
        "org.upgrade_request.submitted",
        "organization",
        str(org.id),
        org_id=org.id,
        actor_id=current_user["user_id"],
        metadata={"org_name": org.name, "submitted_by": current_user.get("email")},
    )

    return PlanStatusResponse(
        org_id=org.id,
        org_name=org.display_name or org.name,
        org_slug=org.slug,
        access_tier=get_org_access_tier(settings),
        verification_status=str(settings.get("verification_status") or "pending_review"),
        limits=get_org_limits(settings),
        upgrade_request=settings.get("upgrade_request"),
    )
