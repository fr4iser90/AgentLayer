"""Voice provider catalog resolution (explicit STT/TTS chains)."""

from __future__ import annotations

import os
from unittest.mock import patch

from apps.backend.infrastructure.voice_catalog_providers import (
    list_voice_stt_provider_specs,
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


def test_voice_env_provider_scans_sparse_high_indexes() -> None:
    invalidate_voice_provider_specs_cache()
    env = {
        "VOICE_STT_PROVIDER_1000_BASE_URL": "https://stt-high.example.com",
        "VOICE_TTS_PROVIDER_1000_BASE_URL": "https://tts-high.example.com",
    }
    with patch.dict(os.environ, env, clear=True):
        assert resolve_active_voice_stt_provider_id() == "voice_stt_provider_1000"
        assert resolve_active_voice_tts_provider_id() == "voice_tts_provider_1000"


def test_voice_db_endpoint_gets_llm_style_provider_id(monkeypatch) -> None:
    from apps.backend.infrastructure.db import db

    invalidate_voice_provider_specs_cache()
    monkeypatch.setattr(
        db,
        "operator_provider_endpoints_list_all",
        lambda kind=None: [
            {
                "id": 1,
                "kind": "voice_stt",
                "sort_order": 0,
                "enabled": True,
                "label": "STT",
                "base_url": "https://stt-db.example/v1",
                "api_key": "secret",
                "api_header_name": "Authorization",
                "model_default": "whisper-large",
                "options_json": {},
            }
        ]
        if kind == "voice_stt"
        else [],
    )
    with patch.dict(os.environ, {}, clear=True):
        specs = list_voice_stt_provider_specs(force_refresh=True)

    assert [s.provider_id for s in specs] == ["voice_stt_provider_db_1"]
    assert specs[0].source == "db"
