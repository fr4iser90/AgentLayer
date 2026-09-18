"""LLM risk assessment columns on ``agent_prompt_versions``.

Publishing a prompt used to check only that the row existed. These columns hold
the LLM assessment that now gates publish, and record the site-admin override
that is the only way past a ``high`` verdict.

``risk_level`` defaults to ``unassessed`` rather than ``low`` so that a row
which never went through the gate can never read as if it had been cleared.
"""

from __future__ import annotations

from alembic import op

revision = "schema_133"
down_revision = "schema_132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_prompt_versions
          ADD COLUMN IF NOT EXISTS risk_level TEXT NOT NULL DEFAULT 'unassessed';
        """
    )
    op.execute(
        """
        ALTER TABLE agent_prompt_versions
          ADD CONSTRAINT agent_prompt_versions_risk_level_check
          CHECK (risk_level IN ('unassessed', 'low', 'medium', 'high'));
        """
    )
    op.execute(
        """
        ALTER TABLE agent_prompt_versions
          ADD COLUMN IF NOT EXISTS risk_reasons JSONB NOT NULL DEFAULT '[]'::jsonb;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_prompt_versions
          ADD COLUMN IF NOT EXISTS assessed_at TIMESTAMPTZ;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_prompt_versions
          ADD COLUMN IF NOT EXISTS override_by UUID NULL REFERENCES users(id) ON DELETE SET NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_prompt_versions
          ADD COLUMN IF NOT EXISTS override_reason TEXT;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN agent_prompt_versions.risk_level IS
          'LLM verdict recorded at publish time. high blocks publish unless a site '
          'admin overrides it. unassessed means the gate never ran for this row.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN agent_prompt_versions.override_by IS
          'Site admin who published despite a high verdict. NULL unless overridden.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_prompt_versions
          DROP CONSTRAINT IF EXISTS agent_prompt_versions_risk_level_check;
        """
    )
    for col in ("override_reason", "override_by", "assessed_at", "risk_reasons", "risk_level"):
        op.execute(f"ALTER TABLE agent_prompt_versions DROP COLUMN IF EXISTS {col};")
