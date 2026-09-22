"""TTS response MIME must reflect the bytes, not the requested format."""

from __future__ import annotations

from apps.backend.domain.voice.tts import sniff_audio_mime


def test_riff_wave_is_detected_as_wav() -> None:
    data = b"RIFF\x00\x10\x00\x00WAVEfmt " + b"\x00" * 32
    assert sniff_audio_mime(data) == "audio/wav"


def test_id3_mp3() -> None:
    assert sniff_audio_mime(b"ID3\x03\x00\x00\x00\x00\x00\x09") == "audio/mpeg"


def test_mpeg_frame_sync_without_id3() -> None:
    assert sniff_audio_mime(b"\xff\xfb\x90\x64" + b"\x00" * 20) == "audio/mpeg"


def test_ogg_and_mp4_and_flac() -> None:
    assert sniff_audio_mime(b"OggS\x00\x02") == "audio/ogg"
    assert sniff_audio_mime(b"\x00\x00\x00 ftypM4A ") == "audio/mp4"
    assert sniff_audio_mime(b"fLaC\x00\x00\x00\x22") == "audio/flac"


def test_fallback_used_when_bytes_are_unrecognized() -> None:
    assert sniff_audio_mime(b"???", fallback="audio/ogg") == "audio/ogg"


def test_non_audio_fallback_collapses_to_mpeg() -> None:
    assert sniff_audio_mime(b"???", fallback="application/json") == "audio/mpeg"
    assert sniff_audio_mime(b"") == "audio/mpeg"


def test_mime_parameters_are_stripped_from_fallback() -> None:
    assert sniff_audio_mime(b"???", fallback="audio/wav; codecs=1") == "audio/wav"


def test_magic_bytes_beat_a_lying_content_type_header() -> None:
    # Piper answers WAV bytes; a header claiming mpeg must not win.
    wav = b"RIFF\x00\x10\x00\x00WAVEfmt " + b"\x00" * 32
    assert sniff_audio_mime(wav, fallback="audio/mpeg") == "audio/wav"
