"""Current-user account settings and preferences router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.dependencies import get_current_user, get_db, get_redis
from app.schemas.organization import CurrentOrganizationResponse
from app.schemas.application import ApplicationListResponse, ApplicationResponse
from app.schemas.user import (
    AccountPreferencesResponse,
    AccountPreferencesUpdate,
    CurrentSessionResponse,
    CurrentUserProfileResponse,
    CurrentUserProfileUpdate,
    MfaCodeVerifyRequest,
    MfaDisableRequest,
    MfaRecoveryCodesRegenerateRequest,
    MfaSetupResponse,
    MfaStatusResponse,
)
from app.services.audit_service import write_audit_event
from app.services.application_service import list_user_assigned_applications
from app.services.mfa_service import (
    MFA_ISSUER_NAME,
    build_totp_uri,
    build_totp_qr_data_url,
    cache_pending_mfa_setup,
    clear_pending_mfa_setup,
    count_recovery_codes,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    generate_recovery_codes,
    get_pending_mfa_setup,
    is_org_mfa_enforced,
    serialize_recovery_codes,
    verify_totp_code,
)
from app.services.notification_service import (
    SECURITY_ALERT_EVENT_KEYS,
    WEEKLY_SUMMARY_EVENT,
    is_notification_enabled,
    send_notification_event,
    set_notification_preference,
)
from app.services.organization_service import get_org_access_tier, get_organization
from app.services.user_service import resolve_rbac, update_current_user_profile
from app.utils.crypto_utils import verify_password

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("/context", response_model=CurrentSessionResponse)
async def get_my_session_context_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current session context for the admin console."""
    user = current_user["user"]
    if user.is_super_admin:
        roles = ["super_admin"]
        permissions = ["*"]
    else:
        roles, permissions = await resolve_rbac(db, user.id, user.org_id)

    return CurrentSessionResponse(
        user_id=user.id,
        email=user.email,
        org_id=user.org_id,
        is_super_admin=bool(user.is_super_admin),
        roles=roles,
        permissions=permissions,
    )


@router.get("/profile", response_model=CurrentUserProfileResponse)
async def get_my_profile_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Return the signed-in user's self-service profile."""
    return CurrentUserProfileResponse.model_validate(current_user["user"])


@router.patch("/profile", response_model=CurrentUserProfileResponse)
async def update_my_profile_endpoint(
    body: CurrentUserProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the signed-in user's self-service profile."""
    current = current_user["user"]
    updates = body.model_dump(exclude_unset=True)

    first_name = current.first_name
    last_name = current.last_name
    profile_image_url = current.profile_image_url

    if "first_name" in updates:
        first_name = updates["first_name"].strip() if updates["first_name"] is not None else None
        if first_name == "":
            first_name = None

    if "last_name" in updates:
        last_name = updates["last_name"].strip() if updates["last_name"] is not None else None
        if last_name == "":
            last_name = None

    if "profile_image_url" in updates:
        profile_image_url = updates["profile_image_url"].strip() if updates["profile_image_url"] is not None else None
        if profile_image_url == "":
            profile_image_url = None

    user = await update_current_user_profile(
        db,
        current_user["user_id"],
        first_name=first_name,
        last_name=last_name,
        profile_image_url=profile_image_url,
    )
    if not user:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "User not found"})

    await write_audit_event(
        db=db,
        event_type="user.profile.updated",
        resource_type="user",
        resource_id=str(user.id),
        org_id=user.org_id,
        actor_id=user.id,
        metadata={
            "updated_fields": sorted(updates.keys()),
            "profile_image_updated": "profile_image_url" in updates,
        },
    )

    return CurrentUserProfileResponse.model_validate(user)


@router.get("/organization", response_model=CurrentOrganizationResponse)
async def get_my_organization_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current user's organization profile for account-facing UI."""
    org = await get_organization(db, current_user["user"].org_id)
    if not org:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Organization not found"})

    settings = org.settings or {}
    return CurrentOrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        display_name=org.display_name,
        status=org.status,
        access_tier=get_org_access_tier(settings),
        verification_status=str(settings.get("verification_status") or "approved"),
    )


@router.get("/applications", response_model=ApplicationListResponse)
async def list_my_applications_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return active applications the current user can access through group assignment."""
    apps = await list_user_assigned_applications(
        db,
        current_user["user"].org_id,
        current_user["user"].id,
    )
    return ApplicationListResponse(
        data=[ApplicationResponse.model_validate(app) for app in apps],
        pagination={
            "total": len(apps),
            "limit": len(apps),
            "has_more": False,
            "next_cursor": None,
        },
    )


@router.get("/preferences", response_model=AccountPreferencesResponse)
async def get_my_preferences_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current user's aggregated account preferences."""
    security_alerts = True
    for event_key in SECURITY_ALERT_EVENT_KEYS:
        if not await is_notification_enabled(db, current_user["user_id"], event_key):
            security_alerts = False
            break

    weekly_summary_emails = await is_notification_enabled(
        db,
        current_user["user_id"],
        WEEKLY_SUMMARY_EVENT,
    )

    return AccountPreferencesResponse(
        security_alerts=security_alerts,
        weekly_summary_emails=weekly_summary_emails,
    )


@router.put("/preferences", response_model=AccountPreferencesResponse)
async def update_my_preferences_endpoint(
    body: AccountPreferencesUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's notification-oriented account preferences."""
    for event_key in SECURITY_ALERT_EVENT_KEYS:
        await set_notification_preference(
            db,
            current_user["user_id"],
            event_key,
            body.security_alerts,
        )

    await set_notification_preference(
        db,
        current_user["user_id"],
        WEEKLY_SUMMARY_EVENT,
        body.weekly_summary_emails,
    )

    await write_audit_event(
        db=db,
        event_type="user.account_preferences.updated",
        resource_type="user",
        resource_id=str(current_user["user_id"]),
        org_id=current_user["org_id"],
        actor_id=current_user["user_id"],
        metadata={
            "security_alerts": body.security_alerts,
            "weekly_summary_emails": body.weekly_summary_emails,
        },
    )

    return AccountPreferencesResponse(
        security_alerts=body.security_alerts,
        weekly_summary_emails=body.weekly_summary_emails,
    )


@router.get("/mfa", response_model=MfaStatusResponse)
async def get_my_mfa_status_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current user's MFA status and whether tenant policy requires it."""
    return MfaStatusResponse(
        enabled=bool(current_user["user"].mfa_enabled and current_user["user"].mfa_secret),
        org_enforced=await is_org_mfa_enforced(db, current_user["user"]),
        recovery_codes_remaining=count_recovery_codes(current_user["user"].mfa_recovery_codes),
    )


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def start_my_mfa_setup_endpoint(
    current_user: dict = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Start TOTP setup for the current user."""
    user = current_user["user"]
    if user.mfa_enabled and user.mfa_secret:
        raise HTTPException(
            status_code=409,
            detail={"error": "mfa_already_enabled", "error_description": "MFA is already enabled for this account."},
        )

    secret = generate_totp_secret()
    otpauth_url = build_totp_uri(secret, user.email)
    await cache_pending_mfa_setup(redis, user.id, secret)
    return MfaSetupResponse(
        manual_entry_key=secret,
        otpauth_url=otpauth_url,
        qr_code_data_url=build_totp_qr_data_url(otpauth_url),
        issuer=MFA_ISSUER_NAME,
        account_name=user.email,
        message="Scan the QR code with Google Authenticator, or enter the setup key manually, then enter the 6-digit code to finish enabling MFA.",
    )


@router.post("/mfa/confirm", response_model=MfaStatusResponse)
async def confirm_my_mfa_setup_endpoint(
    body: MfaCodeVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Confirm a pending MFA setup using a TOTP code."""
    user = current_user["user"]
    secret = await get_pending_mfa_setup(redis, user.id)
    if not secret:
        raise HTTPException(
            status_code=400,
            detail={"error": "mfa_setup_not_started", "error_description": "Start MFA setup again to continue."},
        )

    if not verify_totp_code(secret, body.code):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_mfa_code", "error_description": "Authenticator code is invalid."},
        )

    user.mfa_enabled = True
    user.mfa_secret = encrypt_totp_secret(secret)
    backup_codes = generate_recovery_codes()
    user.mfa_recovery_codes = serialize_recovery_codes(backup_codes)
    user.mfa_recovery_codes_generated_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await clear_pending_mfa_setup(redis, user.id)

    await write_audit_event(
        db=db,
        event_type="user.mfa.enabled",
        resource_type="user",
        resource_id=str(user.id),
        org_id=user.org_id,
        actor_id=user.id,
        metadata={"user_id": str(user.id), "issuer": MFA_ISSUER_NAME},
    )
    await send_notification_event(
        db=db,
        user=user,
        event_key="security.mfa_enabled",
        title="Multi-factor authentication enabled",
        message="Google Authenticator has been enabled for your account.",
    )

    return MfaStatusResponse(
        enabled=True,
        org_enforced=await is_org_mfa_enforced(db, user),
        recovery_codes_remaining=len(backup_codes),
        backup_codes=backup_codes,
    )


@router.post("/mfa/disable", response_model=MfaStatusResponse)
async def disable_my_mfa_endpoint(
    body: MfaDisableRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable MFA for the current user after verifying password and current TOTP code."""
    user = current_user["user"]
    if await is_org_mfa_enforced(db, user):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "mfa_required_by_policy",
                "error_description": "Your organization requires MFA, so it cannot be disabled for this account.",
            },
        )

    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=400,
            detail={"error": "mfa_not_enabled", "error_description": "MFA is not enabled for this account."},
        )

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_credentials", "error_description": "Current password is incorrect."},
        )

    secret = decrypt_totp_secret(user.mfa_secret)
    if not secret or not verify_totp_code(secret, body.code):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_mfa_code", "error_description": "Authenticator code is invalid."},
        )

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = None
    user.mfa_recovery_codes_generated_at = None
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_event(
        db=db,
        event_type="user.mfa.disabled",
        resource_type="user",
        resource_id=str(user.id),
        org_id=user.org_id,
        actor_id=user.id,
        metadata={"user_id": str(user.id)},
    )
    await send_notification_event(
        db=db,
        user=user,
        event_key="security.mfa_disabled",
        title="Multi-factor authentication disabled",
        message="Multi-factor authentication was disabled for your account.",
    )

    return MfaStatusResponse(
        enabled=False,
        org_enforced=await is_org_mfa_enforced(db, user),
        recovery_codes_remaining=0,
    )


@router.post("/mfa/recovery-codes/regenerate", response_model=MfaStatusResponse)
async def regenerate_my_mfa_recovery_codes_endpoint(
    body: MfaRecoveryCodesRegenerateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace recovery codes after verifying current password and authenticator code."""
    user = current_user["user"]
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=400,
            detail={"error": "mfa_not_enabled", "error_description": "MFA must be enabled before recovery codes can be regenerated."},
        )

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_credentials", "error_description": "Current password is incorrect."},
        )

    secret = decrypt_totp_secret(user.mfa_secret)
    if not secret or not verify_totp_code(secret, body.code):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_mfa_code", "error_description": "Authenticator code is invalid."},
        )

    backup_codes = generate_recovery_codes()
    user.mfa_recovery_codes = serialize_recovery_codes(backup_codes)
    user.mfa_recovery_codes_generated_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_event(
        db=db,
        event_type="user.mfa.recovery_codes.regenerated",
        resource_type="user",
        resource_id=str(user.id),
        org_id=user.org_id,
        actor_id=user.id,
        metadata={"user_id": str(user.id), "count": len(backup_codes)},
    )

    return MfaStatusResponse(
        enabled=True,
        org_enforced=await is_org_mfa_enforced(db, user),
        recovery_codes_remaining=len(backup_codes),
        backup_codes=backup_codes,
    )
