"""Validate uploaded media bytes (magic) vs declared MIME."""

from __future__ import annotations


def sniff_media_mime(head: bytes) -> str | None:
    if len(head) >= 3 and head[:3] == b"ID3":
        return "audio/mpeg"
    if len(head) >= 2 and head[:2] == b"\xff\xfb":
        return "audio/mpeg"
    if len(head) >= 2 and head[:2] == b"\xff\xf3":
        return "audio/mpeg"
    if len(head) >= 2 and head[:2] == b"\xff\xf2":
        return "audio/mpeg"
    if len(head) >= 4 and head[:4] == b"fLaC":
        return "audio/flac"
    if len(head) >= 4 and head[:4] == b"OggS":
        return "audio/ogg"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"isom", b"mp41", b"mp42", b"M4A ", b"M4B "):
            return "audio/mp4"
        if brand in (b"isom", b"mp41", b"mp42", b"avc1", b"iso6"):
            return "video/mp4"
    return None


def normalized_content_type(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.split(";")[0].strip().lower()
