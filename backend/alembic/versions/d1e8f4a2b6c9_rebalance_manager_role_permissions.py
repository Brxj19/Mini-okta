"""rebalance manager role permissions

Revision ID: d1e8f4a2b6c9
Revises: c7d2e4f1a8b3
Create Date: 2026-04-21 22:25:00
"""

from alembic import op


revision = "d1e8f4a2b6c9"
down_revision = "c7d2e4f1a8b3"
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
                || ARRAY['user:read']
            ) AS permission
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'group:manager'
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


def downgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET permissions = ARRAY(
            SELECT permission
            FROM unnest(COALESCE(permissions, ARRAY[]::text[])) AS permission
            WHERE permission <> 'user:read'
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'group:manager'
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
