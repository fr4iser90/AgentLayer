"""Tests for TTS speech text preparation."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from apps.backend.domain.voice import speech_prep


def test_strip_emoji_text_uses_unicode_data_not_fixed_ranges():
    raw = "Huhu 😊 🇩🇪 👨‍👩‍👧 1️⃣ 🫠"
    out = speech_prep.strip_emoji_text(raw)
    assert "😊" not in out
    assert "🇩🇪" not in out
    assert "🫠" not in out
    assert "Huhu" in out


def test_strip_text_for_speech_removes_emojis_and_markdown():
    raw = "Huhu! 😊 Ich habe **38 Tool-Kategorien**:\n\n| Bereich | Was |\n|---|---|\n| Mail | senden |"
    out = speech_prep.strip_text_for_speech(raw)
    assert "😊" not in out
    assert "**" not in out
    assert "|" not in out
    assert "Huhu" in out
    assert "38 Tool-Kategorien" in out


def test_needs_speech_summary_for_long_or_structured_text():
    short = "Ja, das geht."
    assert speech_prep.needs_speech_summary(short) is False

    table = "| A | B |\n|---|---|\n| x | y |\n| z | w |"
    assert speech_prep.needs_speech_summary(table) is True

    long_plain = "a " * 200
    assert speech_prep.needs_speech_summary(long_plain) is True


def test_prepare_speech_text_short_reply_without_llm(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(speech_prep, "summarize_for_speech", MagicMock())
    out = speech_prep.prepare_speech_text("Ja, das geht.", language="de", use_llm_summary=True)
    assert out == "Ja, das geht."
    speech_prep.summarize_for_speech.assert_not_called()


def test_prepare_speech_text_uses_llm_summary_when_needed(monkeypatch: pytest.MonkeyPatch):
    raw = "Huhu! 😊\n\n" + "| Tool | Beschreibung |\n" * 5
    monkeypatch.setattr(
        speech_prep,
        "summarize_for_speech",
        lambda _text, language=None: "Ich habe viele Tools. Details stehen im Chat.",
    )
    out = speech_prep.prepare_speech_text(raw, language="de", use_llm_summary=True)
    assert "Details stehen im Chat" in out
    assert "😊" not in out


def test_prepare_speech_text_fallback_when_llm_fails(monkeypatch: pytest.MonkeyPatch):
    raw = "Huhu! 😊 " + "Wetter, Mail, Kalender. " * 20
    monkeypatch.setattr(speech_prep, "summarize_for_speech", lambda *_a, **_k: None)
    out = speech_prep.prepare_speech_text(raw, language="de", use_llm_summary=True)
    assert "Details findest du im Chat" in out
    assert "😊" not in out


def test_attach_speech_text_to_completion_when_voice_enabled(monkeypatch: pytest.MonkeyPatch):
    from apps.backend.application.agent_runtime.runtime import io as agent_io

    uid = uuid.uuid4()
    monkeypatch.setattr("apps.backend.domain.shared.identity.get_identity", lambda: (1, uid))
    monkeypatch.setattr(
        "apps.backend.domain.voice.voice_policy.effective_voice_output",
        lambda **kwargs: kwargs.get("channel") == "web",
    )
    monkeypatch.setattr(
        "apps.backend.domain.voice.voice_policy.effective_stt_language",
        lambda _uid: "de",
    )
    monkeypatch.setattr(
        speech_prep,
        "prepare_speech_text",
        lambda text, **kwargs: "Kurze gesprochene Zusammenfassung.",
    )

    data = {
        "choices": [
            {
                "message": {
                    "content": "Huhu! 😊 **38 Tools** mit Tabelle …",
                }
            }
        ]
    }
    out = agent_io._attach_speech_text_to_completion(data)
    assert out["speech_text"] == "Kurze gesprochene Zusammenfassung."
