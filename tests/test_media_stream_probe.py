"""Tests for stream URL probing before library insert."""

from __future__ import annotations

import httpx
import pytest

from apps.backend.media import stream_probe


def test_probe_rejects_http_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_STREAM_ALLOWED_HOSTS", "radio.example")

    class FakeStream:
        def __init__(self) -> None:
            self.status_code = 404
            self.headers = httpx.Headers({})

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def iter_bytes(self, size: int):
            yield b""

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def stream(self, method: str, url: str):
            return FakeStream()

    monkeypatch.setattr(stream_probe.httpx, "Client", FakeClient)
    result = stream_probe.probe_stream_url("https://radio.example/dead.mp3")
    assert not result.ok
    assert "404" in result.error


def test_probe_rejects_html_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_STREAM_ALLOWED_HOSTS", "radio.example")

    class FakeStream:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = httpx.Headers({"content-type": "text/html"})

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def iter_bytes(self, size: int):
            yield b"<!DOCTYPE html><html><body>404</body></html>"

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def stream(self, method: str, url: str):
            return FakeStream()

    monkeypatch.setattr(stream_probe.httpx, "Client", FakeClient)
    result = stream_probe.probe_stream_url("https://radio.example/fake.mp3")
    assert not result.ok
    assert "HTML" in result.error


def test_probe_accepts_mp3_id3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_STREAM_ALLOWED_HOSTS", "radio.example")

    class FakeStream:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = httpx.Headers({"content-type": "audio/mpeg"})

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def iter_bytes(self, size: int):
            yield b"ID3\x04\x00\x00" + b"\x00" * 100

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def stream(self, method: str, url: str):
            return FakeStream()

    monkeypatch.setattr(stream_probe.httpx, "Client", FakeClient)
    result = stream_probe.probe_stream_url("https://radio.example/live.mp3")
    assert result.ok
    assert result.kind == "audio"


def test_probe_rejects_hls_without_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_STREAM_ALLOWED_HOSTS", "cast.example.de")

    manifest = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=64000\nchunk.m3u8\n"

    class FakeStream:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = httpx.Headers({"content-type": "application/vnd.apple.mpegurl"})

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def iter_bytes(self, size: int):
            yield manifest

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def stream(self, method: str, url: str):
            return FakeStream()

    monkeypatch.setattr(stream_probe.httpx, "Client", FakeClient)
    result = stream_probe.probe_stream_url("https://cast.example.de/live/master.m3u8")
    assert not result.ok
    assert "CORS" in result.error or "Access-Control" in result.error


def test_probe_accepts_hls_with_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_STREAM_ALLOWED_HOSTS", "cdn.example")

    manifest = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=64000\nchunk.m3u8\n"

    class FakeStream:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = httpx.Headers(
                {
                    "content-type": "application/vnd.apple.mpegurl",
                    "access-control-allow-origin": "*",
                }
            )

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def iter_bytes(self, size: int):
            yield manifest

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def stream(self, method: str, url: str):
            return FakeStream()

    monkeypatch.setattr(stream_probe.httpx, "Client", FakeClient)
    result = stream_probe.probe_stream_url("https://cdn.example/hls/master.m3u8")
    assert result.ok
    assert result.kind == "hls"


def test_validate_stream_for_library_returns_none_on_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stream_probe,
        "probe_stream_url",
        lambda url, timeout=12.0: stream_probe.StreamProbeResult(True, kind="audio"),
    )
    assert stream_probe.validate_stream_for_library("https://radio.example/x.mp3") is None


def test_validate_stream_for_library_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stream_probe,
        "probe_stream_url",
        lambda url, timeout=12.0: stream_probe.StreamProbeResult(False, error="dead"),
    )
    assert stream_probe.validate_stream_for_library("https://radio.example/x.mp3") == "dead"
