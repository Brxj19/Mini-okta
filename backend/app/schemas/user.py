"""User Pydantic schemas."""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class UserCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = Field(None, min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    group_ids: Optional[list[UUID]] = None


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class CurrentUserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_image_url: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_image_url: Optional[str] = None
    status: str
    email_verified: bool
    is_super_admin: bool = False
    mfa_enabled: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserDetailResponse(UserResponse):
    groups: list[dict[str, Any]] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class CurrentUserProfileResponse(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_image_url: Optional[str] = None
    status: str
    email_verified: bool
    is_super_admin: bool = False

    model_config = {"from_attributes": True}


class CurrentSessionResponse(BaseModel):
    user_id: UUID
    email: str
    org_id: UUID
    is_super_admin: bool = False
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class UserListResponse(BaseModel):
    data: list[UserResponse]
    pagination: dict[str, Any]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    id_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    mfa_required: bool = False
    mfa_setup_required: bool = False
    challenge_token: Optional[str] = None
    manual_entry_key: Optional[str] = None
    otpauth_url: Optional[str] = None
    qr_code_data_url: Optional[str] = None
    backup_codes: list[str] = Field(default_factory=list)
    recovery_codes_remaining: int = 0
    message: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class AccountPreferencesResponse(BaseModel):
    security_alerts: bool
    weekly_summary_emails: bool


class AccountPreferencesUpdate(BaseModel):
    security_alerts: bool
    weekly_summary_emails: bool


class MfaStatusResponse(BaseModel):
    enabled: bool
    org_enforced: bool
    recovery_codes_remaining: int = 0
    backup_codes: list[str] = Field(default_factory=list)


class MfaSetupResponse(BaseModel):
    manual_entry_key: str
    otpauth_url: str
    qr_code_data_url: str
    issuer: str
    account_name: str
    message: str


class MfaCodeVerifyRequest(BaseModel):
    code: str


class MfaDisableRequest(BaseModel):
    current_password: str
    code: str


class MfaRecoveryCodesRegenerateRequest(BaseModel):
    current_password: str
    code: str


class LoginMfaVerifyRequest(BaseModel):
    challenge_token: str
    code: str
