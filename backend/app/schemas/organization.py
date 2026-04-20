"""Organization Pydantic schemas."""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class BootstrapAdminCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = Field(default=None, min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9\-]+$")
    display_name: Optional[str] = None
    settings: Optional[dict[str, Any]] = Field(default_factory=dict)
    bootstrap_admin: BootstrapAdminCreate


class OrganizationUpdate(BaseModel):
    display_name: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    display_name: Optional[str] = None
    status: str
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BootstrapAdminResponse(BaseModel):
    id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    model_config = {"from_attributes": True}


class OrganizationCreateResponse(OrganizationResponse):
    bootstrap_admin: BootstrapAdminResponse


class OrganizationListResponse(BaseModel):
    data: list[OrganizationResponse]
    pagination: dict[str, Any]


class UpgradeRequestCreate(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=120)
    company_website: Optional[str] = None
    company_size: str = Field(..., min_length=1, max_length=60)
    primary_use_case: str = Field(..., min_length=4, max_length=300)
    expected_monthly_users: Optional[int] = Field(default=None, ge=0)
    requested_features: Optional[str] = Field(default=None, max_length=1000)
    billing_contact_name: str = Field(..., min_length=2, max_length=120)
    billing_contact_email: EmailStr
    notes: Optional[str] = Field(default=None, max_length=1500)
    agree_to_terms: bool = False


class PlanStatusResponse(BaseModel):
    org_id: UUID
    org_name: str
    org_slug: str
    access_tier: str
    verification_status: str
    limits: dict[str, Any] = Field(default_factory=dict)
    upgrade_request: Optional[dict[str, Any]] = None
    current_plan_code: str = "free"
    current_plan: dict[str, Any] = Field(default_factory=dict)
    available_plans: list[dict[str, Any]] = Field(default_factory=list)
    billing_provider: str = "demo"
    gateway_ready: bool = False
    subscription: Optional[dict[str, Any]] = None
    payments: list[dict[str, Any]] = Field(default_factory=list)
    last_paid_plan_code: Optional[str] = None
    current_plan_rank: int = 0
    renewal_available: bool = False
    renewal_available_at: Optional[str] = None


class BillingCheckoutCreate(BaseModel):
    plan_code: str = Field(..., min_length=2, max_length=40)
    payment_method: str = Field(default="upi", min_length=3, max_length=20)


class BillingCheckoutComplete(BaseModel):
    provider: str = Field(..., min_length=3, max_length=30)
    session_id: str = Field(..., min_length=8, max_length=200)
    payment_method: str = Field(default="upi", min_length=3, max_length=20)
    razorpay_order_id: Optional[str] = Field(default=None, max_length=120)
    razorpay_payment_id: Optional[str] = Field(default=None, max_length=120)
    razorpay_signature: Optional[str] = Field(default=None, max_length=256)


class BillingCheckoutSessionResponse(BaseModel):
    checkout: dict[str, Any] = Field(default_factory=dict)
    plan_status: PlanStatusResponse


class CurrentOrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    display_name: Optional[str] = None
    status: str
    access_tier: str
    verification_status: str


class PendingUpgradeRequestItem(BaseModel):
    org_id: UUID
    org_name: str
    org_slug: str
    access_tier: str
    verification_status: str
    submitted_at: Optional[datetime] = None
    submitted_by_email: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class PendingUpgradeRequestListResponse(BaseModel):
    data: list[PendingUpgradeRequestItem]
