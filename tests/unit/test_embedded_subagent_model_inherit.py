"""Embedded sub-agents inherit the parent chat model without bearer override gate."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.domain.model_routing import resolve_effective_model


def test_embedded_subagent_inherits_concrete_body_model() -> None:
    with patch("apps.backend.domain.model_routing.config") as cfg:
        cfg.AGENT_ALLOW_MODEL_OVERRIDE = True
        cfg.AGENT_MODEL_OVERRIDE_ANONYMOUS = False
        model, reason, profile, is_override = resolve_effective_model(
            messages=[{"role": "user", "content": "hi"}],
            body_model="nemotron-3-nano:4b",
            profile_header=None,
            override_header=None,
            bearer_user_role=None,
            embedded_subagent=True,
        )
    assert model == "nemotron-3-nano:4b"
    assert reason == "embedded_subagent:inherit_parent"
    assert profile == "default"
    assert is_override is True


def test_non_embedded_subagent_still_blocks_anonymous_body_override() -> None:
    with patch("apps.backend.domain.model_routing.config") as cfg:
        cfg.AGENT_ALLOW_MODEL_OVERRIDE = True
        cfg.AGENT_MODEL_OVERRIDE_ANONYMOUS = False
        cfg.AGENT_MODEL_PROFILE_DEFAULT = ""
        model, _reason, profile, is_override = resolve_effective_model(
            messages=[{"role": "user", "content": "hi"}],
            body_model="nemotron-3-nano:4b",
            profile_header=None,
            override_header=None,
            bearer_user_role=None,
            embedded_subagent=False,
        )
    assert model == ""
    assert profile == "default"
    assert is_override is False
