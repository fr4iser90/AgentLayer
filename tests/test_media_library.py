"""Unit tests for media library helpers."""

from __future__ import annotations

from apps.backend.media import media_policy
from apps.backend.media.upload_bytes import sniff_media_mime


def test_sniff_mp3_id3() -> None:
    assert sniff_media_mime(b"ID3\x04\x00\x00") == "audio/mpeg"


def test_sniff_flac() -> None:
    assert sniff_media_mime(b"fLaC\x00\x00\x00") == "audio/flac"


def test_sniff_ogg() -> None:
    assert sniff_media_mime(b"OggS\x00\x02") == "audio/ogg"


def test_embed_url_allowed_youtube(monkeypatch) -> None:
    monkeypatch.setenv(
        "AGENT_MEDIA_EMBED_ALLOWED_HOSTS",
        "www.youtube.com,youtube.com",
    )
    assert media_policy.embed_url_allowed("https://www.youtube.com/embed/abc123")
    assert not media_policy.embed_url_allowed("http://www.youtube.com/embed/abc123")
    assert not media_policy.embed_url_allowed("https://evil.test/embed")


def test_env_overrides_media_library_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_LIBRARY_ENABLED", "true")
    assert media_policy.effective_media_library_enabled() is True
    monkeypatch.setenv("AGENT_MEDIA_LIBRARY_ENABLED", "false")
    assert media_policy.effective_media_library_enabled() is False


def test_stream_url_allowed_mdr(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_STREAM_ALLOWED_HOSTS", "cast.addradio.de,mdr.de")
    assert media_policy.stream_url_allowed("https://cast.addradio.de/mdr/jump/live/mp3/stream")
    assert not media_policy.stream_url_allowed("https://evil.test/stream.mp3")
