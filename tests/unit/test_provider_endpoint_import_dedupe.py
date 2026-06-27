from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _EnvRow:
    index: int
    provider_id: str
    label: str
    base_url: str
    api_key: str = "secret"
    api_header_name: str = "X-API-KEY"
    model_default: str | None = "model-a"
    max_parallel: int = 1


def test_generic_embedding_preview_matches_db_without_stripping_visible_v1(monkeypatch) -> None:
    from apps.backend.api.providers.controllers import operator_common

    monkeypatch.setattr(
        operator_common,
        "list_operator_provider_endpoints",
        lambda kind: [
            {
                "id": 37,
                "kind": "embedding",
                "base_url": "https://embed.example",
                "api_key": "secret",
            }
        ],
    )
    monkeypatch.setattr(
        operator_common,
        "_operator_env_rows_for_kind",
        lambda kind: [
            _EnvRow(
                index=1,
                provider_id="embedding_provider_1",
                label="Embedding",
                base_url="https://embed.example/v1",
            )
        ],
    )

    rows = operator_common._operator_env_provider_preview_rows("embedding")

    assert rows[0]["already_in_db"] is True
    assert rows[0]["matched_db_endpoint_id"] == 37
    assert rows[0]["base_url"] == "https://embed.example/v1"


def test_generic_chat_preview_uses_same_dedupe_path(monkeypatch) -> None:
    from apps.backend.api.providers.controllers import operator_common

    monkeypatch.setattr(
        operator_common,
        "list_operator_provider_endpoints",
        lambda kind: [
            {
                "id": 12,
                "kind": "chat",
                "base_url": "https://chat.example",
                "api_key": "secret",
            }
        ],
    )
    monkeypatch.setattr(
        operator_common,
        "_operator_env_rows_for_kind",
        lambda kind: [
            _EnvRow(
                index=1,
                provider_id="provider_1",
                label="Chat",
                base_url="https://chat.example/v1",
                api_header_name="Authorization",
            )
        ],
    )

    rows = operator_common._operator_env_provider_preview_rows("chat")

    assert rows[0]["already_in_db"] is True
    assert rows[0]["matched_db_endpoint_id"] == 12


def test_legacy_single_provider_sync_does_not_delete_when_base_missing(monkeypatch) -> None:
    from apps.backend.infrastructure.settings import operator_settings

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        operator_settings.db,
        "operator_provider_endpoints_sync",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    operator_settings._sync_single_provider_endpoint(
        "embedding",
        label="Embedding",
        base_url="",
        api_key="secret",
        api_header_name="X-API-KEY",
    )

    assert calls == []


def test_legacy_single_provider_sync_is_non_destructive(monkeypatch) -> None:
    from apps.backend.infrastructure.settings import operator_settings

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        operator_settings.db,
        "operator_provider_endpoints_list_all",
        lambda kind: [{"id": 73}] if kind == "embedding" else [],
    )
    monkeypatch.setattr(
        operator_settings.db,
        "operator_provider_endpoints_sync",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    operator_settings._sync_single_provider_endpoint(
        "embedding",
        label="Embedding",
        base_url="https://embed.example/v1",
        api_key="secret",
        api_header_name="X-API-KEY",
        model_default="nomic-embed",
    )

    assert len(calls) == 1
    assert calls[0][0][0] == "embedding"
    assert calls[0][0][1][0]["id"] == 73
    assert calls[0][1]["delete_missing"] is False
