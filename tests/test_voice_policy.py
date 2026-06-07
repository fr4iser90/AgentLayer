"""Voice policy effective flags."""

from __future__ import annotations

import uuid

import pytest

from apps.backend.domain.voice import voice_policy


def test_effective_voice_input_web_requires_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        voice_policy,
        "operator_voice_row",
        lambda: {"voice_enabled": True},
    )
    uid = uuid.uuid4()

    def fake_prefs(_uid: uuid.UUID) -> dict:
        return {
            "input_enabled": True,
            "output_enabled": False,
            "language": "de",
            "voice_id": None,
            "mode_web": "off",
            "mode_telegram": "text_only",
            "mode_discord": "text_only",
            "edit_transcript_before_send": True,
        }

    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", fake_prefs)
    assert voice_policy.effective_voice_input(user_id=uid, channel="web") is False

    def fake_prefs_ptt(_uid: uuid.UUID) -> dict:
        d = fake_prefs(_uid)
        d["mode_web"] = "push_to_talk"
        return d

    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", fake_prefs_ptt)
    assert voice_policy.effective_voice_input(user_id=uid, channel="web") is True

    def fake_prefs_toggle(_uid: uuid.UUID) -> dict:
        d = fake_prefs_ptt(_uid)
        d["mode_web"] = "toggle"
        return d

    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", fake_prefs_toggle)
    assert voice_policy.effective_voice_input(user_id=uid, channel="web") is True


def test_effective_voice_output_telegram_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        voice_policy,
        "operator_voice_row",
        lambda: {"voice_enabled": True},
    )
    uid = uuid.uuid4()

    def prefs_text_only(_uid: uuid.UUID) -> dict:
        return {
            "input_enabled": True,
            "output_enabled": True,
            "language": "de",
            "voice_id": None,
            "mode_web": "push_to_talk",
            "mode_telegram": "text_only",
            "mode_discord": "text_only",
            "edit_transcript_before_send": True,
        }

    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", prefs_text_only)
    assert voice_policy.effective_voice_output(user_id=uid, channel="telegram") is False

    def prefs_voice(_uid: uuid.UUID) -> dict:
        d = prefs_text_only(_uid)
        d["mode_telegram"] = "voice_reply"
        return d

    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", prefs_voice)
    assert voice_policy.effective_voice_output(user_id=uid, channel="telegram") is True


def test_effective_voice_output_web_uses_output_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        voice_policy,
        "operator_voice_row",
        lambda: {"voice_enabled": True},
    )
    uid = uuid.uuid4()

    def prefs_off(_uid: uuid.UUID) -> dict:
        return {
            "input_enabled": True,
            "output_enabled": False,
            "language": "de",
            "voice_id": None,
            "mode_web": "push_to_talk",
            "mode_telegram": "text_only",
            "mode_discord": "text_only",
            "edit_transcript_before_send": True,
        }

    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", prefs_off)
    assert voice_policy.effective_voice_output(user_id=uid, channel="web") is False

    def prefs_on(_uid: uuid.UUID) -> dict:
        d = prefs_off(_uid)
        d["output_enabled"] = True
        return d

    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", prefs_on)
    assert voice_policy.effective_voice_output(user_id=uid, channel="web") is True
