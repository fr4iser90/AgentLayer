"""Add max_parallel slots to generic operator provider endpoints."""

from __future__ import annotations

from alembic import op

revision = "schema_107"
down_revision = "schema_106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_provider_endpoints
          ADD COLUMN IF NOT EXISTS max_parallel INTEGER NOT NULL DEFAULT 1;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_provider_endpoints
          DROP CONSTRAINT IF EXISTS operator_provider_endpoints_max_parallel_check;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_provider_endpoints
          ADD CONSTRAINT operator_provider_endpoints_max_parallel_check
          CHECK (max_parallel >= 1 AND max_parallel <= 64);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_provider_endpoints
          DROP CONSTRAINT IF EXISTS operator_provider_endpoints_max_parallel_check;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_provider_endpoints
          DROP COLUMN IF EXISTS max_parallel;
        """
    )
