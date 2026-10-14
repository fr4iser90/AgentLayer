"""Upsert operator_provider_endpoints by normalized base URL (no duplicate rows)."""
from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings.operator_settings import normalize_external_llm_base_url


def provider_endpoint_dedupe_key(raw: Any) -> str:
    base = str(raw or "").strip().strip("'\"").rstrip("/")
    return (normalize_external_llm_base_url(base) or base).lower()


def normalize_provider_endpoint_base_url(raw: Any) -> str:
    return str(raw or "").strip().strip("'\"").rstrip("/")


def _prefer_row(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """
    Keep the better row when collapsing URL duplicates.

    Prefer: lower sort_order (primary), then URL that still has /v1, then has api key,
    then has model_default, then lower id (stable).
    """
    def score(row: dict[str, Any]) -> tuple:
        sort = int(row.get("sort_order") if row.get("sort_order") is not None else 10_000)
        url = str(row.get("base_url") or "").rstrip("/").lower()
        has_v1 = 1 if url.endswith("/v1") else 0
        has_key = 1 if str(row.get("api_key") or "").strip() else 0
        has_model = 1 if str(row.get("model_default") or "").strip() else 0
        eid = int(row.get("id") or 0)
        # Higher tuple wins. Negate sort/id so lower is better.
        return (has_key, has_model, has_v1, -sort, -eid)

    return a if score(a) >= score(b) else b


def collapse_duplicate_operator_provider_endpoints(kind: str) -> list[int]:
    """
    Delete extra DB rows that share the same normalized base URL within ``kind``.

    Returns deleted endpoint ids. Safe to call on every list/upsert.
    """
    kind_v = (kind or "").strip().lower()
    existing = list(db.operator_provider_endpoints_list_all(kind_v))
    if len(existing) < 2:
        return []

    keep_by_key: dict[str, dict[str, Any]] = {}
    drop_ids: list[int] = []
    for row in existing:
        key = provider_endpoint_dedupe_key(row.get("base_url"))
        if not key:
            continue
        prev = keep_by_key.get(key)
        if prev is None:
            keep_by_key[key] = dict(row)
            continue
        winner = _prefer_row(prev, row)
        loser = row if int(winner.get("id") or 0) == int(prev.get("id") or 0) else prev
        keep_by_key[key] = dict(winner)
        lid = int(loser.get("id") or 0)
        if lid >= 1:
            drop_ids.append(lid)

    if not drop_ids:
        return []

    drop_set = set(drop_ids)
    keep_rows: list[dict[str, Any]] = []
    seen_keep: set[int] = set()
    for winner in keep_by_key.values():
        wid = int(winner.get("id") or 0)
        if wid >= 1 and wid not in seen_keep:
            keep_rows.append(dict(winner))
            seen_keep.add(wid)
    # Keep rows with empty/unormalizable base_url (no dedupe key) unless marked dropped.
    for row in existing:
        eid = int(row.get("id") or 0)
        if eid in drop_set or eid in seen_keep:
            continue
        if not provider_endpoint_dedupe_key(row.get("base_url")):
            keep_rows.append(dict(row))
            seen_keep.add(eid)

    # Full replace for this kind's kept ids — deletes every twin not in keep_rows.
    db.operator_provider_endpoints_sync(
        kind_v,
        keep_rows,
        delete_missing=True,
    )
    return drop_ids


def upsert_operator_provider_endpoint_by_base_url(
    kind: str,
    *,
    label: str,
    base_url: str,
    api_key: str | None = None,
    api_header_name: str | None = "Authorization",
    model_default: str | None = None,
    max_parallel: int = 1,
    options_json: dict[str, Any] | None = None,
    enabled: bool = True,
    preserve_existing_model: bool = False,
) -> dict[str, Any]:
    """
    Insert or update one endpoint for ``kind`` matched by normalized base URL.

    Collapses any existing URL duplicates for that kind. Empty ``api_key`` on
    update keeps the previously stored key (same as sync).

    When ``preserve_existing_model`` is true and a URL match already has
    ``model_default``, the incoming model is ignored (Continue must not replace
    the user's chosen default with a ranked catalog guess).
    """
    kind_v = (kind or "").strip().lower()
    base = normalize_provider_endpoint_base_url(base_url)
    if not base:
        raise ValueError("base_url is required")

    collapse_duplicate_operator_provider_endpoints(kind_v)

    key = provider_endpoint_dedupe_key(base)
    existing = list(db.operator_provider_endpoints_list_all(kind_v))
    combined: list[dict[str, Any]] = [dict(row) for row in existing]

    match_positions = [
        i
        for i, row in enumerate(combined)
        if provider_endpoint_dedupe_key(row.get("base_url")) == key
    ]
    match_pos = match_positions[0] if match_positions else None
    extra_drop = [int(combined[i]["id"]) for i in match_positions[1:] if combined[i].get("id") is not None]

    try:
        mp = max(1, min(64, int(max_parallel)))
    except (TypeError, ValueError):
        mp = 1

    stored_model = None
    stored_base = base
    if match_pos is not None:
        prev = combined[match_pos]
        stored_model = (str(prev.get("model_default") or "").strip() or None)
        stored_base = str(prev.get("base_url") or "").strip() or base

    use_model = (str(model_default).strip() if model_default is not None else None) or None
    if preserve_existing_model and stored_model:
        use_model = stored_model

    payload: dict[str, Any] = {
        "sort_order": len(combined) if match_pos is None else int(combined[match_pos].get("sort_order") or match_pos),
        "enabled": bool(enabled),
        "label": (label or "").strip()[:512] or kind_v,
        # Keep the already-stored URL shape on update (avoid /v1 vs non-/v1 churn).
        "base_url": stored_base if match_pos is not None else base,
        "api_key": "" if api_key is None else str(api_key),
        "api_header_name": (str(api_header_name or "").strip() or "Authorization"),
        "model_default": use_model,
        "max_parallel": mp,
        "options_json": options_json if isinstance(options_json, dict) else {},
    }

    if match_pos is None:
        combined.append(payload)
    else:
        prev = combined[match_pos]
        combined[match_pos] = {
            **prev,
            **payload,
            "id": prev.get("id"),
            "sort_order": prev.get("sort_order", match_pos),
        }
        if extra_drop:
            drop_set = set(extra_drop)
            combined = [row for row in combined if int(row.get("id") or 0) not in drop_set]

    db.operator_provider_endpoints_sync(
        kind_v,
        combined,
        delete_missing=False,
        delete_ids=extra_drop or None,
    )

    refreshed = list(db.operator_provider_endpoints_list_all(kind_v))
    for row in refreshed:
        if provider_endpoint_dedupe_key(row.get("base_url")) == key:
            return dict(row)
    return dict(combined[match_pos if match_pos is not None else -1])
