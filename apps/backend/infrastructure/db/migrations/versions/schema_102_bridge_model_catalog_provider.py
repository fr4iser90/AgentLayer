"""Bridge chat model catalog provider selection."""

from __future__ import annotations

from alembic import op

revision = "schema_102"
down_revision = "schema_101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS discord_chat_model_catalog_owned_by VARCHAR(64),
          ADD COLUMN IF NOT EXISTS telegram_chat_model_catalog_owned_by VARCHAR(64);
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.discord_chat_model_catalog_owned_by IS
          'Model catalog provider id (GET /v1/models owned_by) for Discord bridge chat model.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.telegram_chat_model_catalog_owned_by IS
          'Model catalog provider id (GET /v1/models owned_by) for Telegram bridge chat model.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS discord_chat_model_catalog_owned_by,
          DROP COLUMN IF EXISTS telegram_chat_model_catalog_owned_by;
        """
    )
