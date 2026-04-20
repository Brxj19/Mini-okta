"""Token Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class TokenRequest(BaseModel):
    grant_type: str
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    code_verifier: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class TokenResponse(BaseModel):
    id_token: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int


class TokenIntrospectRequest(BaseModel):
    token: str


class TokenIntrospectResponse(BaseModel):
    active: bool
    sub: Optional[str] = None
    org_id: Optional[str] = None
    scope: Optional[str] = None
    roles: Optional[list[str]] = None
    permissions: Optional[list[str]] = None
    exp: Optional[int] = None
    client_id: Optional[str] = None
    token_type: Optional[str] = None


class UserInfoResponse(BaseModel):
    sub: str
    email: str
    email_verified: bool
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    app_groups: list[str] = Field(default_factory=list)
    app_group_ids: list[str] = Field(default_factory=list)
    app_roles: list[str] = Field(default_factory=list)
    org_id: str


class SessionResponse(BaseModel):
    jti: str
    user_id: str
    client_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: Optional[str] = None
    current: bool = False
