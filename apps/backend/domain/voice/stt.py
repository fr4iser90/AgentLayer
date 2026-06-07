"""Speech-to-text — OpenAI /audio/transcriptions or whisper.cpp /inference."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from apps.backend.domain.voice import voice_policy
from apps.backend.domain.voice.stt_audio_convert import ensure_whisper_wav
from apps.backend.infrastructure.voice_catalog_providers import VoiceProviderSpec

logger = logging.getLogger(__name__)

_MIN_WHISPER_WAV_BYTES = 12_000  # ~0.35 s @ 16 kHz mono PCM16
_BLANK_TRANSCRIPT_MARKERS = frozenset(
    {"[blank_audio]", "(silence)", "[silence]", "[music]", "[música]"}
)


@dataclass
class SttResult:
    transcript: str
    language: str | None = None
    duration_ms: int | None = None


def _guess_filename(mime: str) -> str:
    m = (mime or "").split(";")[0].strip().lower()
    ext = {
        "audio/ogg": ".ogg",
        "audio/opus": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }.get(m, ".audio")
    return f"audio{ext}"


def _stt_url(spec: VoiceProviderSpec) -> str:
    base = spec.base_url.rstrip("/")
    if spec.stt_transcribe_path:
        path = spec.stt_transcribe_path.strip()
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"
    if spec.stt_api_style == "whisper_cpp":
        return f"{base}/inference"
    return f"{base}/audio/transcriptions"


def _stt_form_data(spec: VoiceProviderSpec, *, language: str | None) -> dict[str, Any]:
    if spec.stt_api_style == "whisper_cpp":
        data: dict[str, Any] = {"response_format": "json"}
        if language:
            data["language"] = language[:16]
        return data
    model = voice_policy.voice_stt_model()
    data = {"model": model}
    if language:
        data["language"] = language[:16]
    return data


def _normalize_transcript(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    low = t.lower()
    if low in _BLANK_TRANSCRIPT_MARKERS:
        return ""
    return t


def _parse_stt_response(spec: VoiceProviderSpec, resp: httpx.Response) -> str:
    raw = (resp.text or "").strip()
    if not raw:
        return ""
    ctype = (resp.headers.get("content-type") or "").lower()
    if spec.stt_api_style == "whisper_cpp" and "json" not in ctype:
        return _normalize_transcript(raw)
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        return _normalize_transcript(raw)
    if not isinstance(payload, dict):
        return _normalize_transcript(raw)
    for key in ("text", "transcript", "transcription"):
        val = payload.get(key)
        if isinstance(val, str):
            norm = _normalize_transcript(val)
            if norm:
                return norm
    # whisper verbose_json may nest under segments — concatenate
    segs = payload.get("segments")
    if isinstance(segs, list):
        parts = []
        for seg in segs:
            if isinstance(seg, dict):
                t = seg.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
        if parts:
            return " ".join(parts).strip()
    return ""


def transcribe_audio(
    audio: bytes,
    *,
    mime: str = "audio/ogg",
    language: str | None = None,
    timeout_sec: float = 120.0,
) -> SttResult:
    if not audio:
        raise ValueError("empty audio")
    _max_sec, max_b = voice_policy.effective_voice_limits()
    if len(audio) > max_b:
        raise ValueError(f"audio too large (max {max_b} bytes)")

    from apps.backend.infrastructure.voice_catalog_providers import (
        resolve_active_voice_stt_spec,
        voice_auth_headers,
    )

    spec = resolve_active_voice_stt_spec()
    if not spec or not (spec.api_key or "").strip():
        raise ValueError(
            "voice STT not configured (set VOICE_STT_PROVIDER_1_BASE_URL in .env or Admin → Interfaces → Platform → Voice)"
        )

    upload_audio = audio
    upload_mime = mime or "application/octet-stream"
    if spec.stt_api_style == "whisper_cpp":
        upload_audio, upload_mime = ensure_whisper_wav(audio, upload_mime)
        if len(upload_audio) < _MIN_WHISPER_WAV_BYTES:
            raise ValueError(
                "recording too short — hold the mic button, speak, then release"
            )

    url = _stt_url(spec)
    data = _stt_form_data(spec, language=language)
    files = {
        "file": (_guess_filename(upload_mime), upload_audio, upload_mime),
    }
    headers = voice_auth_headers(spec)

    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(url, headers=headers, data=data, files=files)
    if resp.status_code >= 400:
        body = resp.text[:500]
        logger.warning("voice STT HTTP %s %s: %s", resp.status_code, url, body)
        raise ValueError(f"STT failed ({resp.status_code})")

    transcript = _parse_stt_response(spec, resp)
    if not transcript:
        logger.info(
            "voice STT empty transcript url=%s bytes_in=%s wav_out=%s body=%s",
            url,
            len(audio),
            len(upload_audio),
            (resp.text or "")[:200],
        )
        raise ValueError(
            "no speech detected — hold the mic button longer and speak clearly"
        )
    return SttResult(transcript=transcript, language=language)
