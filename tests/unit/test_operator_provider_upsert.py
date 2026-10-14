from __future__ import annotations


def test_upsert_inserts_when_no_match(monkeypatch) -> None:
    from apps.backend.infrastructure.providers import operator_provider_upsert as mod

    calls: list[tuple[object, ...]] = []
    state = {"phase": "scan"}

    def list_all(kind: str):
        if state["phase"] == "scan":
            return []
        return [
            {
                "id": 9,
                "kind": kind,
                "label": "Chat A",
                "base_url": "https://llm.example/v1",
                "model_default": "m1",
            }
        ]

    def sync(kind, rows, delete_missing=True, delete_ids=None):
        calls.append((kind, rows, delete_missing))
        state["phase"] = "after"

    monkeypatch.setattr(mod.db, "operator_provider_endpoints_list_all", list_all)
    monkeypatch.setattr(mod.db, "operator_provider_endpoints_sync", sync)

    row = mod.upsert_operator_provider_endpoint_by_base_url(
        "chat",
        label="Chat A",
        base_url="https://llm.example/v1",
        api_key="secret",
        model_default="m1",
    )

    assert len(calls) == 1
    assert calls[0][0] == "chat"
    assert calls[0][2] is False
    assert "id" not in calls[0][1][0]
    assert row["id"] == 9


def test_upsert_updates_same_url_instead_of_insert(monkeypatch) -> None:
    from apps.backend.infrastructure.providers import operator_provider_upsert as mod

    store = [
        {
            "id": 3,
            "kind": "chat",
            "label": "Old",
            "base_url": "https://llm.example",
            "api_key": "old-key",
            "model_default": "old",
            "sort_order": 0,
        }
    ]
    calls: list[tuple[object, ...]] = []

    def list_all(kind: str):
        return [dict(r) for r in store]

    def sync(kind, rows, delete_missing=True, delete_ids=None):
        calls.append((kind, rows, delete_missing))
        store.clear()
        store.extend(dict(r) for r in rows)

    monkeypatch.setattr(mod.db, "operator_provider_endpoints_list_all", list_all)
    monkeypatch.setattr(mod.db, "operator_provider_endpoints_sync", sync)

    row = mod.upsert_operator_provider_endpoint_by_base_url(
        "chat",
        label="New Name",
        base_url="https://llm.example/v1",
        api_key="new-key",
        model_default="new-model",
    )

    assert len(calls) == 1
    assert len(calls[0][1]) == 1
    assert calls[0][1][0]["id"] == 3
    assert calls[0][1][0]["label"] == "New Name"
    assert calls[0][1][0]["model_default"] == "new-model"
    assert row["id"] == 3


def test_dedupe_key_treats_v1_suffix_as_same() -> None:
    from apps.backend.infrastructure.providers.operator_provider_upsert import (
        provider_endpoint_dedupe_key,
    )

    assert provider_endpoint_dedupe_key("https://x.example/v1") == provider_endpoint_dedupe_key(
        "https://x.example"
    )


def test_collapse_removes_host_vs_v1_duplicates(monkeypatch) -> None:
    from apps.backend.infrastructure.providers import operator_provider_upsert as mod

    store = [
        {
            "id": 1,
            "kind": "chat",
            "label": "ai.fr4iser.com",
            "base_url": "https://ai.fr4iser.com/v1",
            "api_key": "a",
            "model_default": "chat",
            "sort_order": 0,
        },
        {
            "id": 2,
            "kind": "chat",
            "label": "ai.fr4iser.com",
            "base_url": "https://ai.fr4iser.com",
            "api_key": "b",
            "model_default": "Qwen3.8 Flash Next",
            "sort_order": 1,
        },
    ]
    sync_calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(mod.db, "operator_provider_endpoints_list_all", lambda kind: [dict(r) for r in store])
    monkeypatch.setattr(
        mod.db,
        "operator_provider_endpoints_sync",
        lambda kind, rows, delete_missing=True, delete_ids=None: sync_calls.append(
            (kind, rows, delete_missing, list(delete_ids or []))
        ),
    )

    dropped = mod.collapse_duplicate_operator_provider_endpoints("chat")

    # Keep primary (/v1, sort_order 0); drop the Continue-created twin.
    assert set(dropped) == {2}
    assert len(sync_calls) == 1
    assert sync_calls[0][2] is True  # delete_missing full-replace of kept rows
    assert len(sync_calls[0][1]) == 1
    assert sync_calls[0][1][0]["id"] == 1
    assert sync_calls[0][1][0]["model_default"] == "chat"
