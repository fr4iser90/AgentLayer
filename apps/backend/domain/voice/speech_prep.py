"""Prepare assistant chat text for TTS (strip formatting, summarize when needed)."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SpeechPrepDependencies(Protocol):
    def post_catalog_chat_completions(self, **kwargs: Any) -> tuple[dict[str, Any], Any]: ...


_deps: SpeechPrepDependencies | None = None


def register_speech_prep_dependencies(deps: SpeechPrepDependencies) -> None:
    global _deps
    _deps = deps


def post_catalog_chat_completions(**kwargs: Any) -> tuple[dict[str, Any], Any]:
    if _deps is None:
        raise RuntimeError("speech prep dependencies not registered")
    return _deps.post_catalog_chat_completions(**kwargs)

_SPEECH_MAX_CHARS = 500
_SUMMARY_TRIGGER_CHARS = 280

# Joiners / modifiers inside emoji grapheme clusters (ZWJ, skin tone, VS16, …).
_EMOJI_CLUSTER_EXTRA = frozenset(
    {
        0x200D,  # ZWJ
        0xFE0E,
        0xFE0F,
        *range(0x1F3FB, 0x1F400),
        *range(0xE0020, 0xE0080),
    }
)


def _is_emoji_codepoint(cp: int) -> bool:
    try:
        import emoji as _emoji

        return cp in _emoji.EMOJI_DATA
    except ImportError:
        pass
    if cp in _EMOJI_CLUSTER_EXTRA:
        return True
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return True
    try:
        ch = chr(cp)
    except ValueError:
        return False
    if unicodedata.category(ch) not in ("So", "Sk"):
        return False
    name = unicodedata.name(ch, "")
    return any(
        token in name
        for token in ("EMOJI", "FACE", "SMILING", "SMILE", "HEART", "HAND", "FLAG")
    )


def _strip_emoji_text_fallback(text: str) -> str:
    """Stdlib fallback when the optional ``emoji`` package is not installed."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        cp = ord(text[i])
        if _is_emoji_codepoint(cp):
            while i < n and _is_emoji_codepoint(ord(text[i])):
                i += 1
            if out and out[-1] != " ":
                out.append(" ")
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def strip_emoji_text(text: str) -> str:
    """Remove emoji graphemes using the ``emoji`` package when available."""
    raw = text or ""
    if not raw:
        return ""
    try:
        import emoji as _emoji

        return _emoji.replace_emoji(raw, replace=" ")
    except ImportError:
        logger.debug("emoji package not installed — using stdlib emoji fallback")
        return _strip_emoji_text_fallback(raw)


def _language_instruction(language: str | None) -> str:
    lang = (language or "de").strip().lower()
    if lang.startswith("de"):
        return "Antworte auf Deutsch."
    if lang.startswith("en"):
        return "Respond in English."
    return f"Respond in the user's language ({lang})."


def strip_text_for_speech(text: str) -> str:
    """Deterministic cleanup: markdown, emojis, tables, URLs — plain speakable text."""
    t = (text or "").strip()
    if not t:
        return ""

    t = strip_emoji_text(t)
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`[^`]+`", " ", t)
    t = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\|", " ", t)
    t = re.sub(r"[-=]{3,}", " ", t)
    t = re.sub(r"[#*_~>|]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def needs_speech_summary(text: str, *, stripped: str | None = None) -> bool:
    """Heuristic: long or heavily structured replies need a spoken summary."""
    raw = (text or "").strip()
    if not raw:
        return False
    plain = stripped if stripped is not None else strip_text_for_speech(raw)
    if len(plain) > _SUMMARY_TRIGGER_CHARS:
        return True
    if raw.count("|") >= 6:
        return True
    bullet_lines = sum(1 for line in raw.splitlines() if re.match(r"^\s*[-*+]\s+", line))
    if bullet_lines >= 3:
        return True
    numbered_lines = sum(1 for line in raw.splitlines() if re.match(r"^\s*\d+\.\s+", line))
    if numbered_lines >= 3:
        return True
    if re.search(r"^\|.+\|$", raw, flags=re.MULTILINE):
        return True
    return False


def _truncate_for_speech(text: str, *, max_chars: int = _SPEECH_MAX_CHARS) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    cut = t[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return (cut or t[: max_chars - 1]).rstrip(".,;:") + "…"


def _fallback_speech_text(stripped: str, *, language: str | None) -> str:
    lang = (language or "de").strip().lower()
    if not stripped:
        return "Die Antwort steht im Chat." if lang.startswith("de") else "The answer is in the chat."
    parts = re.split(r"(?<=[.!?])\s+", stripped)
    short = " ".join(parts[:3]).strip() or stripped
    suffix = (
        " Die Details findest du im Chat."
        if lang.startswith("de")
        else " See the chat for details."
    )
    return _truncate_for_speech(short + suffix)


def summarize_for_speech(text: str, *, language: str | None = None) -> str | None:
    """One short LLM call for a natural spoken summary. Returns None on failure."""
    payload = (text or "").strip()
    if not payload:
        return None
    try:
        data, _ = post_catalog_chat_completions(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You rewrite assistant replies for text-to-speech. "
                        "Output 1-3 short spoken sentences only. "
                        "No markdown, emojis, lists, tables, URLs, or tool names. "
                        "Do not read headings or bullet labels aloud. "
                        "Mention that full details are in the chat when the source is long or structured. "
                        + _language_instruction(language)
                    ),
                },
                {
                    "role": "user",
                    "content": payload[:3000],
                },
            ],
            temperature=0,
            max_tokens=180,
            timeout=15.0,
            stream=False,
        )
        choice0 = (data.get("choices") or [{}])[0]
        msg = choice0.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return strip_text_for_speech(content.strip())
    except Exception:
        logger.debug("speech summary LLM failed", exc_info=True)
    return None


def prepare_speech_text(
    text: str,
    *,
    language: str | None = None,
    max_chars: int = _SPEECH_MAX_CHARS,
    use_llm_summary: bool = True,
) -> str:
    """Return speakable text: stripped plain for short replies, summarized when needed."""
    raw = (text or "").strip()
    if not raw:
        return ""

    stripped = strip_text_for_speech(raw)
    if not stripped:
        return _fallback_speech_text("", language=language)

    if not needs_speech_summary(raw, stripped=stripped):
        return _truncate_for_speech(stripped, max_chars=max_chars)

    if use_llm_summary:
        summary = summarize_for_speech(raw, language=language)
        if summary:
            return _truncate_for_speech(summary, max_chars=max_chars)

    return _truncate_for_speech(_fallback_speech_text(stripped, language=language), max_chars=max_chars)
