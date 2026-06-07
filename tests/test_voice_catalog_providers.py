"""Voice provider catalog resolution (explicit STT/TTS chains)."""

from __future__ import annotations

import os
from unittest.mock import patch

from apps.backend.infrastructure.voice_catalog_providers import (
    invalidate_voice_provider_specs_cache,
    resolve_active_voice_stt_provider_id,
    resolve_active_voice_tts_provider_id,
)


def test_stt_and_tts_from_separate_chains() -> None:
    invalidate_voice_provider_specs_cache()
    env = {
        "VOICE_STT_PROVIDER_1_BASE_URL": "https://stt.example.com",
        "VOICE_STT_PROVIDER_1_API_KEY": "stt-key",
        "VOICE_TTS_PROVIDER_1_BASE_URL": "https://tts.example.com",
        "VOICE_TTS_PROVIDER_1_API_KEY": "tts-key",
    }
    with patch.dict(os.environ, env, clear=True):
        assert resolve_active_voice_stt_provider_id() == "voice_stt_provider_1"
        assert resolve_active_voice_tts_provider_id() == "voice_tts_provider_1"


def test_stt_only_no_tts() -> None:
    invalidate_voice_provider_specs_cache()
    env = {
        "VOICE_STT_PROVIDER_1_BASE_URL": "https://stt.example.com",
        "VOICE_STT_PROVIDER_1_API_KEY": "k",
    }
    with patch.dict(os.environ, env, clear=True):
        assert resolve_active_voice_stt_provider_id() == "voice_stt_provider_1"
        assert resolve_active_voice_tts_provider_id() is None


def test_legacy_voice_provider_n_ignored() -> None:
    invalidate_voice_provider_specs_cache()
    env = {
        "VOICE_PROVIDER_1_BASE_URL": "https://old.example.com",
        "VOICE_PROVIDER_1_API_KEY": "k",
    }
    with patch.dict(os.environ, env, clear=True):
        assert resolve_active_voice_stt_provider_id() is None
        assert resolve_active_voice_tts_provider_id() is None
