"""expand manager role permissions

Revision ID: c7d2e4f1a8b3
Revises: ab4d9c2e7f31
Create Date: 2026-04-21 20:58:00
"""

from alembic import op


revision = "c7d2e4f1a8b3"
down_revision = "ab4d9c2e7f31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET permissions = ARRAY(
            SELECT DISTINCT permission
            FROM unnest(
                COALESCE(permissions, ARRAY[]::text[])
                || ARRAY['group:read']
            ) AS permission
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'app:manager'
        """
    )

    op.execute(
        """
        UPDATE roles
        SET permissions = ARRAY(
            SELECT DISTINCT permission
            FROM unnest(
                COALESCE(permissions, ARRAY[]::text[])
                || ARRAY['group:read', 'group:member:add', 'group:member:remove']
            ) AS permission
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'user:manager'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET permissions = ARRAY(
            SELECT permission
            FROM unnest(COALESCE(permissions, ARRAY[]::text[])) AS permission
            WHERE permission <> 'group:read'
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'app:manager'
        """
    )

    op.execute(
        """
        UPDATE roles
        SET permissions = ARRAY(
            SELECT permission
            FROM unnest(COALESCE(permissions, ARRAY[]::text[])) AS permission
            WHERE permission NOT IN ('group:read', 'group:member:add', 'group:member:remove')
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'user:manager'
        """
    )
