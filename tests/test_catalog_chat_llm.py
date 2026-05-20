"""Catalog-only chat LLM resolution (no OLLAMA_DEFAULT_MODEL fallbacks)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.backend.domain import catalog_chat_llm as mod


def test_finalize_requires_catalog_provider() -> None:
    with (
        patch(
            "apps.backend.domain.catalog_chat_llm.infer_catalog_owned_by",
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
        patch("apps.backend.domain.catalog_chat_llm.get_provider_spec", return_value=spec),
        patch(
            "apps.backend.domain.catalog_chat_llm.resolve_model_for_provider",
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


def test_catalog_llm_body_extras_returns_model_and_provider() -> None:
    with patch.object(mod, "finalize_catalog_chat_llm", return_value=("m1", "ollama")):
        out = mod.catalog_llm_body_extras(model="m1", catalog_owned_by="ollama")
    assert out == {"model": "m1", "agent_model_catalog_owned_by": "ollama"}
