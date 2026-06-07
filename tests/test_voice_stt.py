"""STT client against mocked OpenAI-compatible API."""

from __future__ import annotations

import pytest

from apps.backend.domain.voice import stt, voice_policy


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, data=None, files=None):
        assert "/audio/transcriptions" in url
        assert headers and headers.get("Authorization") == "Bearer test-key"
        return _FakeResponse(200, {"text": "Hallo Agent"})


def test_transcribe_audio_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice_policy, "voice_api_credentials", lambda: ("https://api.example/v1", "test-key"))
    monkeypatch.setattr(voice_policy, "voice_stt_model", lambda: "whisper-1")
    monkeypatch.setattr(voice_policy, "effective_voice_limits", lambda: (120, 10_485_760))
    monkeypatch.setattr(stt.httpx, "Client", _FakeClient)

    result = stt.transcribe_audio(b"fake-audio", mime="audio/ogg", language="de")
    assert result.transcript == "Hallo Agent"


def test_transcribe_audio_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="empty audio"):
        stt.transcribe_audio(b"", mime="audio/ogg")
