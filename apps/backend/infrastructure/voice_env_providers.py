"""Parse numbered ``VOICE_STT_PROVIDER_N_*`` and ``VOICE_TTS_PROVIDER_N_*`` env rows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

VOICE_ENV_PROVIDER_MAX = 32

VoiceRole = Literal["stt", "tts"]


def strip_env_value(raw: str | None) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


def strip_opt(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


@dataclass(frozen=True)
class EnvVoiceProviderRow:
    role: VoiceRole
    index: int
    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model: str
    model_tts_voice: str | None = None
    source: str = "env"


def env_voice_provider_id(role: VoiceRole, index: int) -> str:
    return f"voice_{role}_provider_{int(index)}"


def _env_prefix(role: VoiceRole) -> str:
    return "VOICE_STT_PROVIDER_" if role == "stt" else "VOICE_TTS_PROVIDER_"


def _read_numbered_env_row(role: VoiceRole, n: int) -> EnvVoiceProviderRow | None:
    prefix = _env_prefix(role)
    base = strip_env_value(os.environ.get(f"{prefix}{n}_BASE_URL")).rstrip("/")
    if not base:
        return None
    label = strip_env_value(os.environ.get(f"{prefix}{n}_LABEL")) or (
        f"Voice STT {n}" if role == "stt" else f"Voice TTS {n}"
    )
    api_key = strip_env_value(os.environ.get(f"{prefix}{n}_API_KEY"))
    header = (
        strip_env_value(os.environ.get(f"{prefix}{n}_API_HEADER_NAME")) or "Authorization"
    )
    if role == "stt":
        model = strip_opt(os.environ.get(f"{prefix}{n}_MODEL")) or strip_opt(
            os.environ.get(f"{prefix}{n}_MODEL_STT")
        ) or "whisper-1"
        tts_voice = None
    else:
        model = strip_opt(os.environ.get(f"{prefix}{n}_MODEL")) or strip_opt(
            os.environ.get(f"{prefix}{n}_MODEL_TTS")
        ) or "tts-1"
        tts_voice = (
            strip_opt(os.environ.get(f"{prefix}{n}_MODEL_TTS_VOICE"))
            or strip_opt(os.environ.get(f"{prefix}{n}_VOICE"))
            or "alloy"
        )
    return EnvVoiceProviderRow(
        role=role,
        index=n,
        provider_id=env_voice_provider_id(role, n),
        label=label[:128],
        base_url=base,
        api_key=api_key,
        api_header_name=header[:128],
        model=(model or ("whisper-1" if role == "stt" else "tts-1"))[:128],
        model_tts_voice=tts_voice[:64] if tts_voice else None,
        source="env",
    )


def parse_voice_stt_env_providers() -> list[EnvVoiceProviderRow]:
    rows: list[EnvVoiceProviderRow] = []
    for n in range(1, VOICE_ENV_PROVIDER_MAX + 1):
        row = _read_numbered_env_row("stt", n)
        if row is not None:
            rows.append(row)
    return rows


def parse_voice_tts_env_providers() -> list[EnvVoiceProviderRow]:
    rows: list[EnvVoiceProviderRow] = []
    for n in range(1, VOICE_ENV_PROVIDER_MAX + 1):
        row = _read_numbered_env_row("tts", n)
        if row is not None:
            rows.append(row)
    return rows
