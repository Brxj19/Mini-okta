"""Applications router: full app CRUD + rotate-secret + disable."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.dependencies import get_db, require_permission
from app.models.application import Application
from app.models.organization import Organization
from app.schemas.application import (
    ApplicationCreate, ApplicationUpdate, ApplicationResponse,
    ApplicationCreateResponse, ApplicationListResponse, RotateSecretResponse,
    ApplicationGroupAssignRequest, ApplicationGroupListResponse,
    ApplicationRoleMappingCreate, ApplicationRoleMappingResponse, ApplicationRoleMappingListResponse,
)
from app.services.application_service import (
    create_application, get_application, list_applications,
    update_application, rotate_secret, disable_application, enable_application, delete_application,
    list_application_groups, assign_groups_to_application, remove_group_from_application,
    list_application_role_mappings, create_application_role_mapping, delete_application_role_mapping,
    list_group_users,
)
from app.services.token_service import revoke_all_client_tokens
from app.services.audit_service import write_audit_event
from app.services.group_service import get_group
from app.services.notification_service import send_admin_activity_notification, send_notification_event
from app.services.role_service import list_roles
from app.services.organization_service import get_org_limits, is_org_limited
from app.services.organization_service import validate_limited_org_app_policy

router = APIRouter(prefix="/api/v1/organizations/{org_id}/applications", tags=["applications"])


async def _get_org_application_or_404(db: AsyncSession, org_id: UUID, app_id: UUID):
    app = await get_application(db, app_id)
    if not app or app.org_id != org_id:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Application not found"})
    return app


@router.post("", response_model=ApplicationCreateResponse, status_code=201)
async def create_app(
    org_id: UUID,
    body: ApplicationCreate,
    current_user: dict = Depends(require_permission("app:create")),
    db: AsyncSession = Depends(get_db),
):
    """Create an OAuth application. Returns client_secret ONCE for web/m2m types."""
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if org and is_org_limited(org.settings):
        limits = get_org_limits(org.settings)
        max_apps = limits.get("max_apps")
        if max_apps:
            current_apps_result = await db.execute(
                select(func.count())
                .select_from(Application)
                .where(Application.org_id == org_id, Application.status != "deleted")
            )
            current_apps = current_apps_result.scalar() or 0
            if current_apps >= max_apps:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "self_serve_limit_reached",
                        "error_description": f"Self-serve organizations can have up to {max_apps} applications until verified by a super admin.",
                    },
                )

        policy_error = validate_limited_org_app_policy(
            app_type=body.app_type,
            redirect_uris=body.redirect_uris or [],
            allowed_scopes=body.allowed_scopes or [],
            refresh_token_enabled=bool(body.refresh_token_enabled),
        )
        if policy_error:
            raise HTTPException(
                status_code=403,
                detail={"error": "organization_verification_required", "error_description": policy_error},
            )

    app, raw_secret = await create_application(
        db, org_id, body.name, body.app_type, body.redirect_uris, body.post_logout_redirect_uris,
        body.allowed_scopes, body.id_token_lifetime, body.access_token_lifetime,
        body.refresh_token_enabled, body.require_explicit_role_mappings, body.logo_url,
    )

    await write_audit_event(
        db, "app.created", "application", str(app.id),
        org_id=org_id, actor_id=current_user["user_id"],
        metadata={"client_id": app.client_id, "app_type": app.app_type}
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application created",
        message=f"{current_user.get('email', 'An admin')} created application '{app.name}'.",
    )

    response_data = ApplicationCreateResponse.model_validate(app)
    if raw_secret:
        response_data.client_secret = raw_secret
    return response_data


@router.get("", response_model=ApplicationListResponse)
async def list_apps(
    org_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission("app:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all applications for an org."""
    result = await list_applications(db, org_id, limit, cursor)
    return ApplicationListResponse(
        data=[ApplicationResponse.model_validate(a) for a in result["data"]],
        pagination=result["pagination"],
    )


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_app(
    org_id: UUID,
    app_id: UUID,
    current_user: dict = Depends(require_permission("app:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get application details (NEVER returns client_secret)."""
    app = await _get_org_application_or_404(db, org_id, app_id)
    return ApplicationResponse.model_validate(app)


@router.patch("/{app_id}", response_model=ApplicationResponse)
async def update_app(
    org_id: UUID,
    app_id: UUID,
    body: ApplicationUpdate,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Update application fields."""
    existing_app = await _get_org_application_or_404(db, org_id, app_id)
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if org and is_org_limited(org.settings):
        policy_error = validate_limited_org_app_policy(
            app_type=body.app_type if hasattr(body, "app_type") and body.app_type is not None else existing_app.app_type,
            redirect_uris=body.redirect_uris if body.redirect_uris is not None else (existing_app.redirect_uris or []),
            allowed_scopes=body.allowed_scopes if body.allowed_scopes is not None else (existing_app.allowed_scopes or []),
            refresh_token_enabled=bool(
                body.refresh_token_enabled if body.refresh_token_enabled is not None else existing_app.refresh_token_enabled
            ),
        )
        if policy_error:
            raise HTTPException(
                status_code=403,
                detail={"error": "organization_verification_required", "error_description": policy_error},
            )

    app = await update_application(
        db, app_id, body.name, body.redirect_uris, body.post_logout_redirect_uris, body.allowed_scopes,
        body.id_token_lifetime, body.access_token_lifetime, body.refresh_token_enabled, body.require_explicit_role_mappings, body.logo_url,
    )
    if not app:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Application not found"})
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application updated",
        message=f"{current_user.get('email', 'An admin')} updated application '{app.name}'.",
    )
    return ApplicationResponse.model_validate(app)


@router.post("/{app_id}/rotate-secret", response_model=RotateSecretResponse)
async def rotate_app_secret(
    org_id: UUID,
    app_id: UUID,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Rotate client secret. Returns new secret ONCE."""
    await _get_org_application_or_404(db, org_id, app_id)
    app, raw_secret = await rotate_secret(db, app_id)
    if not app:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Application not found"})
    if not raw_secret:
        raise HTTPException(400, detail={"error": "no_secret", "error_description": "SPA/native apps do not have client secrets"})

    await write_audit_event(
        db, "app.secret_rotated", "application", str(app.id),
        org_id=org_id, actor_id=current_user["user_id"],
        metadata={"client_id": app.client_id, "actor_id": str(current_user["user_id"])}
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application secret rotated",
        message=f"{current_user.get('email', 'An admin')} rotated client secret for '{app.name}'.",
    )

    return RotateSecretResponse(client_id=app.client_id, client_secret=raw_secret)


@router.post("/{app_id}/disable", response_model=ApplicationResponse)
async def disable_app(
    org_id: UUID,
    app_id: UUID,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Disable an application."""
    await _get_org_application_or_404(db, org_id, app_id)
    app = await disable_application(db, app_id)
    if not app:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Application not found"})
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application disabled",
        message=f"{current_user.get('email', 'An admin')} disabled application '{app.name}'.",
    )
    return ApplicationResponse.model_validate(app)


@router.post("/{app_id}/enable", response_model=ApplicationResponse)
async def enable_app(
    org_id: UUID,
    app_id: UUID,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Re-enable a disabled application."""
    await _get_org_application_or_404(db, org_id, app_id)
    app = await enable_application(db, app_id)
    if not app:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Application not found"})
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application enabled",
        message=f"{current_user.get('email', 'An admin')} enabled application '{app.name}'.",
    )
    return ApplicationResponse.model_validate(app)


@router.delete("/{app_id}")
async def delete_app(
    org_id: UUID,
    app_id: UUID,
    current_user: dict = Depends(require_permission("app:delete")),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete application and revoke all its tokens."""
    app = await _get_org_application_or_404(db, org_id, app_id)

    await revoke_all_client_tokens(db, app.client_id, reason="app_deleted")
    await delete_application(db, app_id)

    await write_audit_event(
        db, "app.deleted", "application", str(app.id),
        org_id=org_id, actor_id=current_user["user_id"],
        metadata={"client_id": app.client_id}
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application deleted",
        message=f"{current_user.get('email', 'An admin')} deleted application '{app.name}'.",
    )

    return {"message": "Application deleted"}


@router.get("/{app_id}/groups", response_model=ApplicationGroupListResponse)
async def list_application_groups_endpoint(
    org_id: UUID,
    app_id: UUID,
    current_user: dict = Depends(require_permission("app:read")),
    db: AsyncSession = Depends(get_db),
):
    """List groups assigned to an application."""
    await _get_org_application_or_404(db, org_id, app_id)
    from app.schemas.group import GroupResponse

    groups = await list_application_groups(db, app_id)
    return ApplicationGroupListResponse(data=[GroupResponse.model_validate(group) for group in groups])


@router.post("/{app_id}/groups")
async def assign_application_groups_endpoint(
    org_id: UUID,
    app_id: UUID,
    body: ApplicationGroupAssignRequest,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Assign organization groups to an application."""
    app = await _get_org_application_or_404(db, org_id, app_id)

    for group_id in body.group_ids:
        group = await get_group(db, group_id)
        if not group or group.org_id != org_id:
            raise HTTPException(404, detail={"error": "not_found", "error_description": "Group not found"})

    assigned = await assign_groups_to_application(db, app_id, body.group_ids)
    notified_user_ids: set[UUID] = set()
    for group_id in assigned:
        for user in await list_group_users(db, group_id):
            if user.id in notified_user_ids:
                continue
            notified_user_ids.add(user.id)
            await send_notification_event(
                db=db,
                user=user,
                event_key="app.assignment",
                title="A new application is available",
                message=f"You now have access to {app.name} in your application directory.",
            )
    if assigned:
        await send_admin_activity_notification(
            db=db,
            org_id=org_id,
            actor_user_id=current_user["user_id"],
            title="Application groups updated",
            message=f"{current_user.get('email', 'An admin')} assigned {len(assigned)} group(s) to application '{app.name}'.",
        )
    return {"message": f"Assigned {len(assigned)} groups", "assigned": [str(group_id) for group_id in assigned]}


@router.delete("/{app_id}/groups/{group_id}")
async def remove_application_group_endpoint(
    org_id: UUID,
    app_id: UUID,
    group_id: UUID,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Remove a group assignment from an application."""
    await _get_org_application_or_404(db, org_id, app_id)
    success = await remove_group_from_application(db, app_id, group_id)
    if not success:
        raise HTTPException(404, detail={"error": "not_found", "error_description": "Group assignment not found"})
    app = await _get_org_application_or_404(db, org_id, app_id)
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application groups updated",
        message=f"{current_user.get('email', 'An admin')} removed a group assignment from application '{app.name}'.",
    )
    return {"message": "Group removed from application"}


@router.get("/{app_id}/role-mappings", response_model=ApplicationRoleMappingListResponse)
async def list_application_role_mappings_endpoint(
    org_id: UUID,
    app_id: UUID,
    current_user: dict = Depends(require_permission("app:read")),
    db: AsyncSession = Depends(get_db),
):
    """List per-application source-to-role mappings."""
    await _get_org_application_or_404(db, org_id, app_id)
    mappings = await list_application_role_mappings(db, app_id)
    return ApplicationRoleMappingListResponse(
        data=[ApplicationRoleMappingResponse.model_validate(mapping) for mapping in mappings]
    )


@router.post("/{app_id}/role-mappings", response_model=ApplicationRoleMappingResponse, status_code=201)
async def create_application_role_mapping_endpoint(
    org_id: UUID,
    app_id: UUID,
    body: ApplicationRoleMappingCreate,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Create one per-application source-to-role mapping."""
    app = await _get_org_application_or_404(db, org_id, app_id)

    source_value = body.source_value.strip().lower()
    if body.source_type == "group":
        assigned_groups = await list_application_groups(db, app.id)
        assigned_group_names = {group.name.lower() for group in assigned_groups}
        if source_value not in assigned_group_names:
            raise HTTPException(
                400,
                detail={
                    "error": "invalid_source_value",
                    "error_description": "For source_type=group, source_value must be an assigned application group name",
                },
            )
    else:
        role_result = await list_roles(db, org_id, limit=200, cursor=None)
        role_names = {role.name.lower() for role in role_result["data"]}
        if source_value not in role_names:
            raise HTTPException(
                400,
                detail={
                    "error": "invalid_source_value",
                    "error_description": "For source_type=role, source_value must be an organization role name",
                },
            )

    mapping = await create_application_role_mapping(
        db=db,
        app_id=app_id,
        source_type=body.source_type,
        source_value=body.source_value,
        app_role=body.app_role,
    )
    await write_audit_event(
        db,
        "app.role_mapping.created",
        "application",
        str(app_id),
        org_id=org_id,
        actor_id=current_user["user_id"],
        metadata={
            "mapping_id": str(mapping.id),
            "source_type": mapping.source_type,
            "source_value": mapping.source_value,
            "app_role": mapping.app_role,
        },
    )
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application role mapping updated",
        message=f"{current_user.get('email', 'An admin')} added role mapping '{mapping.source_type}:{mapping.source_value} -> {mapping.app_role}' for application '{app.name}'.",
    )
    return ApplicationRoleMappingResponse.model_validate(mapping)


@router.delete("/{app_id}/role-mappings/{mapping_id}")
async def delete_application_role_mapping_endpoint(
    org_id: UUID,
    app_id: UUID,
    mapping_id: UUID,
    current_user: dict = Depends(require_permission("app:update")),
    db: AsyncSession = Depends(get_db),
):
    """Delete one per-application source-to-role mapping."""
    await _get_org_application_or_404(db, org_id, app_id)
    deleted = await delete_application_role_mapping(db, app_id, mapping_id)
    if not deleted:
        raise HTTPException(
            404,
            detail={"error": "not_found", "error_description": "Role mapping not found"},
        )
    await write_audit_event(
        db,
        "app.role_mapping.deleted",
        "application",
        str(app_id),
        org_id=org_id,
        actor_id=current_user["user_id"],
        metadata={"mapping_id": str(mapping_id)},
    )
    app = await _get_org_application_or_404(db, org_id, app_id)
    await send_admin_activity_notification(
        db=db,
        org_id=org_id,
        actor_user_id=current_user["user_id"],
        title="Application role mapping updated",
        message=f"{current_user.get('email', 'An admin')} removed a role mapping from application '{app.name}'.",
    )
    return {"message": "Role mapping deleted"}
