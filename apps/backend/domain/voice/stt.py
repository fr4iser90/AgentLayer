"""Speech-to-text via OpenAI-compatible /audio/transcriptions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from apps.backend.domain.voice import voice_policy

logger = logging.getLogger(__name__)


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

    base = spec.base_url.rstrip("/")
    model = voice_policy.voice_stt_model()
    url = f"{base}/audio/transcriptions"
    data: dict[str, Any] = {"model": model}
    if language:
        data["language"] = language[:16]

    files = {"file": (_guess_filename(mime), audio, mime or "application/octet-stream")}
    headers = voice_auth_headers(spec)

    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(url, headers=headers, data=data, files=files)
    if resp.status_code >= 400:
        body = resp.text[:500]
        logger.warning("voice STT HTTP %s: %s", resp.status_code, body)
        raise ValueError(f"STT failed ({resp.status_code})")

    payload = resp.json()
    text = (payload.get("text") if isinstance(payload, dict) else None) or ""
    transcript = str(text).strip()
    if not transcript:
        raise ValueError("STT returned empty transcript")
    return SttResult(transcript=transcript, language=language)
