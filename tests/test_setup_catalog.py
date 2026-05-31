"""Setup catalog: model classification and preferences."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.domain import setup_catalog as mod
from apps.backend.domain.setup_catalog import SetupPreferencesBody


def test_classify_model_id_embedding() -> None:
    assert mod.classify_model_id("nomic-embed-text") == "embedding"
    assert mod.classify_model_id("bge-m3") == "embedding"


def test_classify_model_id_chat() -> None:
    assert mod.classify_model_id("llama3.2") == "chat"
    assert mod.classify_model_id("qwen2.5:7b") == "chat"


def test_rank_chat_model_ids_prefers_chat_over_embed() -> None:
    ranked = mod.rank_chat_model_ids(["nomic-embed-text", "llama3.2:instruct"])
    assert ranked[0] == "llama3.2:instruct"


def test_build_setup_catalog_splits_models() -> None:
    merged = [
        {"id": "llama3", "owned_by": "provider_1"},
        {"id": "nomic-embed-text", "owned_by": "provider_1"},
    ]
    agentlayer = {
        "provider_1": {"reachable": True, "detail": None},
        "embedding": {"reachable": False, "configured": True},
    }
    spec = MagicMock(
        provider_id="provider_1",
        label="provider_1",
        source="env",
        base_url="http://host:11434",
        api_key=None,
    )
    with (
        patch.object(mod, "fetch_full_model_catalog", return_value=(merged, agentlayer)),
        patch.object(mod, "list_provider_specs", return_value=[spec]),
        patch.object(mod, "pick_reachable_catalog_provider", return_value="provider_1"),
    ):
        out = mod.build_setup_catalog()
    assert out["any_chat_reachable"] is True
    prov = out["providers"][0]
    assert "llama3" in prov["chat_models"]
    assert "nomic-embed-text" in prov["embedding_models"]
    assert out["suggestions"]["model_agent"] == "llama3"


def test_apply_setup_preferences_unreachable_provider() -> None:
    spec = MagicMock(provider_id="x", label="X", base_url="http://x", api_key=None)
    with (
        patch.object(mod, "get_provider_spec", return_value=spec),
        patch.object(mod, "fetch_models_for_provider", return_value=([], {"reachable": False})),
    ):
        with pytest.raises(HTTPException) as exc:
            mod.apply_setup_preferences(
                SetupPreferencesBody(primary_provider_id="x", model_agent="m1")
            )
    assert exc.value.status_code == 400


def test_chat_provider_embedding_base_url_from_spec() -> None:
    spec = MagicMock(base_url="http://host:11434", provider_id="provider_1")
    with patch.object(mod, "get_provider_spec", return_value=spec):
        url = mod.chat_provider_embedding_base_url()
    assert url == "http://host:11434"


def test_enrich_setup_embedding_meta_not_configured() -> None:
    emb = {"configured": False, "reachable": False}
    providers = [
        {
            "provider_id": "provider_1",
            "reachable": True,
            "embedding_models": ["nomic-embed-text"],
        }
    ]
    with patch.object(mod, "chat_provider_embedding_base_url", return_value="http://host:11434"):
        out = mod.enrich_setup_embedding_meta(emb, providers)
    assert out["rag_active"] is False
    assert "status_line" in out or out.get("status_line")
    assert out["chat_embed_opt_in"]["available"] is True
    assert out["chat_embed_opt_in"]["suggested_model"] == "nomic-embed-text"


def test_apply_setup_preferences_syncs_db() -> None:
    spec = MagicMock(
        provider_id="provider_1",
        label="provider_1",
        base_url="http://host:11434",
        api_key="",
    )
    rows = [{"id": "llama3"}, {"id": "nomic-embed-text"}]
    with (
        patch.object(mod, "get_provider_spec", return_value=spec),
        patch.object(mod, "fetch_models_for_provider", return_value=(rows, {"reachable": True})),
        patch.object(mod.db, "external_llm_endpoints_sync") as sync,
        patch.object(mod, "invalidate_operator_settings_cache"),
        patch.object(mod, "invalidate_model_catalog_cache"),
        patch(
            "apps.backend.infrastructure.embedding_client._normalized_embedding_base",
            return_value="",
        ),
        patch.object(mod, "apply_operator_settings_patch"),
    ):
        out = mod.apply_setup_preferences(
            SetupPreferencesBody(
                primary_provider_id="provider_1",
                model_agent="llama3",
                model_coding="llama3",
                model_default="llama3",
            )
        )
    assert out["ok"] is True
    sync.assert_called_once()
    row = sync.call_args[0][0][0]
    assert row["model_agent"] == "llama3"
    assert row["base_url"] == "http://host:11434"
