"""STT client — OpenAI /audio/transcriptions and whisper.cpp /inference."""

from __future__ import annotations

import pytest

from apps.backend.domain.voice import stt, voice_policy
from apps.backend.infrastructure.voice_catalog_providers import VoiceProviderSpec


def _stt_spec(
    *,
    api_style: str = "openai",
    transcribe_path: str | None = None,
    header: str = "Authorization",
) -> VoiceProviderSpec:
    return VoiceProviderSpec(
        role="stt",
        provider_id="voice_stt_provider_1",
        label="Test STT",
        base_url="https://stt.example.com",
        api_key="test-key",
        api_header_name=header,
        model_stt="whisper-1",
        stt_api_style=api_style,  # type: ignore[arg-type]
        stt_transcribe_path=transcribe_path,
    )


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | str, *, content_type: str = "application/json") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = payload if isinstance(payload, str) else str(payload)
        self.headers = {"content-type": content_type}

    def json(self) -> dict:
        if isinstance(self._payload, dict):
            return self._payload
        raise ValueError("not json")


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.last_url: str | None = None
        self.last_data: dict | None = None
        self.last_headers: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, data=None, files=None):
        self.last_url = url
        self.last_data = data
        self.last_headers = headers
        return _FakeResponse(200, {"text": "Hallo Agent"})


def test_transcribe_openai_style(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()

    monkeypatch.setattr(voice_policy, "active_voice_stt_spec", lambda: _stt_spec())
    monkeypatch.setattr(voice_policy, "voice_stt_model", lambda: "whisper-1")
    monkeypatch.setattr(voice_policy, "effective_voice_limits", lambda: (120, 10_485_760))
    monkeypatch.setattr(stt.httpx, "Client", lambda *a, **k: fake)

    result = stt.transcribe_audio(b"fake-audio", mime="audio/ogg", language="de")
    assert result.transcript == "Hallo Agent"
    assert fake.last_url == "https://stt.example.com/audio/transcriptions"
    assert fake.last_data == {"model": "whisper-1", "language": "de"}
    assert fake.last_headers and fake.last_headers.get("Authorization") == "Bearer test-key"


def test_transcribe_whisper_cpp_style(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()

    monkeypatch.setattr(
        voice_policy,
        "active_voice_stt_spec",
        lambda: _stt_spec(api_style="whisper_cpp", header="X-API-KEY"),
    )
    monkeypatch.setattr(voice_policy, "effective_voice_limits", lambda: (120, 10_485_760))
    monkeypatch.setattr(stt.httpx, "Client", lambda *a, **k: fake)
    monkeypatch.setattr(
        stt,
        "ensure_whisper_wav",
        lambda audio, mime: (b"x" * 20000, "audio/wav"),
    )

    result = stt.transcribe_audio(b"fake-audio", mime="audio/ogg", language="de")
    assert result.transcript == "Hallo Agent"
    assert fake.last_url == "https://stt.example.com/inference"
    assert fake.last_data == {"response_format": "json", "language": "de"}
    assert fake.last_headers and fake.last_headers.get("X-API-KEY") == "test-key"
    assert "model" not in (fake.last_data or {})


def test_transcribe_custom_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()

    monkeypatch.setattr(
        voice_policy,
        "active_voice_stt_spec",
        lambda: _stt_spec(api_style="whisper_cpp", transcribe_path="/v1/transcribe"),
    )
    monkeypatch.setattr(voice_policy, "effective_voice_limits", lambda: (120, 10_485_760))
    monkeypatch.setattr(stt.httpx, "Client", lambda *a, **k: fake)
    monkeypatch.setattr(
        stt,
        "ensure_whisper_wav",
        lambda audio, mime: (b"x" * 20000, "audio/wav"),
    )

    stt.transcribe_audio(b"fake-audio", mime="audio/wav")
    assert fake.last_url == "https://stt.example.com/v1/transcribe"


def test_transcribe_audio_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="empty audio"):
        stt.transcribe_audio(b"", mime="audio/ogg")


def test_empty_whisper_transcript_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EmptyResp:
        status_code = 200
        text = '{"text":""}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"text": ""}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _EmptyResp()

    monkeypatch.setattr(voice_policy, "active_voice_stt_spec", lambda: _stt_spec(api_style="whisper_cpp"))
    monkeypatch.setattr(voice_policy, "effective_voice_limits", lambda: (120, 10_485_760))
    monkeypatch.setattr(stt, "ensure_whisper_wav", lambda audio, mime: (b"x" * 20000, "audio/wav"))
    monkeypatch.setattr(stt.httpx, "Client", lambda *a, **k: _Client())

    with pytest.raises(ValueError, match="no speech detected"):
        stt.transcribe_audio(b"audio", mime="audio/webm")
