"""Add post logout redirect URIs to applications.

Revision ID: b2c4d6e8f0a1
Revises: f1a2c3d4e5f6
Create Date: 2026-04-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b2c4d6e8f0a1"
down_revision = "f1a2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "post_logout_redirect_uris",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            server_default="{}",
        ),
    )
    op.execute(
        """
        UPDATE applications
        SET post_logout_redirect_uris = (
          SELECT COALESCE(array_agg(DISTINCT candidate_uri), ARRAY[]::text[])
          FROM (
            SELECT unnest(COALESCE(redirect_uris, ARRAY[]::text[])) AS candidate_uri
            UNION
            SELECT regexp_replace(unnest(COALESCE(redirect_uris, ARRAY[]::text[])), '^(https?://[^/]+).*$','\\1')
          ) candidates
          WHERE candidate_uri IS NOT NULL AND candidate_uri <> ''
        )
        """
    )
    op.alter_column("applications", "post_logout_redirect_uris", nullable=False)


def downgrade() -> None:
    op.drop_column("applications", "post_logout_redirect_uris")
