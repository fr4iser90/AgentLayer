"""VOICE_STT_PROVIDER_N_* and VOICE_TTS_PROVIDER_N_* env parsing."""

from __future__ import annotations

import os
from unittest.mock import patch

from apps.backend.infrastructure.voice_env_providers import (
    parse_voice_stt_env_providers,
    parse_voice_tts_env_providers,
)


def test_numbered_stt_providers() -> None:
    env = {
        "VOICE_STT_PROVIDER_1_BASE_URL": "https://stt.example.com",
        "VOICE_STT_PROVIDER_1_LABEL": "Whisper",
        "VOICE_STT_PROVIDER_1_API_KEY": "stt-key",
        "VOICE_STT_PROVIDER_1_MODEL": "whisper-1",
    }
    with patch.dict(os.environ, env, clear=False):
        rows = parse_voice_stt_env_providers()
    assert len(rows) == 1
    assert rows[0].provider_id == "voice_stt_provider_1"
    assert rows[0].role == "stt"
    assert rows[0].model == "whisper-1"
    assert rows[0].stt_api_style == "openai"


def test_stt_whisper_cpp_api_style() -> None:
    env = {
        "VOICE_STT_PROVIDER_1_BASE_URL": "https://stt.example.com",
        "VOICE_STT_PROVIDER_1_API_KEY": "k",
        "VOICE_STT_PROVIDER_1_API_STYLE": "whisper_cpp",
        "VOICE_STT_PROVIDER_1_TRANSCRIBE_PATH": "/inference",
    }
    with patch.dict(os.environ, env, clear=False):
        row = parse_voice_stt_env_providers()[0]
    assert row.stt_api_style == "whisper_cpp"
    assert row.stt_transcribe_path == "/inference"


def test_numbered_tts_providers() -> None:
    env = {
        "VOICE_TTS_PROVIDER_1_BASE_URL": "https://tts.example.com",
        "VOICE_TTS_PROVIDER_1_LABEL": "Piper",
        "VOICE_TTS_PROVIDER_1_API_KEY": "tts-key",
        "VOICE_TTS_PROVIDER_1_MODEL": "tts-1",
    }
    with patch.dict(os.environ, env, clear=False):
        rows = parse_voice_tts_env_providers()
    assert len(rows) == 1
    assert rows[0].provider_id == "voice_tts_provider_1"
    assert rows[0].role == "tts"


def test_empty_when_no_providers() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert parse_voice_stt_env_providers() == []
        assert parse_voice_tts_env_providers() == []
