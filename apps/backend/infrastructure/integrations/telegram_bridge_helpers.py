"""Small pure helpers for the Telegram bridge adapter."""
from __future__ import annotations

import os
from typing import Any

from apps.backend.domain.shared.bridge_formatting import chunk_markdown

_EXT_TO_MIME = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".amr": "audio/amr",
    ".aif": "audio/aiff",
    ".aiff": "audio/aiff",
}


def audio_document(document: Any) -> str | None:
    """Return the mime type when a Telegram *document* is really audio, else ``None``.

    Telegram does not normalise this: the same mp3 arrives on ``message.audio`` when
    sent from the media picker and on ``message.document`` when attached as a file.
    Some clients also mislabel audio as ``application/octet-stream``, so the file
    extension is the second source of truth.
    """
    if document is None:
        return None
    mime = (getattr(document, "mime_type", "") or "").split(";")[0].strip().lower()
    if mime.startswith("audio/"):
        return mime
    ext = os.path.splitext((getattr(document, "file_name", "") or "").lower())[1]
    return _EXT_TO_MIME.get(ext)


def audio_mime(payload: Any, *, default: str = "audio/ogg") -> str:
    """Best-effort mime for a Telegram audio-ish object, falling back to extension."""
    mime = (getattr(payload, "mime_type", "") or "").split(";")[0].strip().lower()
    if mime.startswith("audio/"):
        return mime
    ext = os.path.splitext((getattr(payload, "file_name", "") or "").lower())[1]
    return _EXT_TO_MIME.get(ext, default)


def select_audio_payload(message: Any) -> tuple[Any, str] | None:
    """Return ``(payload, mime)`` for a message carrying audio, else ``None``.

    Telegram splits the same user intent across three shapes: a recording lands on
    ``message.voice``, a media-picker upload on ``message.audio``, and a file
    attached from disk on ``message.document``. The payload object and its mime are
    resolved together here so a caller never confuses the two.
    """
    if message is None:
        return None
    audio = getattr(message, "audio", None)
    if audio is not None:
        return audio, audio_mime(audio)
    document = getattr(message, "document", None)
    mime = audio_document(document)
    if mime is None:
        return None
    return document, mime


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    return chunk_markdown(text, limit=limit)


def extract_reply(data: dict[str, Any]) -> str:
    err = data.get("error") or data.get("detail")
    if isinstance(err, dict):
        err = err.get("message") or str(err)
    if err and not data.get("choices"):
        return f"AgentLayer error: {err}"
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return f"Unexpected response: {data!r:.2000}"
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return f"(no text in response: {data!r:.1500})"


def normalize_bot_token(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return "".join(s.split())
