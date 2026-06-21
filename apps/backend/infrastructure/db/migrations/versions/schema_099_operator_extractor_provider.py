"""Provider endpoint rows for embedding, voice, and K1-lite extractor."""

from __future__ import annotations

from alembic import op

revision = "schema_099"
down_revision = "schema_098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS extractor_api_base_url TEXT,
          ADD COLUMN IF NOT EXISTS extractor_api_key TEXT,
          ADD COLUMN IF NOT EXISTS extractor_api_header_name VARCHAR(128),
          ADD COLUMN IF NOT EXISTS extractor_provider_id VARCHAR(64),
          ADD COLUMN IF NOT EXISTS extractor_model TEXT,
          ADD COLUMN IF NOT EXISTS extractor_timeout_sec DOUBLE PRECISION NOT NULL DEFAULT 120;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_provider_endpoints (
          id BIGSERIAL PRIMARY KEY,
          kind VARCHAR(32) NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0,
          enabled BOOLEAN NOT NULL DEFAULT true,
          label TEXT NOT NULL DEFAULT '',
          base_url TEXT NOT NULL,
          api_key TEXT NOT NULL DEFAULT '',
          api_header_name VARCHAR(128) NOT NULL DEFAULT 'Authorization',
          model_default TEXT,
          options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT operator_provider_endpoints_kind_check
            CHECK (kind IN ('embedding', 'voice_stt', 'voice_tts', 'extractor'))
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_operator_provider_endpoints_kind_sort
          ON operator_provider_endpoints (kind, sort_order ASC, id ASC);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_operator_provider_endpoints_kind_sort;")
    op.execute("DROP TABLE IF EXISTS operator_provider_endpoints;")
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS extractor_api_base_url,
          DROP COLUMN IF EXISTS extractor_api_key,
          DROP COLUMN IF EXISTS extractor_api_header_name,
          DROP COLUMN IF EXISTS extractor_provider_id,
          DROP COLUMN IF EXISTS extractor_model,
          DROP COLUMN IF EXISTS extractor_timeout_sec;
        """
    )

