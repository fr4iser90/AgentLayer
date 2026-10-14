"""operator_settings: nullable overrides for external coding runtimes.

NULL = follow env (AGENT_EXTERNAL_RUNTIME_ENABLED / AGENT_QWEN_ENABLED).
Non-null = operator/wizard override without editing .env.
"""

from __future__ import annotations

from alembic import op

revision = "schema_140"
down_revision = "schema_139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS external_runtime_enabled BOOLEAN NULL,
          ADD COLUMN IF NOT EXISTS qwen_runtime_enabled BOOLEAN NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.external_runtime_enabled IS
          'Nullable override for AGENT_EXTERNAL_RUNTIME_ENABLED. NULL = use env.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.qwen_runtime_enabled IS
          'Nullable override for AGENT_QWEN_ENABLED. NULL = use env.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS external_runtime_enabled,
          DROP COLUMN IF EXISTS qwen_runtime_enabled;
        """
    )
