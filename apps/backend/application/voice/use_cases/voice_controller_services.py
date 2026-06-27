from __future__ import annotations

from apps.backend.infrastructure.providers.model_access_policy import is_provider_capability_allowed
from apps.backend.infrastructure.voice.voice_catalog_providers import (
    resolve_active_voice_stt_provider_id,
    resolve_active_voice_tts_provider_id,
    voice_role_configured,
)
