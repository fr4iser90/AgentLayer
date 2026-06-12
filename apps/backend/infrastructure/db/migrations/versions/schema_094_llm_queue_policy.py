"""Add LLM slot queue policy settings (operator + per-user priority)."""

from __future__ import annotations

from alembic import op

revision = "schema_094"
down_revision = "schema_093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llm_queue_policy TEXT NOT NULL DEFAULT 'priority';

        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llm_queue_user_priority INTEGER NOT NULL DEFAULT 100;

        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llm_queue_benchmark_priority INTEGER NOT NULL DEFAULT 10;

        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llm_queue_scheduler_priority INTEGER NOT NULL DEFAULT 50;

        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_policy_check;

        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_llm_queue_policy_check
          CHECK (llm_queue_policy IN ('fifo', 'priority', 'round_robin'));

        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_user_priority_check;

        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_llm_queue_user_priority_check
          CHECK (llm_queue_user_priority >= 0 AND llm_queue_user_priority <= 1000);

        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_benchmark_priority_check;

        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_llm_queue_benchmark_priority_check
          CHECK (llm_queue_benchmark_priority >= 0 AND llm_queue_benchmark_priority <= 1000);

        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_scheduler_priority_check;

        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_llm_queue_scheduler_priority_check
          CHECK (llm_queue_scheduler_priority >= 0 AND llm_queue_scheduler_priority <= 1000);

        COMMENT ON COLUMN operator_settings.llm_queue_policy IS
          'LLM slot wait order: priority (tier + user RR) | fifo | round_robin (global RR)';

        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS llm_queue_priority INTEGER NULL;

        ALTER TABLE users
          DROP CONSTRAINT IF EXISTS users_llm_queue_priority_check;

        ALTER TABLE users
          ADD CONSTRAINT users_llm_queue_priority_check
          CHECK (llm_queue_priority IS NULL OR (llm_queue_priority >= 0 AND llm_queue_priority <= 1000));

        COMMENT ON COLUMN users.llm_queue_priority IS
          'Optional per-user LLM slot priority override (higher = served sooner); NULL = class default';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_llm_queue_priority_check;
        ALTER TABLE users DROP COLUMN IF EXISTS llm_queue_priority;

        ALTER TABLE operator_settings DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_scheduler_priority_check;
        ALTER TABLE operator_settings DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_benchmark_priority_check;
        ALTER TABLE operator_settings DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_user_priority_check;
        ALTER TABLE operator_settings DROP CONSTRAINT IF EXISTS operator_settings_llm_queue_policy_check;

        ALTER TABLE operator_settings DROP COLUMN IF EXISTS llm_queue_scheduler_priority;
        ALTER TABLE operator_settings DROP COLUMN IF EXISTS llm_queue_benchmark_priority;
        ALTER TABLE operator_settings DROP COLUMN IF EXISTS llm_queue_user_priority;
        ALTER TABLE operator_settings DROP COLUMN IF EXISTS llm_queue_policy;
        """
    )
