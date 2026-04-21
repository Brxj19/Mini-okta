"""Public signup schemas."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class OrganizationSelfServeSignupRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=100)
    organization_slug: Optional[str] = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9\-]+$")
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8)
    admin_first_name: Optional[str] = None
    admin_last_name: Optional[str] = None


class PublicSignupOrganizationSummary(BaseModel):
    id: Optional[UUID] = None
    name: str
    slug: str
    status: str
    access_tier: str
    verification_status: str


class PublicSignupAdminSummary(BaseModel):
    id: Optional[UUID] = None
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class OrganizationSelfServeSignupResponse(BaseModel):
    message: str
    organization: PublicSignupOrganizationSummary
    admin_user: PublicSignupAdminSummary
    email_verification_required: bool = True
    verification_challenge_token: str
    verification_expires_in_seconds: int


class OrganizationSelfServeVerifyEmailOtpRequest(BaseModel):
    challenge_token: str = Field(..., min_length=12, max_length=255)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class OrganizationSelfServeVerifyEmailOtpResponse(BaseModel):
    message: str
    organization: PublicSignupOrganizationSummary
    admin_user: PublicSignupAdminSummary


class OrganizationSelfServeResendEmailOtpRequest(BaseModel):
    challenge_token: str = Field(..., min_length=12, max_length=255)
