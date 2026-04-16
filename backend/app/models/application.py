"""Application (OAuth Client) model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, Boolean, DateTime, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(Text, nullable=False)
    client_id = Column(Text, nullable=False, unique=True)
    client_secret = Column(Text, nullable=True)  # bcrypt hashed; NULL for spa/native
    app_type = Column(Text, nullable=False, default="web")  # web | spa | native | m2m
    redirect_uris = Column(ARRAY(Text), nullable=False, default=list)
    post_logout_redirect_uris = Column(ARRAY(Text), nullable=False, default=list)
    allowed_scopes = Column(ARRAY(Text), nullable=False, default=lambda: ["openid", "profile", "email"])
    logo_url = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
    id_token_lifetime = Column(Integer, nullable=False, default=3600)
    access_token_lifetime = Column(Integer, nullable=True, default=3600)
    refresh_token_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    organization = relationship("Organization", back_populates="applications")
    group_assignments = relationship("ApplicationGroupAssignment", back_populates="application", lazy="selectin", cascade="all, delete-orphan")
    role_mappings = relationship("ApplicationRoleMapping", back_populates="application", lazy="selectin", cascade="all, delete-orphan")
