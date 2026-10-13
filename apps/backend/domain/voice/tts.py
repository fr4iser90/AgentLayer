"""Text-to-speech via OpenAI-compatible /audio/speech."""

from __future__ import annotations

import logging
import uuid

import httpx

from apps.backend.domain.voice import voice_policy

logger = logging.getLogger(__name__)


def synthesize_speech(
    text: str,
    *,
    user_id: uuid.UUID,
    timeout_sec: float = 120.0,
) -> tuple[bytes, str]:
    t = (text or "").strip()
    if not t:
        raise ValueError("empty text for TTS")
    if len(t) > 4096:
        t = t[:4096]

    spec = voice_policy.active_voice_tts_spec()
    if not spec or not (spec.api_key or "").strip():
        raise ValueError(
            "voice TTS not configured (set VOICE_TTS_PROVIDER_1_BASE_URL in .env or Admin → Interfaces → Platform → Voice)"
        )

    base = spec.base_url.rstrip("/")
    model = voice_policy.voice_tts_model()
    voice = voice_policy.effective_tts_voice(user_id)
    url = f"{base}/audio/speech"
    headers = {**voice_policy.voice_auth_headers(spec), "Content-Type": "application/json"}
    body = {
        "model": model,
        "input": t,
        "voice": voice,
        "response_format": "mp3",
    }

    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(url, headers=headers, json=body)
    if resp.status_code >= 400:
        logger.warning("voice TTS HTTP %s: %s", resp.status_code, resp.text[:500])
        raise ValueError(f"TTS failed ({resp.status_code})")
    return resp.content, sniff_audio_mime(resp.content, fallback=resp.headers.get("content-type"))


def sniff_audio_mime(data: bytes, *, fallback: str | None = None) -> str:
    """Report what the bytes actually are.

    We ask for ``response_format=mp3`` but the provider answers with whatever it
    emits — Piper returns WAV. Declaring WAV as ``audio/mpeg`` breaks playback in
    the browser and makes Telegram reject the clip, so the magic bytes win over the
    requested format.
    """
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    if data[:4] == b"fLaC":
        return "audio/flac"
    base = (fallback or "").split(";")[0].strip().lower()
    return base if base.startswith("audio/") else "audio/mpeg"
