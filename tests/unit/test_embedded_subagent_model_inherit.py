"""Embedded sub-agents inherit the parent chat model without bearer override gate."""

from __future__ import annotations

from apps.backend.domain.model_routing.resolution import ModelRoutingSettings, resolve_effective_model


def test_embedded_subagent_inherits_concrete_body_model() -> None:
    model, reason, profile, is_override = resolve_effective_model(
        messages=[{"role": "user", "content": "hi"}],
        body_model="nemotron-3-nano:4b",
        profile_header=None,
        override_header=None,
        bearer_user_role=None,
        embedded_subagent=True,
        settings=ModelRoutingSettings(
            allow_model_override=True,
            override_anonymous=False,
        ),
    )
    assert model == "nemotron-3-nano:4b"
    assert reason == "embedded_subagent:inherit_parent"
    assert profile == "default"
    assert is_override is True


def test_non_embedded_subagent_still_blocks_anonymous_body_override() -> None:
    model, _reason, profile, is_override = resolve_effective_model(
        messages=[{"role": "user", "content": "hi"}],
        body_model="nemotron-3-nano:4b",
        profile_header=None,
        override_header=None,
        bearer_user_role=None,
        embedded_subagent=False,
        settings=ModelRoutingSettings(
            profile_default="",
            allow_model_override=True,
            override_anonymous=False,
        ),
    )
    assert model == ""
    assert profile == "default"
    assert is_override is False
