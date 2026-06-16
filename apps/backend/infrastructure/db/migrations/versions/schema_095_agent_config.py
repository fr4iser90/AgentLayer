"""Agent runtime config overrides, changelog, sessions, benchmark cohort metadata."""

from __future__ import annotations

from alembic import op

revision = "schema_095"
down_revision = "schema_094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_config_overrides (
          tenant_id INTEGER NOT NULL,
          knob_id VARCHAR(128) NOT NULL,
          value_json JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          PRIMARY KEY (tenant_id, knob_id)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_config_overrides_tenant
          ON agent_config_overrides (tenant_id);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_config_changelog (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          actor_type VARCHAR(32) NOT NULL DEFAULT 'user',
          actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          actor_agent_id VARCHAR(64) NULL,
          session_id UUID NULL,
          experiment_id UUID NULL,
          hypothesis TEXT NULL,
          patches_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          fingerprint_before VARCHAR(128) NULL,
          fingerprint_after VARCHAR(128) NULL
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_config_changelog_tenant_created
          ON agent_config_changelog (tenant_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_config_sessions (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          label VARCHAR(128) NOT NULL DEFAULT '',
          hypothesis TEXT NULL,
          cohort_label VARCHAR(128) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'open',
          baseline_fingerprint VARCHAR(128) NULL,
          current_fingerprint VARCHAR(128) NULL,
          run_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          experiment_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          closed_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_experiments (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          label VARCHAR(128) NOT NULL,
          hypothesis TEXT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          session_id UUID NULL,
          fingerprint_at_start VARCHAR(128) NULL,
          fingerprint_at_end VARCHAR(128) NULL,
          pending_patches_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          run_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          review_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          suite_preset VARCHAR(64) NULL,
          harness_preset VARCHAR(64) NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          closed_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_reviews (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          experiment_id UUID NULL,
          session_id UUID NULL,
          mode VARCHAR(32) NOT NULL DEFAULT 'llm',
          reviewer_model VARCHAR(256) NULL,
          input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          actor_type VARCHAR(32) NOT NULL DEFAULT 'reviewer_job',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        ALTER TABLE benchmark_runs
          ADD COLUMN IF NOT EXISTS cohort_json JSONB NULL;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE benchmark_runs DROP COLUMN IF EXISTS cohort_json;")
    op.execute("DROP TABLE IF EXISTS benchmark_reviews;")
    op.execute("DROP TABLE IF EXISTS benchmark_experiments;")
    op.execute("DROP TABLE IF EXISTS agent_config_sessions;")
    op.execute("DROP TABLE IF EXISTS agent_config_changelog;")
    op.execute("DROP TABLE IF EXISTS agent_config_overrides;")
