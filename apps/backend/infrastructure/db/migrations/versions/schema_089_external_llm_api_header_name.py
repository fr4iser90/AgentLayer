"""Add api_header_name to operator_external_llm_endpoints (X-API-KEY, Authorization, …)."""

from __future__ import annotations

from alembic import op

revision = "schema_089"
down_revision = "schema_088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_external_llm_endpoints
          ADD COLUMN IF NOT EXISTS api_header_name VARCHAR(128);
        """
    )
    op.execute(
        """
        UPDATE operator_external_llm_endpoints
           SET api_header_name = 'Authorization'
         WHERE api_header_name IS NULL OR btrim(api_header_name) = '';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_external_llm_endpoints
          DROP COLUMN IF EXISTS api_header_name;
        """
    )
