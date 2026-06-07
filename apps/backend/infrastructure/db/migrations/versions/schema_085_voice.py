"""Voice STT/TTS: operator flags + per-user voice preferences.

Revision ID: schema_085
Revises: schema_084
"""

from __future__ import annotations

from alembic import op

revision = "schema_085"
down_revision = "schema_084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_api_base_url TEXT;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_api_key TEXT;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_stt_model TEXT;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_tts_model TEXT;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_tts_voice TEXT;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_max_seconds INTEGER;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_max_bytes INTEGER;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_bridge_telegram BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_bridge_discord BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_voice_prefs (
          user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          tenant_id INTEGER NOT NULL,
          input_enabled BOOLEAN NOT NULL DEFAULT true,
          output_enabled BOOLEAN NOT NULL DEFAULT false,
          language TEXT NOT NULL DEFAULT 'de',
          voice_id TEXT,
          mode_web TEXT NOT NULL DEFAULT 'push_to_talk',
          mode_telegram TEXT NOT NULL DEFAULT 'text_only',
          mode_discord TEXT NOT NULL DEFAULT 'text_only',
          edit_transcript_before_send BOOLEAN NOT NULL DEFAULT true,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_voice_prefs_tenant
          ON user_voice_prefs (tenant_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_voice_prefs;")
    for col in (
        "voice_bridge_discord",
        "voice_bridge_telegram",
        "voice_max_bytes",
        "voice_max_seconds",
        "voice_tts_voice",
        "voice_tts_model",
        "voice_stt_model",
        "voice_api_key",
        "voice_api_base_url",
        "voice_enabled",
    ):
        op.execute(f"ALTER TABLE operator_settings DROP COLUMN IF EXISTS {col};")
