"""Parse numbered ``VOICE_STT_PROVIDER_N_*`` and ``VOICE_TTS_PROVIDER_N_*`` env rows."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal

VoiceRole = Literal["stt", "tts"]
SttApiStyle = Literal["openai", "whisper_cpp"]
TtsApiStyle = Literal["openai"]
_ENV_INDEX_RE = {
    "stt": re.compile(r"^VOICE_STT_PROVIDER_(\d+)_BASE_URL$"),
    "tts": re.compile(r"^VOICE_TTS_PROVIDER_(\d+)_BASE_URL$"),
}


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
    stt_api_style: SttApiStyle = "openai"
    stt_transcribe_path: str | None = None
    source: str = "env"


def env_voice_provider_id(role: VoiceRole, index: int) -> str:
    return f"voice_{role}_provider_{int(index)}"


def _env_prefix(role: VoiceRole) -> str:
    return "VOICE_STT_PROVIDER_" if role == "stt" else "VOICE_TTS_PROVIDER_"


def _configured_env_indexes(role: VoiceRole) -> list[int]:
    indexes: set[int] = set()
    pattern = _ENV_INDEX_RE[role]
    for key, value in os.environ.items():
        m = pattern.match(key)
        if not m or not strip_env_value(value):
            continue
        try:
            indexes.add(int(m.group(1)))
        except ValueError:
            continue
    return sorted(indexes)


def _normalize_stt_api_style(raw: str | None) -> SttApiStyle:
    s = (raw or "").strip().lower().replace("-", "_")
    if s in ("whisper_cpp", "whispercpp", "whisper"):
        return "whisper_cpp"
    return "openai"


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
        stt_style = _normalize_stt_api_style(
            strip_opt(os.environ.get(f"{prefix}{n}_API_STYLE"))
            or strip_opt(os.environ.get(f"{prefix}{n}_STT_API_STYLE"))
        )
        stt_path = strip_opt(os.environ.get(f"{prefix}{n}_TRANSCRIBE_PATH")) or strip_opt(
            os.environ.get(f"{prefix}{n}_STT_PATH")
        )
    else:
        model = strip_opt(os.environ.get(f"{prefix}{n}_MODEL")) or strip_opt(
            os.environ.get(f"{prefix}{n}_MODEL_TTS")
        ) or "tts-1"
        tts_voice = (
            strip_opt(os.environ.get(f"{prefix}{n}_MODEL_TTS_VOICE"))
            or strip_opt(os.environ.get(f"{prefix}{n}_VOICE"))
            or "alloy"
        )
        stt_style = "openai"
        stt_path = None
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
        stt_api_style=stt_style,
        stt_transcribe_path=(stt_path[:256] if stt_path else None),
        source="env",
    )


def parse_voice_stt_env_providers() -> list[EnvVoiceProviderRow]:
    rows: list[EnvVoiceProviderRow] = []
    for n in _configured_env_indexes("stt"):
        row = _read_numbered_env_row("stt", n)
        if row is not None:
            rows.append(row)
    return rows


def parse_voice_tts_env_providers() -> list[EnvVoiceProviderRow]:
    rows: list[EnvVoiceProviderRow] = []
    for n in _configured_env_indexes("tts"):
        row = _read_numbered_env_row("tts", n)
        if row is not None:
            rows.append(row)
    return rows
