"""Tests for scheduled coding agent LLM provider selection."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.infrastructure import coding_schedule_execution as mod


def test_schedule_llm_uses_coding_profile_token() -> None:
    with patch.object(mod, "_pick_schedule_catalog_provider", return_value="llama_cpp"):
        fields, profile = mod._schedule_llm_body_fields({})
    assert profile == "coding"
    assert fields["model"] == "coding"
    assert fields["agent_model_catalog_owned_by"] == "llama_cpp"


def test_schedule_llm_workflow_explicit_provider() -> None:
    fields, _ = mod._schedule_llm_body_fields(
        {
            "model_catalog_owned_by": "ollama",
            "model": "llama3.2",
        }
    )
    assert fields["agent_model_catalog_owned_by"] == "ollama"
    assert fields["model"] == "llama3.2"


def test_pick_provider_prefers_reachable_llama_cpp() -> None:
    with (
        patch.object(mod, "_provider_configured", return_value=True),
        patch(
            "apps.backend.infrastructure.model_catalog_providers.fetch_full_model_catalog",
            return_value=(
                [],
                {
                    "llama_cpp": {"reachable": True},
                    "ollama": {"reachable": True},
                },
            ),
        ),
    ):
        assert mod._pick_schedule_catalog_provider() == "llama_cpp"


def test_pick_provider_uses_ollama_when_only_ollama_reachable() -> None:
    with (
        patch.object(mod, "_provider_configured", return_value=True),
        patch(
            "apps.backend.infrastructure.model_catalog_providers.fetch_full_model_catalog",
            return_value=(
                [],
                {
                    "llama_cpp": {"reachable": False},
                    "ollama": {"reachable": True},
                },
            ),
        ),
    ):
        assert mod._pick_schedule_catalog_provider() == "ollama"


def test_pick_provider_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_SCHEDULE_LLM_PROVIDER", "ollama")
    with patch.object(mod, "_provider_configured", return_value=True):
        assert mod._pick_schedule_catalog_provider() == "ollama"
