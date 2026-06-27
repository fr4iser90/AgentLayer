"""Catalog-only chat LLM resolution (no OLLAMA_DEFAULT_MODEL fallbacks)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.backend.domain.model_routing import catalog_chat as mod


def _normalize(raw: str | None) -> str | None:
    return (raw or "").strip() or None


def test_finalize_requires_catalog_provider() -> None:
    with (
        patch.object(mod, "normalize_model_catalog_owned_by", side_effect=_normalize),
        patch(
            "apps.backend.domain.model_routing.catalog_chat.infer_catalog_owned_by",
            return_value=None,
        ),
        pytest.raises(ValueError, match="No LLM catalog provider"),
    ):
        mod.finalize_catalog_chat_llm(
            model="qwen-test",
            profile_key="agent",
            is_override=True,
            catalog_owned_by=None,
        )


def test_finalize_resolves_profile_via_endpoint() -> None:
    spec = MagicMock()
    spec.model_agent = "agent-model"
    spec.model_default = "default-model"
    with (
        patch.object(mod, "normalize_model_catalog_owned_by", side_effect=_normalize),
        patch("apps.backend.domain.model_routing.catalog_chat.get_provider_spec", return_value=spec),
        patch(
            "apps.backend.domain.model_routing.catalog_chat.resolve_model_for_provider",
            return_value="resolved-agent",
        ),
    ):
        eff, owned = mod.finalize_catalog_chat_llm(
            model="agent",
            profile_key="agent",
            is_override=False,
            catalog_owned_by="llama_cpp",
        )
    assert eff == "resolved-agent"
    assert owned == "llama_cpp"


def test_finalize_vlm_rejects_model_not_exposed_by_provider() -> None:
    spec = MagicMock()
    with (
        patch.object(mod, "normalize_model_catalog_owned_by", side_effect=_normalize),
        patch("apps.backend.domain.model_routing.catalog_chat.get_provider_spec", return_value=spec),
        patch(
            "apps.backend.domain.model_routing.catalog_chat.resolve_model_for_provider",
            return_value="missing-vlm.gguf",
        ),
        patch(
            "apps.backend.domain.model_routing.catalog_chat.fetch_models_for_provider",
            return_value=(
                [{"id": "text-model.gguf"}, {"id": "vision-model.gguf"}],
                {"reachable": True},
            ),
        ),
        pytest.raises(ValueError, match="VLM image analysis is not available"),
    ):
        mod.finalize_catalog_chat_llm(
            model="vlm",
            profile_key="vlm",
            is_override=False,
            catalog_owned_by="provider_1",
        )


def test_catalog_llm_body_extras_returns_model_and_provider() -> None:
    with (
        patch.object(mod, "normalize_model_catalog_owned_by", side_effect=_normalize),
        patch.object(mod, "finalize_catalog_chat_llm", return_value=("m1", "provider_1")),
    ):
        out = mod.catalog_llm_body_extras(model="m1", catalog_owned_by="provider_1")
    assert out == {"model": "m1", "agent_model_catalog_owned_by": "provider_1"}
