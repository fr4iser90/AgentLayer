"""Tests for scheduled coding agent LLM provider selection."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.infrastructure.codebase import coding_schedule_execution as mod


def test_schedule_llm_uses_coding_profile_token() -> None:
    with patch.object(mod, "_pick_schedule_catalog_provider", return_value="llama_cpp"):
        fields, profile = mod._schedule_llm_body_fields({})
    assert profile == "coding"
    assert fields["model"] == "coding"
    assert fields["agent_model_catalog_owned_by"] == "llama_cpp"


def test_schedule_llm_workflow_explicit_provider() -> None:
    fields, _ = mod._schedule_llm_body_fields(
        {
            "model_catalog_owned_by": "provider_1",
            "model": "llama3.2",
        }
    )
    assert fields["agent_model_catalog_owned_by"] == "provider_1"
    assert fields["model"] == "llama3.2"


def test_pick_provider_prefers_first_reachable_in_order() -> None:
    with (
        patch.object(mod, "_provider_configured", return_value=True),
        patch(
            "apps.backend.infrastructure.providers.model_catalog_providers.fetch_full_model_catalog",
            return_value=(
                [],
                {
                    "llama_cpp": {"reachable": True},
                    "provider_1": {"reachable": True},
                },
            ),
        ),
    ):
        assert mod._pick_schedule_catalog_provider() == "provider_1"


def test_pick_provider_uses_provider_1_when_only_provider_1_reachable() -> None:
    with (
        patch.object(mod, "_provider_configured", return_value=True),
        patch(
            "apps.backend.infrastructure.providers.model_catalog_providers.fetch_full_model_catalog",
            return_value=(
                [],
                {
                    "llama_cpp": {"reachable": False},
                    "provider_1": {"reachable": True},
                },
            ),
        ),
    ):
        assert mod._pick_schedule_catalog_provider() == "provider_1"


def test_pick_provider_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_SCHEDULE_LLM_PROVIDER", "provider_1")
    with patch.object(mod, "_provider_configured", return_value=True):
        assert mod._pick_schedule_catalog_provider() == "provider_1"
