"""add deleted_at to applications

Revision ID: ab4d9c2e7f31
Revises: 9a7c5e4d1b2f
Create Date: 2026-04-20 15:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "ab4d9c2e7f31"
down_revision = "9a7c5e4d1b2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE applications
        SET deleted_at = COALESCE(updated_at, created_at, NOW())
        WHERE status = 'deleted' AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("applications", "deleted_at")
