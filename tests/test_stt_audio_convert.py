"""STT audio normalization for whisper.cpp."""

from __future__ import annotations

import shutil
import wave
from io import BytesIO

import pytest

from apps.backend.domain.voice.stt_audio_convert import ensure_whisper_wav


def _tiny_wav() -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


def test_wav_passthrough() -> None:
    wav = _tiny_wav()
    out, mime = ensure_whisper_wav(wav, "audio/wav")
    assert out == wav
    assert mime == "audio/wav"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_webm_converts_to_wav() -> None:
    # Minimal webm is hard to synthesize; use wav labeled as webm to force ffmpeg path.
    wav = _tiny_wav()
    out, mime = ensure_whisper_wav(wav, "audio/webm")
    assert mime == "audio/wav"
    assert out.startswith(b"RIFF")
    assert len(out) > 44
