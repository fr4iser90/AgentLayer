"""Realtime voice policy flags."""

from __future__ import annotations

import uuid

import pytest

from apps.backend.domain.voice import voice_policy


def test_effective_voice_realtime_requires_operator_and_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    uid = uuid.uuid4()

    def op_row() -> dict:
        return {
            "voice_enabled": True,
            "voice_realtime_enabled": False,
            "voice_discord_vc_enabled": False,
        }

    monkeypatch.setattr(voice_policy, "operator_voice_row", op_row)
    monkeypatch.setattr(
        voice_policy,
        "user_voice_prefs_get",
        lambda _u: {"input_enabled": True, "mode_web": "hands_free"},
    )
    assert voice_policy.effective_voice_realtime(user_id=uid) is False

    def op_on() -> dict:
        d = op_row()
        d["voice_realtime_enabled"] = True
        return d

    monkeypatch.setattr(voice_policy, "operator_voice_row", op_on)
    assert voice_policy.effective_voice_realtime(user_id=uid) is True


def test_effective_discord_vc_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        voice_policy,
        "operator_voice_row",
        lambda: {"voice_enabled": True, "voice_discord_vc_enabled": True},
    )
    assert voice_policy.effective_discord_vc() is True
