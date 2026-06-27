"""Tests for chat audio → media library ingest."""

from __future__ import annotations

import base64
import uuid

from apps.backend.domain.agent_runtime.chat_audio_attachments import (
    format_ingested_audio_system_block,
    ingest_chat_audio_attachments,
)


def test_ingest_skips_when_no_agent_audio_parts() -> None:
    msgs = [{"role": "user", "content": "hello"}]
    assert ingest_chat_audio_attachments(msgs, tenant_id=1, user_id=uuid.uuid4()) == []


def test_format_ingested_block() -> None:
    block = format_ingested_audio_system_block(
        [{"media_item_id": "abc", "media_ref": "media:abc", "title": "track.mp3"}]
    )
    assert "media_item_id=abc" in block
    assert "track.mp3" in block


def test_parse_data_url_audio_via_ingest(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_MEDIA_LIBRARY_ENABLED", "true")
    monkeypatch.setenv("AGENT_MEDIA_USER_UPLOAD_ENABLED", "true")
    # Without DB/schema this returns [] — smoke test only parses path
    mp3 = b"ID3\x04\x00\x00" + b"\x00" * 32
    b64 = base64.b64encode(mp3).decode("ascii")
    url = f"data:audio/mpeg;base64,{b64}"
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "upload this"},
                {"type": "agent_audio", "audio_url": {"url": url}, "agent_filename": "t.mp3"},
            ],
        }
    ]
    out = ingest_chat_audio_attachments(msgs, tenant_id=1, user_id=uuid.uuid4())
    assert isinstance(out, list)
