"""operator_settings: DSH enable + preferred coding runtime.

NULL preferred = internal AgentLayer coding loop.
NULL dsh/qwen enables = follow env (AGENT_DSH_ENABLED / AGENT_QWEN_ENABLED).
"""

from __future__ import annotations

from alembic import op

revision = "schema_141"
down_revision = "schema_140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS dsh_runtime_enabled BOOLEAN NULL,
          ADD COLUMN IF NOT EXISTS preferred_coding_runtime TEXT NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.dsh_runtime_enabled IS
          'Nullable override for AGENT_DSH_ENABLED. NULL = use env.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.preferred_coding_runtime IS
          'Preferred coding runtime id (qwen_code, deepseek_harness) or empty/NULL for internal.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS dsh_runtime_enabled,
          DROP COLUMN IF EXISTS preferred_coding_runtime;
        """
    )
