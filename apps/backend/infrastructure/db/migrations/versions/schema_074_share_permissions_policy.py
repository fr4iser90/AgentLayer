"""Add policy JSONB to share_permissions for scoped grants (days_ahead, expires_at)."""

from __future__ import annotations

from alembic import op

revision = "schema_074"
down_revision = "schema_073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE share_permissions
        ADD COLUMN IF NOT EXISTS policy JSONB NOT NULL DEFAULT '{}'::jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE share_permissions
        DROP COLUMN IF EXISTS policy;
        """
    )
