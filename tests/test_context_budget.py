"""Context budget from provider metadata and usage.prompt_tokens."""

from __future__ import annotations

from apps.backend.infrastructure.context_budget import (
    ContextBudget,
    extract_context_length_from_model_item,
    limits_from_context_window,
    resolve_context_budget,
    should_compact_by_usage,
    usage_prompt_tokens,
)


def test_extract_context_length_openai_style() -> None:
    item = {"id": "m1", "context_length": 32768}
    assert extract_context_length_from_model_item(item) == 32768


def test_extract_context_length_ollama_nested() -> None:
    item = {"id": "m1", "model_info": {"general.context_length": 131072}}
    assert extract_context_length_from_model_item(item) == 131072


def test_extract_context_length_llama_cpp_meta_n_ctx() -> None:
    """llama.cpp OpenAI server: window in meta.n_ctx, top-level context_length is null."""
    item = {
        "id": "Qwen3.6-35B-A3B-MTP-UD-Q5_K_XL.gguf",
        "context_length": None,
        "meta": {"n_ctx": 262144, "n_ctx_train": 262144},
    }
    assert extract_context_length_from_model_item(item) == 262144


def test_extract_context_length_llama_cpp_meta_n_ctx_train_only() -> None:
    item = {"id": "m1", "meta": {"n_ctx_train": 131072}}
    assert extract_context_length_from_model_item(item) == 131072


def test_limits_from_context_window_percentages() -> None:
    from apps.backend.core import config as cfg

    cfg.config.CHAT_CONTEXT_SOFT_LIMIT_RATIO = 0.6
    cfg.config.CHAT_CONTEXT_HARD_LIMIT_RATIO = 0.85
    b = limits_from_context_window(100_000, source="provider_catalog")
    assert b.context_window_tokens == 100_000
    assert b.soft_limit_tokens == 60_000
    assert b.hard_limit_tokens == 85_000


def test_should_compact_by_usage_provider_tokens(monkeypatch) -> None:
    from apps.backend.core import config as cfg

    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_SOFT_LIMIT_RATIO", 0.6)
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_HARD_LIMIT_RATIO", 0.85)
    budget = limits_from_context_window(100_000, source="provider_catalog")
    assert should_compact_by_usage(budget, 59_999) == (False, False)
    assert should_compact_by_usage(budget, 60_000) == (True, False)
    assert should_compact_by_usage(budget, 85_000) == (True, True)
    assert should_compact_by_usage(None, 90_000) == (False, False)


def test_usage_prompt_tokens_openai_shape() -> None:
    assert usage_prompt_tokens({"prompt_tokens": 1234, "completion_tokens": 56}) == 1234


def test_resolve_context_budget_operator_override(monkeypatch) -> None:
    from apps.backend.core import config as cfg

    monkeypatch.setattr(
        cfg.config,
        "CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES",
        '{"my-model.gguf": 65536}',
    )
    monkeypatch.setattr(cfg.config, "CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 0)
    b = resolve_context_budget("my-model.gguf")
    assert isinstance(b, ContextBudget)
    assert b.context_window_tokens == 65536
    assert b.source == "operator_override"


def test_lookup_model_context_length_direct_provider_fetch(monkeypatch) -> None:
    from apps.backend.infrastructure import model_catalog_providers as mcp

    spec = mcp.CatalogProviderSpec(
        provider_id="provider_1",
        label="test",
        base_url="https://example/v1",
        api_key="",
        api_header_name="X-API-KEY",
        source="env",
    )

    def fake_get_spec(pid: str):
        return spec if pid == "provider_1" else None

    def fake_fetch(_spec, timeout=15.0):
        return (
            [
                {
                    "id": "Qwen3.6-35B-A3B-MTP-UD-Q5_K_XL.gguf",
                    "owned_by": "provider_1",
                    "context_length": 262144,
                }
            ],
            {"reachable": True},
        )

    monkeypatch.setattr(mcp, "get_provider_spec", fake_get_spec)
    monkeypatch.setattr(mcp, "fetch_models_for_provider", fake_fetch)
    monkeypatch.setattr(mcp, "fetch_full_model_catalog", lambda: ([], {}))

    assert (
        mcp.lookup_model_context_length(
            "Qwen3.6-35B-A3B-MTP-UD-Q5_K_XL.gguf",
            "provider_1",
        )
        == 262144
    )
