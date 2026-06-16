"""operator_settings.delegate_enabled kill-switch (ADR 0007)."""

from __future__ import annotations

from alembic import op

revision = "schema_096"
down_revision = "schema_095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS delegate_enabled BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.delegate_enabled IS
          'When false, the delegate tool rejects all invocations (operator tuning kill-switch).';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS delegate_enabled;")
