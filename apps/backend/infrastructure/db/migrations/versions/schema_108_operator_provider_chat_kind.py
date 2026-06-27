"""Allow chat endpoints in generic operator provider endpoints."""

from __future__ import annotations

from alembic import op

revision = "schema_108"
down_revision = "schema_107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_provider_endpoints
          DROP CONSTRAINT IF EXISTS operator_provider_endpoints_kind_check;
        ALTER TABLE operator_provider_endpoints
          ADD CONSTRAINT operator_provider_endpoints_kind_check
          CHECK (kind IN ('chat', 'embedding', 'voice_stt', 'voice_tts', 'extractor'));
        """
    )
    op.execute(
        """
        INSERT INTO operator_provider_endpoints (
          kind, sort_order, enabled, label, base_url, api_key, api_header_name,
          model_default, max_parallel, options_json, updated_at
        )
        SELECT
          'chat',
          sort_order,
          enabled,
          label,
          base_url,
          api_key,
          COALESCE(NULLIF(api_header_name, ''), 'Authorization'),
          model_default,
          GREATEST(1, LEAST(64, COALESCE(max_parallel, 1))),
          '{}'::jsonb,
          now()
        FROM operator_external_llm_endpoints legacy
        WHERE NOT EXISTS (
          SELECT 1
            FROM operator_provider_endpoints generic
           WHERE generic.kind = 'chat'
             AND btrim(generic.base_url) = btrim(legacy.base_url)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM operator_provider_endpoints WHERE kind = 'chat';
        ALTER TABLE operator_provider_endpoints
          DROP CONSTRAINT IF EXISTS operator_provider_endpoints_kind_check;
        ALTER TABLE operator_provider_endpoints
          ADD CONSTRAINT operator_provider_endpoints_kind_check
          CHECK (kind IN ('embedding', 'voice_stt', 'voice_tts', 'extractor'));
        """
    )
