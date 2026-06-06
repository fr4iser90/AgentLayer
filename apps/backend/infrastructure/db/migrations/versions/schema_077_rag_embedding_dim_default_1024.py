"""Unset rag_embedding_dim default (0) until live model probe; no hardcoded width.

Revision ID: schema_077
Revises: schema_076
"""

from __future__ import annotations

from alembic import op

revision = "schema_077"
down_revision = "schema_076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN rag_embedding_dim SET DEFAULT 0;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN rag_embedding_dim SET DEFAULT 768;
        """
    )
