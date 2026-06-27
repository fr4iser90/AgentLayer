"""Versioned tenant agent prompt drafts and published prompts.

Revision ID: schema_110
Revises: schema_109
Create Date: 2026-06-27
"""

from __future__ import annotations

from alembic import op

revision = "schema_110"
down_revision = "schema_109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_prompt_versions (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          agent_id VARCHAR(64) NOT NULL,
          version INTEGER NOT NULL,
          status VARCHAR(16) NOT NULL DEFAULT 'draft',
          prompt_text TEXT NOT NULL,
          notes TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          published_at TIMESTAMPTZ NULL,
          published_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          archived_at TIMESTAMPTZ NULL,
          CONSTRAINT agent_prompt_versions_agent_id_check
            CHECK (agent_id ~ '^[a-z0-9_][a-z0-9_-]{0,63}$'),
          CONSTRAINT agent_prompt_versions_status_check
            CHECK (status IN ('draft', 'published', 'archived')),
          CONSTRAINT agent_prompt_versions_prompt_len_check
            CHECK (char_length(prompt_text) BETWEEN 1 AND 12000)
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_prompt_versions_version
          ON agent_prompt_versions (tenant_id, agent_id, version);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_prompt_versions_published
          ON agent_prompt_versions (tenant_id, agent_id)
          WHERE status = 'published';
        CREATE INDEX IF NOT EXISTS idx_agent_prompt_versions_agent
          ON agent_prompt_versions (tenant_id, agent_id, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_prompt_versions;")
