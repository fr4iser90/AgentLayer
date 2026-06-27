"""Voice schema validation."""
from __future__ import annotations


def validate_speech_text(text: str, *, max_chars: int = 5000) -> str:
    value = text.strip()
    if not value:
        raise ValueError("speech text must not be blank")
    if len(value) > max_chars:
        raise ValueError("speech text exceeds provider limit")
    return value


def validate_language_tag(language: str | None) -> str | None:
    value = (language or "").strip()
    if not value:
        return None
    if len(value) > 16:
        raise ValueError("voice language tag is too long")
    return value
