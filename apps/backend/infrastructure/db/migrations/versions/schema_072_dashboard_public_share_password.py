"""Optional password on dashboard public share links."""

from __future__ import annotations

from alembic import op

revision = "schema_072"
down_revision = "schema_071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE dashboard_public_share_tokens
          ADD COLUMN IF NOT EXISTS password_hash TEXT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE dashboard_public_share_tokens
          DROP COLUMN IF EXISTS password_hash;
        """
    )
