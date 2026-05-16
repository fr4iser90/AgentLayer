"""Persist chat model catalog provider per conversation (composer dropdown).

Revision ID: schema_049
Revises: schema_048
"""

from __future__ import annotations

from alembic import op

revision = "schema_049"
down_revision = "schema_048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS pref_model_catalog_owned_by VARCHAR(64);
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.pref_model_catalog_owned_by IS
          'GET /v1/models row owned_by for the last chat model pick (e.g. llama_cpp, ollama).';
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE chat_conversations DROP COLUMN IF EXISTS pref_model_catalog_owned_by;"
    )
