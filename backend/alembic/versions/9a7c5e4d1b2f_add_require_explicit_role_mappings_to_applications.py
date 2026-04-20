"""add require_explicit_role_mappings to applications

Revision ID: 9a7c5e4d1b2f
Revises: b2c4d6e8f0a1
Create Date: 2026-04-17 16:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "9a7c5e4d1b2f"
down_revision = "b2c4d6e8f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("require_explicit_role_mappings", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("applications", "require_explicit_role_mappings")
