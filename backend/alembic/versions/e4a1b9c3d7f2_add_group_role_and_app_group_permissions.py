"""add group-role and app-group permissions

Revision ID: e4a1b9c3d7f2
Revises: d1e8f4a2b6c9
Create Date: 2026-04-21 22:42:00
"""

from alembic import op


revision = "e4a1b9c3d7f2"
down_revision = "d1e8f4a2b6c9"
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
                || ARRAY['app:group:assign', 'app:group:update']
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
                || ARRAY['role:read', 'group:role:assign', 'group:role:update', 'user:read']
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
            SELECT DISTINCT permission
            FROM unnest(
                COALESCE(permissions, ARRAY[]::text[])
                || ARRAY['app:group:assign', 'app:group:update', 'group:role:assign', 'group:role:update']
            ) AS permission
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'org:admin'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET permissions = ARRAY(
            SELECT permission
            FROM unnest(COALESCE(permissions, ARRAY[]::text[])) AS permission
            WHERE permission NOT IN ('app:group:assign', 'app:group:update')
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
            WHERE permission NOT IN ('role:read', 'group:role:assign', 'group:role:update', 'user:read')
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
            WHERE permission NOT IN ('app:group:assign', 'app:group:update', 'group:role:assign', 'group:role:update')
            ORDER BY permission
        )
        WHERE is_system = true AND name = 'org:admin'
        """
    )
