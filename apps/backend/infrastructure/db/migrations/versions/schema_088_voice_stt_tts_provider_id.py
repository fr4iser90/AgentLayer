"""Separate STT and TTS voice catalog provider selection."""

from __future__ import annotations

from alembic import op

revision = "schema_088"
down_revision = "schema_087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS voice_stt_provider_id VARCHAR(64);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS voice_tts_provider_id VARCHAR(64);
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.voice_stt_provider_id IS
          'Active voice catalog provider for STT (voice_provider_1, voice_admin, …).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.voice_tts_provider_id IS
          'Active voice catalog provider for TTS (voice_provider_2, voice_admin, …).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS voice_stt_provider_id;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS voice_tts_provider_id;
        """
    )
