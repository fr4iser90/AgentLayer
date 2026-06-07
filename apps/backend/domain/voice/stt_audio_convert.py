"""Normalize browser/bridge audio to 16 kHz mono WAV for whisper.cpp."""

from __future__ import annotations

import shutil
import subprocess


def _is_wav_mime(mime: str) -> bool:
    m = (mime or "").split(";")[0].strip().lower()
    return m in ("audio/wav", "audio/x-wav", "audio/wave")


def ensure_whisper_wav(audio: bytes, mime: str) -> tuple[bytes, str]:
    """Return PCM WAV suitable for whisper.cpp ``read_audio_data``."""
    if not audio:
        raise ValueError("empty audio")
    if _is_wav_mime(mime):
        return audio, "audio/wav"

    if not shutil.which("ffmpeg"):
        raise ValueError(
            "whisper.cpp needs WAV audio (browser sends webm/ogg). "
            "Install ffmpeg in agent-layer or start whisper-server with --convert"
        )

    proc = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ],
        input=audio,
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode(errors="replace").strip()[:400]
        raise ValueError(f"audio conversion failed{f': {err}' if err else ''}")
    return proc.stdout, "audio/wav"
