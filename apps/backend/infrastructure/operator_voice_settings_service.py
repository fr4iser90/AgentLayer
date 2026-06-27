"""Infrastructure adapter for operator voice settings."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.voice import operator_voice_settings as domain
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.operator_settings import _invalidate, _sync_single_provider_endpoint
from apps.backend.infrastructure.voice_catalog_providers import (
    invalidate_voice_provider_specs_cache,
    list_voice_stt_provider_specs,
    list_voice_tts_provider_specs,
    resolve_active_voice_stt_provider_id,
    resolve_active_voice_stt_spec,
    resolve_active_voice_tts_provider_id,
    resolve_active_voice_tts_spec,
    voice_role_configured,
)


class _OperatorVoiceSettingsDeps:
    list_voice_stt_provider_specs = staticmethod(list_voice_stt_provider_specs)
    list_voice_tts_provider_specs = staticmethod(list_voice_tts_provider_specs)
    resolve_active_voice_stt_spec = staticmethod(resolve_active_voice_stt_spec)
    resolve_active_voice_tts_spec = staticmethod(resolve_active_voice_tts_spec)
    resolve_active_voice_stt_provider_id = staticmethod(resolve_active_voice_stt_provider_id)
    resolve_active_voice_tts_provider_id = staticmethod(resolve_active_voice_tts_provider_id)
    voice_role_configured = staticmethod(voice_role_configured)
    invalidate_operator_settings = staticmethod(_invalidate)
    sync_single_provider_endpoint = staticmethod(_sync_single_provider_endpoint)
    invalidate_voice_provider_specs_cache = staticmethod(invalidate_voice_provider_specs_cache)

    @staticmethod
    def apply_voice_operator_row(out: dict[str, Any]) -> None:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO operator_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
                cur.execute(
                    """
                    UPDATE operator_settings SET
                      voice_enabled = %s,
                      voice_provider_id = %s,
                      voice_stt_provider_id = %s,
                      voice_tts_provider_id = %s,
                      voice_api_base_url = %s,
                      voice_api_key = %s,
                      voice_stt_model = %s,
                      voice_tts_model = %s,
                      voice_tts_voice = %s,
                      voice_max_seconds = %s,
                      voice_max_bytes = %s,
                      voice_bridge_telegram = %s,
                      voice_bridge_discord = %s,
                      voice_realtime_enabled = %s,
                      voice_discord_vc_enabled = %s,
                      updated_at = now()
                    WHERE id = 1
                    """,
                    (
                        bool(out.get("voice_enabled")),
                        out.get("voice_provider_id"),
                        out.get("voice_stt_provider_id"),
                        out.get("voice_tts_provider_id"),
                        out.get("voice_api_base_url"),
                        out.get("voice_api_key"),
                        out.get("voice_stt_model"),
                        out.get("voice_tts_model"),
                        out.get("voice_tts_voice"),
                        out.get("voice_max_seconds"),
                        out.get("voice_max_bytes"),
                        bool(out.get("voice_bridge_telegram", True)),
                        bool(out.get("voice_bridge_discord", True)),
                        bool(out.get("voice_realtime_enabled")),
                        bool(out.get("voice_discord_vc_enabled")),
                    ),
                )
            conn.commit()


domain.register_operator_voice_settings_dependencies(_OperatorVoiceSettingsDeps())

apply_voice_operator_patch = domain.apply_voice_operator_patch
voice_settings_public_fields = domain.voice_settings_public_fields
