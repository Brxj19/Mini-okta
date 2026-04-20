"""Application Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from uuid import UUID

from app.schemas.group import GroupResponse


class ApplicationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    app_type: str = Field(..., pattern=r"^(web|spa|native|m2m)$")
    redirect_uris: list[str] = Field(default_factory=list)
    post_logout_redirect_uris: list[str] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default=["openid", "profile", "email"])
    logo_url: Optional[str] = None
    id_token_lifetime: int = Field(default=3600, ge=300, le=86400)
    access_token_lifetime: int = Field(default=3600, ge=300, le=86400)
    refresh_token_enabled: bool = False
    require_explicit_role_mappings: bool = False


class ApplicationUpdate(BaseModel):
    name: Optional[str] = None
    redirect_uris: Optional[list[str]] = None
    post_logout_redirect_uris: Optional[list[str]] = None
    allowed_scopes: Optional[list[str]] = None
    id_token_lifetime: Optional[int] = Field(default=None, ge=300, le=86400)
    access_token_lifetime: Optional[int] = Field(default=None, ge=300, le=86400)
    refresh_token_enabled: Optional[bool] = None
    require_explicit_role_mappings: Optional[bool] = None
    logo_url: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    client_id: str
    app_type: str
    redirect_uris: list[str]
    post_logout_redirect_uris: list[str]
    allowed_scopes: list[str]
    logo_url: Optional[str] = None
    status: str
    id_token_lifetime: int
    access_token_lifetime: Optional[int] = None
    refresh_token_enabled: bool
    require_explicit_role_mappings: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationCreateResponse(ApplicationResponse):
    client_secret: Optional[str] = None  # Only returned ONCE on creation


class ApplicationListResponse(BaseModel):
    data: list[ApplicationResponse]
    pagination: dict[str, Any]


class ApplicationGroupAssignRequest(BaseModel):
    group_ids: list[UUID] = Field(default_factory=list, min_length=1)


class ApplicationGroupListResponse(BaseModel):
    data: list[GroupResponse]


class ApplicationRoleMappingCreate(BaseModel):
    source_type: str = Field(..., pattern=r"^(group|role)$")
    source_value: str = Field(..., min_length=1, max_length=200)
    app_role: str = Field(..., min_length=1, max_length=200)


class ApplicationRoleMappingResponse(BaseModel):
    id: UUID
    application_id: UUID
    source_type: str
    source_value: str
    app_role: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationRoleMappingListResponse(BaseModel):
    data: list[ApplicationRoleMappingResponse]


class RotateSecretResponse(BaseModel):
    client_id: str
    client_secret: str  # Only returned ONCE
