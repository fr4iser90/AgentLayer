"""Infrastructure adapter for voice policy state and provider resolution."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.voice import voice_policy as domain
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.voice_catalog_providers import (
    resolve_active_voice_stt_spec,
    resolve_active_voice_tts_spec,
    voice_auth_headers,
)


class _VoicePolicyDeps:
    @staticmethod
    def operator_voice_row() -> dict[str, Any] | None:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT voice_enabled, voice_provider_id, voice_stt_provider_id, voice_tts_provider_id,
                           voice_api_base_url, voice_api_key,
                           voice_stt_model, voice_tts_model, voice_tts_voice,
                           voice_max_seconds, voice_max_bytes,
                           voice_bridge_telegram, voice_bridge_discord,
                           voice_realtime_enabled, voice_discord_vc_enabled
                    FROM operator_settings WHERE id = 1
                    """
                )
                row = cur.fetchone()
        if not row:
            return None
        keys = tuple(domain._DEFAULT_OPERATOR.keys())
        return {k: row[i] for i, k in enumerate(keys)}

    @staticmethod
    def user_voice_prefs_get(user_id: uuid.UUID) -> dict[str, Any] | None:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT input_enabled, output_enabled, language, voice_id,
                           mode_web, mode_telegram, mode_discord,
                           edit_transcript_before_send
                    FROM user_voice_prefs WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        keys = (
            "input_enabled",
            "output_enabled",
            "language",
            "voice_id",
            "mode_web",
            "mode_telegram",
            "mode_discord",
            "edit_transcript_before_send",
        )
        return {k: row[i] for i, k in enumerate(keys)}

    @staticmethod
    def user_voice_prefs_upsert(
        tenant_id: int,
        user_id: uuid.UUID,
        values: dict[str, Any],
    ) -> None:
        with db.pool().connection() as conn:
            with conn.cursor() as cur_db:
                cur_db.execute(
                    """
                    INSERT INTO user_voice_prefs (
                      user_id, tenant_id, input_enabled, output_enabled, language, voice_id,
                      mode_web, mode_telegram, mode_discord, edit_transcript_before_send, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (user_id) DO UPDATE SET
                      tenant_id = EXCLUDED.tenant_id,
                      input_enabled = EXCLUDED.input_enabled,
                      output_enabled = EXCLUDED.output_enabled,
                      language = EXCLUDED.language,
                      voice_id = EXCLUDED.voice_id,
                      mode_web = EXCLUDED.mode_web,
                      mode_telegram = EXCLUDED.mode_telegram,
                      mode_discord = EXCLUDED.mode_discord,
                      edit_transcript_before_send = EXCLUDED.edit_transcript_before_send,
                      updated_at = now()
                    """,
                    (
                        user_id,
                        tenant_id,
                        bool(values.get("input_enabled", True)),
                        bool(values.get("output_enabled", False)),
                        str(values.get("language") or "de")[:16],
                        (str(values["voice_id"]).strip()[:64] if values.get("voice_id") else None),
                        str(values.get("mode_web") or "push_to_talk")[:32],
                        str(values.get("mode_telegram") or "text_only")[:32],
                        str(values.get("mode_discord") or "text_only")[:32],
                        bool(values.get("edit_transcript_before_send", True)),
                    ),
                )
            conn.commit()

    active_voice_stt_spec = staticmethod(resolve_active_voice_stt_spec)
    active_voice_tts_spec = staticmethod(resolve_active_voice_tts_spec)
    voice_auth_headers = staticmethod(voice_auth_headers)


domain.register_voice_policy_dependencies(_VoicePolicyDeps())

effective_discord_vc = domain.effective_discord_vc
effective_stt_language = domain.effective_stt_language
effective_tts_voice = domain.effective_tts_voice
effective_voice_enabled = domain.effective_voice_enabled
effective_voice_input = domain.effective_voice_input
effective_voice_limits = domain.effective_voice_limits
effective_voice_output = domain.effective_voice_output
effective_voice_realtime = domain.effective_voice_realtime
operator_voice_row = domain.operator_voice_row
user_voice_prefs_get = domain.user_voice_prefs_get
user_voice_prefs_upsert = domain.user_voice_prefs_upsert
voice_api_credentials = domain.voice_api_credentials
voice_auth_headers = domain.voice_auth_headers
voice_stt_model = domain.voice_stt_model
voice_tts_model = domain.voice_tts_model
