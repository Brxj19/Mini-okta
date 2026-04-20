"""Auth router: login, authorize, token, logout, userinfo, verify-email, password-reset, OIDC discovery."""

import json
import base64
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, get_redis, get_current_user
from app.models.authorization_code import AuthorizationCode
from app.models.organization import Organization
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.auth_service import (
    authenticate_primary_credentials,
    authorize_and_issue_tokens,
    AuthError,
    issue_login_success,
    resolve_application_access,
)
from app.services.auth_page_renderer import (
    login_error_page,
    render_logged_out_page,
    render_authorize_backup_codes_page,
    render_authorize_login_page,
    render_authorize_mfa_page,
    render_authorize_transition_page,
)
from app.services.browser_session_service import (
    attach_browser_session_cookie,
    clear_browser_session_cookie,
    create_browser_session,
    get_browser_session,
    read_browser_session_id,
    revoke_all_browser_sessions_for_user,
    revoke_browser_session,
    touch_browser_session,
)
from app.services.mfa_service import (
    MFA_ISSUER_NAME,
    build_totp_uri,
    build_totp_qr_data_url,
    count_recovery_codes,
    create_mfa_challenge,
    decrypt_totp_secret,
    delete_mfa_challenge,
    encrypt_totp_secret,
    generate_recovery_codes,
    generate_totp_secret,
    get_mfa_challenge,
    get_mfa_requirement,
    serialize_recovery_codes,
    verify_and_consume_recovery_code,
    verify_totp_code,
)
from app.services.user_service import get_user, get_user_by_email, resolve_rbac, verify_user_email, update_password, get_user_groups
from app.services.notification_service import send_admin_activity_notification, send_notification_event, send_org_admin_notification
from app.services.session_service import register_provider_session, revoke_provider_session
from app.services.token_service import (
    get_token_by_jti, revoke_token, issue_id_token, issue_refresh_token,
    issue_access_token, revoke_token_family, revoke_all_user_tokens, get_user_token_jtis,
)
from app.services.application_service import get_application_by_client_id
from app.services.audit_service import write_audit_event
from app.services.email_service import send_password_reset_email
from app.services.organization_service import (
    build_self_serve_settings,
    create_organization_with_admin,
    get_org_access_tier,
    get_organization_by_slug,
)
from app.schemas.signup import (
    OrganizationSelfServeSignupRequest,
    OrganizationSelfServeSignupResponse,
    PublicSignupOrganizationSummary,
    PublicSignupAdminSummary,
)
from app.schemas.user import LoginMfaVerifyRequest, LoginRequest, LoginResponse, PasswordResetRequest, PasswordResetConfirm
from app.schemas.token import TokenResponse, UserInfoResponse, TokenIntrospectResponse
from app.utils.jwt_utils import verify_token, build_jwks, build_audience_claims
from app.utils.crypto_utils import (
    verify_password, pkce_verify, generate_auth_code,
    verify_email_verification_token, generate_reset_token, validate_password_policy, hash_password,
)

from sqlalchemy import select, update

router = APIRouter(prefix="/api/v1", tags=["auth"])


async def invalidate_active_reset_tokens(db: AsyncSession, user_id: UUID) -> None:
    """Expire any outstanding password reset tokens for the user."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.purpose == "reset",
            PasswordResetToken.used.is_(False),
            PasswordResetToken.expires_at > now,
        )
        .values(expires_at=now)
    )


def _slugify_org_name(name: str) -> str:
    """Convert organization name to a safe slug."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return cleaned or "org"


async def _resolve_available_org_slug(db: AsyncSession, preferred_slug: str) -> str:
    """Return preferred slug if free, otherwise append numeric suffix."""
    candidate = preferred_slug
    suffix = 2
    while True:
        existing = await get_organization_by_slug(db, candidate)
        if not existing:
            return candidate
        candidate = f"{preferred_slug}-{suffix}"
        suffix += 1


async def _finalize_authorization_success(
    *,
    db: AsyncSession,
    user: User,
    auth_state: dict,
    state: str,
    request: Request,
 ) -> str:
    """Create authorization code and return the final client redirect URL."""
    code = generate_auth_code()
    scopes = auth_state.get("scope", "openid").split()

    auth_code = AuthorizationCode(
        code=code,
        user_id=user.id,
        client_id=auth_state["client_id"],
        org_id=user.org_id,
        redirect_uri=auth_state["redirect_uri"],
        scopes=scopes,
        code_challenge=auth_state.get("code_challenge"),
        nonce=auth_state.get("nonce"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(auth_code)
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_event(
        db,
        "user.login.success",
        "user",
        str(user.id),
        org_id=user.org_id,
        actor_id=user.id,
        metadata={
            "ip_address": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "client_id": auth_state["client_id"],
            "login_flow": "oidc_authorize",
        },
    )

    redirect_url = f"{auth_state['redirect_uri']}?code={code}&state={state}"
    return redirect_url


async def _attach_browser_sso_cookie(
    response: Response,
    *,
    redis: aioredis.Redis,
    user: User,
    request: Request,
    client_id: str = "admin-console",
    token_jti: str = "",
) -> None:
    browser_session_id = await create_browser_session(
        redis,
        user_id=str(user.id),
        org_id=str(user.org_id),
        email=user.email,
        client_id=client_id,
        token_jti=token_jti,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    attach_browser_session_cookie(response, browser_session_id)


def _append_state_to_redirect_url(redirect_url: str, state: Optional[str]) -> str:
    """Append OIDC logout state to a validated redirect URL."""
    if not state:
        return redirect_url

    parsed = urlsplit(redirect_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_pairs.append(("state", state))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query_pairs), parsed.fragment))


def _extract_client_id_from_hint_claims(claims: dict) -> Optional[str]:
    """Resolve a client_id from standard OIDC token audiences."""
    audience = claims.get("aud")
    if isinstance(audience, list):
        return str(audience[0]) if audience else None
    if audience:
        return str(audience)
    return None


async def _resolve_logout_redirect(
    *,
    db: AsyncSession,
    client_id: Optional[str],
    post_logout_redirect_uri: Optional[str],
    hint_claims: Optional[dict],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Validate logout redirect target against the registered client application."""
    effective_client_id = client_id or (_extract_client_id_from_hint_claims(hint_claims or {}) if hint_claims else None)
    if not post_logout_redirect_uri:
        return None, effective_client_id, None
    if not effective_client_id:
        raise HTTPException(
            400,
            detail={
                "error": "invalid_request",
                "error_description": "client_id or id_token_hint is required when post_logout_redirect_uri is provided",
            },
        )

    app = await get_application_by_client_id(db, effective_client_id)
    if not app or app.status != "active":
        raise HTTPException(400, detail={"error": "invalid_client", "error_description": "Unknown or inactive client"})

    if post_logout_redirect_uri not in (app.post_logout_redirect_uris or []):
        raise HTTPException(
            400,
            detail={
                "error": "invalid_post_logout_redirect_uri",
                "error_description": "post_logout_redirect_uri does not match any registered logout redirect URIs",
            },
        )

    return post_logout_redirect_uri, effective_client_id, app.name


async def _attempt_authorize_with_browser_session(
    *,
    request: Request,
    db: AsyncSession,
    redis: aioredis.Redis,
    state: str,
    auth_state: dict,
) -> Optional[HTMLResponse]:
    browser_session_id = read_browser_session_id(request)
    browser_session = await get_browser_session(redis, browser_session_id)
    if not browser_session:
        return None

    user = await get_user(db, UUID(str(browser_session.get("user_id"))))
    if not user or user.status != "active":
        await revoke_browser_session(redis, browser_session_id)
        response = HTMLResponse(
            content=render_authorize_login_page(state=state, auth_state=auth_state),
            status_code=200,
        )
        clear_browser_session_cookie(response)
        return response

    roles, _ = await resolve_rbac(db, user.id, user.org_id)
    user_groups = await get_user_groups(db, user.id)
    app_access = await resolve_application_access(
        db,
        user,
        str(auth_state["client_id"]),
        roles,
        user_groups,
    )
    if not app_access["access_allowed"]:
        response = HTMLResponse(
            content=login_error_page(
                state,
                app_access["access_error"] or "You are not authorized to access this application. Contact your administrator.",
            ),
            status_code=403,
        )
        attach_browser_session_cookie(response, str(browser_session_id))
        await touch_browser_session(redis, str(browser_session_id), browser_session)
        return response

    await redis.delete(f"auth_state:{state}")
    redirect_url = await _finalize_authorization_success(
        db=db,
        user=user,
        auth_state=auth_state,
        state=state,
        request=request,
    )
    response = HTMLResponse(
        content=render_authorize_transition_page(
            redirect_url=redirect_url,
            auth_state=auth_state,
        ),
        status_code=200,
    )
    attach_browser_session_cookie(response, str(browser_session_id))
    await touch_browser_session(redis, str(browser_session_id), browser_session)
    return response


# ─── POST /signup/organization ──────────────────────────────────────
@router.post("/signup/organization", response_model=OrganizationSelfServeSignupResponse, status_code=201)
async def self_serve_signup_organization(
    body: OrganizationSelfServeSignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Self-serve public signup: create org + first admin in limited mode."""
    existing_user = await get_user_by_email(db, body.admin_email)
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "email_already_registered",
                "error_description": "That admin email is already registered. Sign in or use password reset.",
            },
        )

    preferred_slug = (body.organization_slug or _slugify_org_name(body.organization_name)).strip().lower()
    preferred_slug = re.sub(r"-{2,}", "-", preferred_slug).strip("-")
    if not re.fullmatch(r"[a-z0-9\\-]{2,100}", preferred_slug or ""):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_slug",
                "error_description": "Organization slug must contain only lowercase letters, numbers, and hyphens.",
            },
        )

    org_name_taken = await db.execute(
        select(Organization).where(Organization.name == body.organization_name.strip(), Organization.deleted_at.is_(None))
    )
    if org_name_taken.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "organization_name_taken",
                "error_description": "An organization with this name already exists.",
            },
        )

    slug = await _resolve_available_org_slug(db, preferred_slug)

    try:
        org, admin_user, _ = await create_organization_with_admin(
            db=db,
            name=body.organization_name.strip(),
            slug=slug,
            admin_email=body.admin_email,
            admin_password=body.admin_password,
            admin_first_name=body.admin_first_name,
            admin_last_name=body.admin_last_name,
            display_name=body.organization_name.strip(),
            org_settings=build_self_serve_settings(),
        )
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_signup_data", "error_description": str(exc)})

    await write_audit_event(
        db=db,
        event_type="org.self_serve_signup",
        resource_type="organization",
        resource_id=str(org.id),
        org_id=org.id,
        actor_id=admin_user.id,
        metadata={
            "org_name": org.name,
            "org_slug": org.slug,
            "signup_origin": "self_serve",
            "access_tier": get_org_access_tier(org.settings),
        },
    )

    await send_admin_activity_notification(
        db=db,
        org_id=org.id,
        actor_user_id=admin_user.id,
        title="Self-serve organization created",
        message=f"{admin_user.email} created organization {org.display_name or org.name} on the free self-serve tier.",
        event_key="org.self_serve_signup",
    )

    return OrganizationSelfServeSignupResponse(
        message="Organization created in free self-serve mode. Sign in as org admin and upgrade to a paid plan whenever you want higher limits and full access.",
        organization=PublicSignupOrganizationSummary(
            id=org.id,
            name=org.name,
            slug=org.slug,
            status=org.status,
            access_tier=get_org_access_tier(org.settings),
            verification_status=str((org.settings or {}).get("verification_status") or "pending"),
        ),
        admin_user=PublicSignupAdminSummary(
            id=admin_user.id,
            email=admin_user.email,
            first_name=admin_user.first_name,
            last_name=admin_user.last_name,
        ),
    )


# ─── POST /login ─────────────────────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
async def login_endpoint(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Authenticate user and return ID token."""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    try:
        user = await authenticate_primary_credentials(db, redis, body.email, body.password, ip, ua)
        mfa_requirement = await get_mfa_requirement(db, user)

        if mfa_requirement == "verify":
            challenge_token = await create_mfa_challenge(
                redis,
                user_id=user.id,
                email=user.email,
                flow="login",
                challenge_type="verify",
                client_id="admin-console",
                ip_address=ip,
                user_agent=ua,
            )
            await db.commit()
            return LoginResponse(
                mfa_required=True,
                challenge_token=challenge_token,
                message="Enter the 6-digit code from Google Authenticator to continue.",
            )

        if mfa_requirement == "setup":
            secret = generate_totp_secret()
            otpauth_url = build_totp_uri(secret, user.email)
            challenge_token = await create_mfa_challenge(
                redis,
                user_id=user.id,
                email=user.email,
                flow="login",
                challenge_type="setup",
                client_id="admin-console",
                ip_address=ip,
                user_agent=ua,
                pending_secret=secret,
            )
            await db.commit()
            return LoginResponse(
                mfa_setup_required=True,
                challenge_token=challenge_token,
                manual_entry_key=secret,
                otpauth_url=otpauth_url,
                qr_code_data_url=build_totp_qr_data_url(otpauth_url),
                message="Set up Google Authenticator to finish signing in.",
            )

        result = await issue_login_success(db, redis, user, ip, ua)
        await db.commit()
        session_jti = str(result.pop("session_jti", "") or "")
        response = JSONResponse(content=result)
        await _attach_browser_sso_cookie(
            response,
            redis=redis,
            user=user,
            request=request,
            client_id="admin-console",
            token_jti=session_jti,
        )
        return response
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail={"error": e.error, "error_description": e.description})


@router.post("/login/mfa/verify", response_model=LoginResponse)
async def login_mfa_verify_endpoint(
    body: LoginMfaVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Complete admin-console login after MFA verification or setup."""
    challenge = await get_mfa_challenge(redis, body.challenge_token)
    if not challenge or challenge.get("flow") != "login":
        raise HTTPException(
            status_code=400,
            detail={"error": "mfa_challenge_expired", "error_description": "The MFA challenge expired. Sign in again."},
        )

    user = await get_user(db, UUID(challenge["user_id"]))
    if not user or user.status != "active":
        raise HTTPException(
            status_code=401,
            detail={"error": "account_inactive", "error_description": "Account is no longer available for sign-in."},
        )

    challenge_type = str(challenge.get("challenge_type") or "verify")
    issued_backup_codes: list[str] = []
    if challenge_type == "setup":
        pending_secret = str(challenge.get("pending_secret") or "")
        if not pending_secret or not verify_totp_code(pending_secret, body.code):
            await write_audit_event(
                db,
                "user.mfa.challenge.failure",
                "user",
                str(user.id),
                org_id=user.org_id,
                actor_id=user.id,
                metadata={"flow": "login", "challenge_type": "setup"},
            )
            await db.commit()
            raise HTTPException(
                status_code=401,
                detail={"error": "invalid_mfa_code", "error_description": "Authenticator code is invalid."},
            )

        user.mfa_enabled = True
        user.mfa_secret = encrypt_totp_secret(pending_secret)
        issued_backup_codes = generate_recovery_codes()
        user.mfa_recovery_codes = serialize_recovery_codes(issued_backup_codes)
        user.mfa_recovery_codes_generated_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await write_audit_event(
            db,
            "user.mfa.enabled",
            "user",
            str(user.id),
            org_id=user.org_id,
            actor_id=user.id,
            metadata={"flow": "login", "issuer": MFA_ISSUER_NAME},
        )
    else:
        secret = decrypt_totp_secret(user.mfa_secret or "")
        totp_valid = bool(secret and verify_totp_code(secret, body.code))
        if not totp_valid:
            recovery_code_valid, updated_recovery_codes, remaining_codes = verify_and_consume_recovery_code(
                user.mfa_recovery_codes,
                body.code,
            )
            if recovery_code_valid:
                user.mfa_recovery_codes = updated_recovery_codes
                user.updated_at = datetime.now(timezone.utc)
                await db.flush()
                await write_audit_event(
                    db,
                    "user.mfa.recovery_code.used",
                    "user",
                    str(user.id),
                    org_id=user.org_id,
                    actor_id=user.id,
                    metadata={"flow": "login", "remaining_recovery_codes": remaining_codes},
                )
            else:
                await write_audit_event(
                    db,
                    "user.mfa.challenge.failure",
                    "user",
                    str(user.id),
                    org_id=user.org_id,
                    actor_id=user.id,
                    metadata={"flow": "login", "challenge_type": "verify"},
                )
                await db.commit()
                raise HTTPException(
                    status_code=401,
                    detail={"error": "invalid_mfa_code", "error_description": "Authenticator or backup code is invalid."},
                )

    await delete_mfa_challenge(redis, body.challenge_token)
    result = await issue_login_success(
        db=db,
        redis=redis,
        user=user,
        ip_address=str(challenge.get("ip_address") or ""),
        user_agent=str(challenge.get("user_agent") or ""),
        client_id=str(challenge.get("client_id") or "admin-console"),
    )
    await write_audit_event(
        db,
        "user.mfa.challenge.success",
        "user",
        str(user.id),
        org_id=user.org_id,
        actor_id=user.id,
        metadata={"flow": "login", "challenge_type": challenge_type},
    )
    result["backup_codes"] = issued_backup_codes
    result["recovery_codes_remaining"] = count_recovery_codes(user.mfa_recovery_codes)
    await db.commit()
    session_jti = str(result.pop("session_jti", "") or "")
    response = JSONResponse(content=result)
    await _attach_browser_sso_cookie(
        response,
        redis=redis,
        user=user,
        request=request,
        client_id=str(challenge.get("client_id") or "admin-console"),
        token_jti=session_jti,
    )
    return response


# ─── GET /authorize ──────────────────────────────────────────────────
@router.get("/authorize")
async def authorize_endpoint(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query("openid"),
    state: str = Query(...),
    nonce: Optional[str] = Query(None),
    code_challenge: Optional[str] = Query(None),
    code_challenge_method: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """OIDC Authorization endpoint — validates client and redirects to login page."""
    # Validate response_type
    if response_type != "code":
        raise HTTPException(400, detail={"error": "unsupported_response_type", "error_description": "Only response_type=code is supported"})

    # Validate client
    app = await get_application_by_client_id(db, client_id)
    if not app or app.status != "active":
        raise HTTPException(400, detail={"error": "invalid_client", "error_description": "Unknown or inactive client"})

    # Exact match redirect_uri
    if redirect_uri not in (app.redirect_uris or []):
        raise HTTPException(400, detail={"error": "invalid_redirect_uri", "error_description": "redirect_uri does not match any registered URIs"})

    requested_scopes = [item for item in scope.split() if item]
    if not requested_scopes:
        requested_scopes = ["openid"]

    invalid_scopes = [item for item in requested_scopes if item not in (app.allowed_scopes or [])]
    if invalid_scopes:
        raise HTTPException(
            400,
            detail={
                "error": "invalid_scope",
                "error_description": f"Requested scopes are not allowed for this application: {', '.join(invalid_scopes)}",
            },
        )

    # PKCE required for spa/native
    if app.app_type in ("spa", "native") and not code_challenge:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": "code_challenge is required for SPA and native applications"})

    # code_challenge_method must be S256
    if code_challenge and code_challenge_method and code_challenge_method != "S256":
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": "Only S256 code_challenge_method is supported"})

    # Store pending auth state in Redis
    auth_state = {
        "client_id": client_id,
        "client_name": app.name,
        "client_logo_url": app.logo_url,
        "redirect_uri": redirect_uri,
        "scope": " ".join(requested_scopes),
        "requested_scopes": requested_scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method or ("S256" if code_challenge else None),
    }
    await redis.set(f"auth_state:{state}", json.dumps(auth_state), ex=600)

    browser_sso_response = await _attempt_authorize_with_browser_session(
        request=request,
        db=db,
        redis=redis,
        state=state,
        auth_state=auth_state,
    )
    if browser_sso_response is not None:
        await db.commit()
        return browser_sso_response

    return RedirectResponse(url=f"/api/v1/authorize/login-page?state={state}", status_code=302)


# ─── GET /authorize/login-page ───────────────────────────────────────
@router.get("/authorize/login-page", response_class=HTMLResponse)
async def authorize_login_page(
    request: Request,
    state: str = Query(...),
    error_message: Optional[str] = Query(None, alias="error"),
    db: AsyncSession = Depends(get_db),
):
    """Serve the HTML login form for the authorization flow."""
    redis = await get_redis()
    state_data = await redis.get(f"auth_state:{state}")
    if not state_data:
        raise HTTPException(400, detail={"error": "invalid_state", "error_description": "Authorization state not found or expired"})

    auth_state = json.loads(state_data)
    if not error_message:
        browser_sso_response = await _attempt_authorize_with_browser_session(
            request=request,
            db=db,
            redis=redis,
            state=state,
            auth_state=auth_state,
        )
        if browser_sso_response is not None:
            await db.commit()
            return browser_sso_response

    return HTMLResponse(
        content=render_authorize_login_page(
            state=state,
            auth_state=auth_state,
            error_message=error_message,
        )
    )


# ─── POST /authorize/submit ──────────────────────────────────────────
@router.post("/authorize/submit")
async def authorize_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    state: str = Form(...),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Process the authorization login form submission."""
    # Retrieve pending auth state
    state_data = await redis.get(f"auth_state:{state}")
    if not state_data:
        raise HTTPException(400, detail={"error": "invalid_state", "error_description": "Authorization state not found or expired"})

    auth_state = json.loads(state_data)

    try:
        user = await authenticate_primary_credentials(
            db=db,
            redis=redis,
            email=email,
            password=password,
            ip_address=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
            client_id=str(auth_state["client_id"]),
        )
    except AuthError as exc:
        await db.commit()
        return HTMLResponse(content=login_error_page(state, exc.description), status_code=exc.status_code)

    # Authorize this user for the requested application before issuing auth code.
    roles, _ = await resolve_rbac(db, user.id, user.org_id)
    user_groups = await get_user_groups(db, user.id)
    app_access = await resolve_application_access(
        db,
        user,
        str(auth_state["client_id"]),
        roles,
        user_groups,
    )
    if not app_access["access_allowed"]:
        return HTMLResponse(
            content=login_error_page(
                state,
                app_access["access_error"] or "You are not authorized to access this application. Contact your administrator.",
            ),
            status_code=403,
        )

    mfa_requirement = await get_mfa_requirement(db, user)
    if mfa_requirement in {"verify", "setup"}:
        pending_secret = generate_totp_secret() if mfa_requirement == "setup" else None
        qr_code_data_url = None
        if pending_secret:
            qr_code_data_url = build_totp_qr_data_url(build_totp_uri(pending_secret, user.email))
        challenge_token = await create_mfa_challenge(
            redis,
            user_id=user.id,
            email=user.email,
            flow="authorize",
            challenge_type="setup" if mfa_requirement == "setup" else "verify",
            client_id=str(auth_state["client_id"]),
            ip_address=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
            state=state,
            pending_secret=pending_secret,
        )
        await db.commit()
        return HTMLResponse(
            content=render_authorize_mfa_page(
                state=state,
                challenge_token=challenge_token,
                auth_state=auth_state,
                challenge_type="setup" if mfa_requirement == "setup" else "verify",
                manual_entry_key=pending_secret,
                qr_code_data_url=qr_code_data_url,
            ),
            status_code=200,
        )

    # Clean up state
    await redis.delete(f"auth_state:{state}")

    redirect_url = await _finalize_authorization_success(
        db=db,
        user=user,
        auth_state=auth_state,
        state=state,
        request=request,
    )
    await db.commit()
    response = HTMLResponse(
        content=render_authorize_transition_page(
            redirect_url=redirect_url,
            auth_state=auth_state,
        ),
        status_code=200,
    )
    await _attach_browser_sso_cookie(response, redis=redis, user=user, request=request)
    return response


@router.post("/authorize/mfa-submit")
async def authorize_mfa_submit(
    request: Request,
    challenge_token: str = Form(...),
    state: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Complete MFA challenge for authorize/login-page flow."""
    auth_state_raw = await redis.get(f"auth_state:{state}")
    if not auth_state_raw:
        raise HTTPException(400, detail={"error": "invalid_state", "error_description": "Authorization state not found or expired"})
    auth_state = json.loads(auth_state_raw)

    challenge = await get_mfa_challenge(redis, challenge_token)
    if not challenge or challenge.get("flow") != "authorize" or challenge.get("state") != state:
        return HTMLResponse(content=login_error_page(state, "MFA challenge expired. Sign in again."), status_code=400)

    user = await get_user(db, UUID(challenge["user_id"]))
    if not user or user.status != "active":
        return HTMLResponse(content=login_error_page(state, "Account is no longer available."), status_code=401)

    challenge_type = str(challenge.get("challenge_type") or "verify")
    issued_backup_codes: list[str] = []
    if challenge_type == "setup":
        pending_secret = str(challenge.get("pending_secret") or "")
        if not pending_secret or not verify_totp_code(pending_secret, code):
            await write_audit_event(
                db,
                "user.mfa.challenge.failure",
                "user",
                str(user.id),
                org_id=user.org_id,
                actor_id=user.id,
                metadata={"flow": "authorize", "challenge_type": "setup"},
            )
            return HTMLResponse(
                content=render_authorize_mfa_page(
                    state=state,
                    challenge_token=challenge_token,
                    auth_state=auth_state,
                    challenge_type="setup",
                    manual_entry_key=pending_secret,
                    qr_code_data_url=build_totp_qr_data_url(build_totp_uri(pending_secret, user.email)) if pending_secret else None,
                    error_message="Authenticator code is invalid.",
                ),
                status_code=401,
            )
        user.mfa_enabled = True
        user.mfa_secret = encrypt_totp_secret(pending_secret)
        issued_backup_codes = generate_recovery_codes()
        user.mfa_recovery_codes = serialize_recovery_codes(issued_backup_codes)
        user.mfa_recovery_codes_generated_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await write_audit_event(
            db,
            "user.mfa.enabled",
            "user",
            str(user.id),
            org_id=user.org_id,
            actor_id=user.id,
            metadata={"flow": "authorize", "issuer": MFA_ISSUER_NAME},
        )
    else:
        secret = decrypt_totp_secret(user.mfa_secret or "")
        totp_valid = bool(secret and verify_totp_code(secret, code))
        if not totp_valid:
            recovery_code_valid, updated_recovery_codes, remaining_codes = verify_and_consume_recovery_code(
                user.mfa_recovery_codes,
                code,
            )
            if recovery_code_valid:
                user.mfa_recovery_codes = updated_recovery_codes
                user.updated_at = datetime.now(timezone.utc)
                await db.flush()
                await write_audit_event(
                    db,
                    "user.mfa.recovery_code.used",
                    "user",
                    str(user.id),
                    org_id=user.org_id,
                    actor_id=user.id,
                    metadata={"flow": "authorize", "remaining_recovery_codes": remaining_codes},
                )
            else:
                await write_audit_event(
                    db,
                    "user.mfa.challenge.failure",
                    "user",
                    str(user.id),
                    org_id=user.org_id,
                    actor_id=user.id,
                    metadata={"flow": "authorize", "challenge_type": "verify"},
                )
                return HTMLResponse(
                    content=render_authorize_mfa_page(
                        state=state,
                        challenge_token=challenge_token,
                        auth_state=auth_state,
                        challenge_type="verify",
                        error_message="Authenticator or backup code is invalid.",
                    ),
                    status_code=401,
                )

    await write_audit_event(
        db,
        "user.mfa.challenge.success",
        "user",
        str(user.id),
        org_id=user.org_id,
        actor_id=user.id,
        metadata={"flow": "authorize", "challenge_type": challenge_type},
    )

    await delete_mfa_challenge(redis, challenge_token)
    await redis.delete(f"auth_state:{state}")
    redirect_url = await _finalize_authorization_success(
        db=db,
        user=user,
        auth_state=auth_state,
        state=state,
        request=request,
    )
    if issued_backup_codes:
        await db.commit()
        response = HTMLResponse(
            content=render_authorize_backup_codes_page(
                redirect_url=redirect_url,
                auth_state=auth_state,
                backup_codes=issued_backup_codes,
            ),
            status_code=200,
        )
        await _attach_browser_sso_cookie(response, redis=redis, user=user, request=request)
        return response
    await db.commit()
    response = HTMLResponse(
        content=render_authorize_transition_page(
            redirect_url=redirect_url,
            auth_state=auth_state,
        ),
        status_code=200,
    )
    await _attach_browser_sso_cookie(response, redis=redis, user=user, request=request)
    return response


# ─── POST /token ─────────────────────────────────────────────────────
@router.post("/token")
async def token_endpoint(
    request: Request,
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Token endpoint supporting authorization_code, refresh_token, and client_credentials grants."""

    if grant_type == "authorization_code":
        return await _handle_auth_code_grant(db, redis, request, code, redirect_uri, client_id, code_verifier)
    elif grant_type == "refresh_token":
        return await _handle_refresh_token_grant(db, redis, request, refresh_token, client_id)
    elif grant_type == "client_credentials":
        return await _handle_client_credentials_grant(db, client_id, client_secret, scope)
    else:
        raise HTTPException(400, detail={"error": "unsupported_grant_type", "error_description": f"Grant type '{grant_type}' is not supported"})


async def _handle_auth_code_grant(db, redis, request, code, redirect_uri, client_id, code_verifier):
    """Handle authorization_code grant type."""
    if not code or not redirect_uri or not client_id:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": "code, redirect_uri, and client_id are required"})

    now = datetime.now(timezone.utc)

    # Fetch auth code
    result = await db.execute(select(AuthorizationCode).where(AuthorizationCode.code == code))
    auth_code = result.scalar_one_or_none()

    if not auth_code:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Invalid authorization code"})

    # Verify not used
    if auth_code.used_at is not None:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Authorization code has already been used"})

    # Verify not expired
    if auth_code.expires_at < now:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Authorization code has expired"})

    # Verify redirect_uri matches
    if auth_code.redirect_uri != redirect_uri:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "redirect_uri does not match"})

    # Verify client_id matches
    if auth_code.client_id != client_id:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "client_id does not match"})

    # PKCE verification
    if auth_code.code_challenge:
        if not code_verifier:
            raise HTTPException(400, detail={"error": "invalid_request", "error_description": "code_verifier is required"})
        if not pkce_verify(code_verifier, auth_code.code_challenge):
            raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "PKCE verification failed"})

    # Atomically consume the code so concurrent exchanges cannot both succeed.
    consume_result = await db.execute(
        update(AuthorizationCode)
        .where(
            AuthorizationCode.code == code,
            AuthorizationCode.used_at.is_(None),
        )
        .values(used_at=now)
    )
    if consume_result.rowcount != 1:
        await db.rollback()
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Authorization code has already been used"})

    auth_code.used_at = now
    await db.flush()

    # Get user
    user = await get_user(db, auth_code.user_id)
    if not user:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "User not found"})

    # Get app config
    app = await get_application_by_client_id(db, client_id)

    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    try:
        result = await authorize_and_issue_tokens(
            db=db,
            redis=redis,
            user=user,
            client_id=client_id,
            scopes=auth_code.scopes or ["openid"],
            nonce=auth_code.nonce,
            id_token_lifetime=app.id_token_lifetime if app else None,
            access_token_lifetime=app.access_token_lifetime if app else None,
            refresh_token_enabled=app.refresh_token_enabled if app else False,
            ip_address=ip,
            user_agent=ua,
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.error, "error_description": exc.description})
    if not result:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Token exchange failed"})
    await db.commit()
    return JSONResponse(content=result)


async def _handle_refresh_token_grant(db, redis, request, refresh_token_str, client_id):
    """Handle refresh_token grant type with rotation and reuse detection."""
    if not refresh_token_str or not client_id:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": "refresh_token and client_id are required"})

    # Look up token by jti
    token_record = await get_token_by_jti(db, refresh_token_str)
    if not token_record or token_record.token_type != "refresh":
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Invalid refresh token"})

    # Reuse detection: if already revoked → revoke entire family
    if token_record.revoked:
        await revoke_token_family(db, token_record.user_id, token_record.client_id)
        await db.commit()
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Refresh token reuse detected — all tokens revoked"})

    # Verify not expired
    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Refresh token expired"})

    # Verify client_id matches
    if token_record.client_id != client_id:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "client_id does not match"})

    # Rotate: revoke old refresh token
    await revoke_token(db, refresh_token_str, reason="rotated")

    # Get user
    user = await get_user(db, token_record.user_id)
    if not user:
        raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "User not found"})

    # Resolve RBAC
    roles, permissions = await resolve_rbac(db, user.id, user.org_id)
    user_groups = await get_user_groups(db, user.id)
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
    app = await get_application_by_client_id(db, client_id)
    access = await resolve_application_access(db, user, client_id, roles, user_groups)
    if not access["access_allowed"]:
        await revoke_token_family(db, user.id, client_id)
        await db.commit()
        raise HTTPException(403, detail={"error": "access_denied", "error_description": access["access_error"]})
    authorized_app_groups = access["authorized_app_groups"]
    app_roles = access["app_roles"]

    # Issue new ID Token
    id_token_str, jti, expires_in = await issue_id_token(
        db=db,
        user_id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        name=name,
        given_name=user.first_name or "",
        family_name=user.last_name or "",
        org_id=user.org_id,
        is_super_admin=user.is_super_admin,
        client_id=client_id,
        roles=roles,
        permissions=permissions,
        groups=[group["name"] for group in user_groups],
        group_ids=[str(group["id"]) for group in user_groups],
        app_groups=[group["name"] for group in authorized_app_groups],
        app_group_ids=[str(group["id"]) for group in authorized_app_groups],
        app_roles=app_roles,
        scopes=token_record.scopes,
    )

    await register_provider_session(
        db=db,
        redis=redis,
        jti=jti,
        user_id=str(user.id),
        client_id=client_id,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        expires_in=expires_in,
    )

    # Issue new refresh token
    new_refresh = await issue_refresh_token(db, user.id, user.org_id, client_id, token_record.scopes)

    result = {
        "id_token": id_token_str,
        "refresh_token": new_refresh,
        "token_type": "Bearer",
        "expires_in": expires_in,
    }

    await db.commit()
    return JSONResponse(content=result)


async def _handle_client_credentials_grant(db, client_id, client_secret, scope_str):
    """Handle client_credentials grant type (M2M)."""
    if not client_id or not client_secret:
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": "client_id and client_secret are required"})

    app = await get_application_by_client_id(db, client_id)
    if not app or app.status != "active":
        raise HTTPException(401, detail={"error": "invalid_client", "error_description": "Unknown or inactive client"})

    if app.app_type != "m2m":
        raise HTTPException(400, detail={"error": "unauthorized_client", "error_description": "client_credentials grant only allowed for M2M applications"})

    # Verify client_secret
    if not app.client_secret or not verify_password(client_secret, app.client_secret):
        raise HTTPException(401, detail={"error": "invalid_client", "error_description": "Invalid client credentials"})

    scopes = scope_str.split() if scope_str else app.allowed_scopes or []

    at_str, at_jti, at_exp = await issue_access_token(
        db=db,
        sub=client_id,
        org_id=app.org_id,
        is_super_admin=False,
        client_id=client_id,
        email=None,
        email_verified=None,
        name=None,
        given_name=None,
        family_name=None,
        scopes=scopes,
        roles=[],
        permissions=[],
        groups=[],
        group_ids=[],
        app_groups=[],
        app_group_ids=[],
        app_roles=[],
        lifetime=app.access_token_lifetime,
    )

    await db.commit()
    return JSONResponse(content={
        "access_token": at_str,
        "token_type": "Bearer",
        "expires_in": at_exp,
    })


# ─── POST /logout ────────────────────────────────────────────────────
@router.get("/logout")
async def oidc_logout_endpoint(
    request: Request,
    client_id: Optional[str] = Query(None),
    post_logout_redirect_uri: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    id_token_hint: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """OIDC-style end-session endpoint for browser redirects from client applications."""
    hint_claims: Optional[dict] = None
    if id_token_hint:
        try:
            hint_claims = verify_token(id_token_hint)
        except JWTError as exc:
            raise HTTPException(
                400,
                detail={"error": "invalid_token_hint", "error_description": f"id_token_hint is invalid: {str(exc)}"},
            )

    redirect_url, effective_client_id, client_name = await _resolve_logout_redirect(
        db=db,
        client_id=client_id,
        post_logout_redirect_uri=post_logout_redirect_uri,
        hint_claims=hint_claims,
    )

    if hint_claims:
        hinted_jti = hint_claims.get("jti")
        hinted_sub = hint_claims.get("sub")
        hinted_org_id = hint_claims.get("org_id")
        if hinted_jti:
            await revoke_provider_session(db=db, redis=redis, jti=str(hinted_jti), reason="oidc_logout")
        if hinted_sub and hinted_org_id:
            try:
                hinted_user_id = UUID(str(hinted_sub))
                hinted_org_uuid = UUID(str(hinted_org_id))
            except (TypeError, ValueError):
                hinted_user_id = None
                hinted_org_uuid = None
            if hinted_user_id and hinted_org_uuid:
                await write_audit_event(
                    db,
                    "user.logout",
                    "user",
                    str(hinted_user_id),
                    org_id=hinted_org_uuid,
                    actor_id=hinted_user_id,
                    metadata={
                        "logout_flow": "oidc_end_session",
                        "client_id": effective_client_id or _extract_client_id_from_hint_claims(hint_claims),
                    },
                )

    await revoke_browser_session(redis, read_browser_session_id(request))
    final_redirect_url = _append_state_to_redirect_url(redirect_url, state)
    response = HTMLResponse(
        content=render_logged_out_page(
            redirect_url=final_redirect_url,
            client_name=client_name,
        ),
        status_code=200,
    )
    clear_browser_session_cookie(response)
    await db.commit()
    return response


@router.post("/logout", status_code=204)
async def logout_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Logout: revoke ID Token and clear session."""
    jti = current_user.get("jti")

    if jti:
        await revoke_provider_session(db=db, redis=redis, jti=jti, reason="logout")

        await write_audit_event(
            db, "token.revoked", "token", jti,
            org_id=current_user["org_id"], actor_id=current_user["user_id"],
            metadata={"jti": jti, "revoke_reason": "logout"}
        )

    await revoke_browser_session(redis, read_browser_session_id(request))

    response = Response(status_code=204)
    clear_browser_session_cookie(response)
    return response


# ─── GET /userinfo ────────────────────────────────────────────────────
@router.get("/userinfo", response_model=UserInfoResponse)
async def userinfo_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """UserInfo endpoint: returns current user data with fresh RBAC."""
    user = current_user["user"]
    roles, permissions = await resolve_rbac(db, user.id, user.org_id)
    audience_claims = build_audience_claims(
        client_id=str(current_user["claims"].get("aud") or ""),
        roles=roles,
        permissions=permissions,
        groups=[],
        group_ids=[],
        app_groups=list(current_user["claims"].get("app_groups") or []),
        app_group_ids=list(current_user["claims"].get("app_group_ids") or []),
        app_roles=list(current_user["claims"].get("app_roles") or []),
    )
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email

    return UserInfoResponse(
        sub=str(user.id),
        email=user.email,
        email_verified=user.email_verified,
        name=name,
        given_name=user.first_name or "",
        family_name=user.last_name or "",
        roles=audience_claims["roles"],
        permissions=audience_claims["permissions"],
        app_groups=audience_claims["app_groups"],
        app_group_ids=audience_claims["app_group_ids"],
        app_roles=audience_claims["app_roles"],
        org_id=str(user.org_id),
    )


# ─── OIDC Discovery ──────────────────────────────────────────────────
@router.get("/.well-known/openid-configuration")
async def openid_configuration():
    """OpenID Connect Discovery document."""
    return JSONResponse(content={
        "issuer": settings.ISSUER_URL,
        "authorization_endpoint": f"{settings.ISSUER_URL}/api/v1/authorize",
        "token_endpoint": f"{settings.ISSUER_URL}/api/v1/token",
        "userinfo_endpoint": f"{settings.ISSUER_URL}/api/v1/userinfo",
        "end_session_endpoint": f"{settings.ISSUER_URL}/api/v1/logout",
        "jwks_uri": f"{settings.ISSUER_URL}/api/v1/.well-known/jwks.json",
        "scopes_supported": ["openid", "profile", "email"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
        "code_challenge_methods_supported": ["S256"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    })


@router.get("/.well-known/jwks.json")
async def jwks_endpoint():
    """JWKS endpoint: publishes all active public keys."""
    return JSONResponse(content=build_jwks())


# ─── POST /introspect ────────────────────────────────────────────────
@router.post("/introspect")
async def introspect_endpoint(
    request: Request,
    token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Token introspection endpoint. Requires HTTP Basic auth (client_id:client_secret)."""
    # Parse Basic auth
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Basic "):
        raise HTTPException(401, detail={"error": "invalid_client", "error_description": "Basic authentication required"})

    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        basic_client_id, basic_secret = decoded.split(":", 1)
    except Exception:
        raise HTTPException(401, detail={"error": "invalid_client", "error_description": "Invalid Basic auth header"})

    # Verify client
    app = await get_application_by_client_id(db, basic_client_id)
    if not app or not app.client_secret:
        raise HTTPException(401, detail={"error": "invalid_client", "error_description": "Unknown client"})

    if not verify_password(basic_secret, app.client_secret):
        raise HTTPException(401, detail={"error": "invalid_client", "error_description": "Invalid client credentials"})

    # Decode token to get jti
    try:
        claims = verify_token(token)
    except JWTError:
        return JSONResponse(content={"active": False})

    jti = claims.get("jti")
    if not jti:
        return JSONResponse(content={"active": False})

    token_record = await get_token_by_jti(db, jti)
    if not token_record:
        return JSONResponse(content={"active": False})

    if token_record.revoked or token_record.expires_at < datetime.now(timezone.utc):
        return JSONResponse(content={"active": False})

    # Get fresh RBAC
    user_id = claims.get("sub")
    roles, permissions = [], []
    if user_id:
        try:
            roles, permissions = await resolve_rbac(db, UUID(user_id), token_record.org_id)
        except Exception:
            pass

    return JSONResponse(content={
        "active": True,
        "sub": claims.get("sub"),
        "org_id": str(token_record.org_id),
        "scope": " ".join(token_record.scopes),
        "roles": roles,
        "permissions": permissions,
        "exp": claims.get("exp"),
        "client_id": token_record.client_id,
        "token_type": token_record.token_type,
    })


# ─── GET /verify-email ───────────────────────────────────────────────
@router.get("/verify-email")
async def verify_email_endpoint(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Verify user email via HMAC-SHA256 signed token."""
    valid, result = verify_email_verification_token(token, settings.ADMIN_SECRET)

    if not valid:
        raise HTTPException(400, detail={"error": "invalid_token", "error_description": result})

    user_id = result
    user = await verify_user_email(db, UUID(user_id))
    if not user:
        raise HTTPException(404, detail={"error": "user_not_found", "error_description": "User not found"})

    return RedirectResponse(url=f"{settings.ISSUER_URL}/login?verified=true", status_code=302)


# ─── POST /password-reset/request ────────────────────────────────────
@router.post("/password-reset/request")
async def password_reset_request(
    body: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a password reset for an existing account."""
    user = await get_user_by_email(db, body.email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail={"error": "email_not_found", "error_description": "No account was found for that email address."},
        )

    await invalidate_active_reset_tokens(db, user.id)
    reset_token = generate_reset_token()
    token_record = PasswordResetToken(
        token=reset_token,
        user_id=user.id,
        purpose="reset",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(token_record)
    await db.flush()
    await send_password_reset_email(db, body.email, reset_token, org_id=user.org_id, user_id=user.id)

    return JSONResponse(content={"message": "Password reset link sent. Check your inbox to continue."})


# ─── POST /password-reset/confirm ────────────────────────────────────
@router.post("/password-reset/confirm")
async def password_reset_confirm(
    body: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Confirm password reset with token and new password."""
    # Look up token
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == body.token)
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(400, detail={"error": "invalid_token", "error_description": "Invalid reset token"})

    if token_record.used:
        raise HTTPException(400, detail={"error": "token_used", "error_description": "Reset token has already been used"})

    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, detail={"error": "token_expired", "error_description": "Reset token has expired"})

    # Validate password policy
    valid, error = validate_password_policy(body.new_password)
    if not valid:
        raise HTTPException(400, detail={"error": "invalid_password", "error_description": error})

    if token_record.purpose != "reset":
        raise HTTPException(400, detail={"error": "invalid_token", "error_description": "Token purpose mismatch"})

    # Update password
    try:
        user = await update_password(db, token_record.user_id, body.new_password)
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_password", "error_description": str(exc)})
    if not user:
        raise HTTPException(404, detail={"error": "user_not_found", "error_description": "User not found"})

    # Mark token as used
    token_record.used = True
    token_record.used_at = datetime.now(timezone.utc)
    await db.flush()
    await invalidate_active_reset_tokens(db, token_record.user_id)

    # Revoke all existing tokens
    jtis = await get_user_token_jtis(db, token_record.user_id)
    await revoke_all_user_tokens(db, token_record.user_id, reason="password_reset")
    await revoke_all_browser_sessions_for_user(redis, str(token_record.user_id))

    # Clear Redis sessions
    for jti in jtis:
        await revoke_provider_session(db=db, redis=redis, jti=jti, reason="password_reset")

    # Audit
    await write_audit_event(
        db, "user.password_reset", "user", str(token_record.user_id),
        actor_id=token_record.user_id,
        metadata={"user_id": str(token_record.user_id)}
    )
    await send_notification_event(
        db=db,
        user=user,
        event_key="security.password_reset",
        title="Password reset completed",
        message="Your account password was reset successfully. If this was not you, contact support immediately.",
    )

    return JSONResponse(content={"message": "Password has been reset successfully"})


# ─── POST /password-setup/confirm ────────────────────────────────────
@router.post("/password-setup/confirm")
async def password_setup_confirm(
    body: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Complete first-time account setup with onboarding token."""
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == body.token)
    )
    token_record = result.scalar_one_or_none()
    if not token_record:
        raise HTTPException(400, detail={"error": "invalid_token", "error_description": "Invalid setup token"})
    if token_record.used:
        raise HTTPException(400, detail={"error": "token_used", "error_description": "Setup token has already been used"})
    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, detail={"error": "token_expired", "error_description": "Setup token has expired"})
    if token_record.purpose != "onboarding":
        raise HTTPException(400, detail={"error": "invalid_token", "error_description": "Token purpose mismatch"})

    valid, error = validate_password_policy(body.new_password)
    if not valid:
        raise HTTPException(400, detail={"error": "invalid_password", "error_description": error})

    try:
        user = await update_password(db, token_record.user_id, body.new_password)
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_password", "error_description": str(exc)})
    if not user:
        raise HTTPException(404, detail={"error": "user_not_found", "error_description": "User not found"})
    user.email_verified = True
    user.invitation_expires_at = None
    user.updated_at = datetime.now(timezone.utc)
    token_record.used = True
    token_record.used_at = datetime.now(timezone.utc)
    await db.flush()

    # Revoke any previously issued sessions/tokens before first real sign-in.
    jtis = await get_user_token_jtis(db, token_record.user_id)
    await revoke_all_user_tokens(db, token_record.user_id, reason="password_setup")
    await revoke_all_browser_sessions_for_user(redis, str(token_record.user_id))
    for jti in jtis:
        await revoke_provider_session(db=db, redis=redis, jti=jti, reason="password_setup")

    await write_audit_event(
        db, "user.password_setup.completed", "user", str(token_record.user_id),
        org_id=user.org_id, actor_id=user.id,
        metadata={"user_id": str(user.id)}
    )
    await send_notification_event(
        db=db,
        user=user,
        event_key="account.created",
        title="Account is ready",
        message="Your account setup is complete and you can sign in to your organization dashboard.",
    )
    await send_org_admin_notification(
        db=db,
        org_id=user.org_id,
        actor_user_id=user.id,
        title="Invitation accepted",
        message=f"{user.email} completed invitation-based account setup and can now sign in.",
        event_key="account.invitation_accepted",
    )
    return JSONResponse(content={"message": "Account setup completed. You can now sign in."})
