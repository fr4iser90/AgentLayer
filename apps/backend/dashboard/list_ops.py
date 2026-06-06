"""Generic list row CRUD on dashboard ``data`` (any ``list_path``, any board kind)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.data_compute import finalize_dashboard_data
from apps.backend.dashboard.data_paths import get_path, set_path, top_level_key
from apps.backend.dashboard.layout_tree import data_paths_from_blocks, primary_list_data_path

_MAX_ROWS = 2000
_MAX_BATCH = 80
_MAX_ROW_KEYS = 64


def _new_row_id() -> str:
    return f"r_{uuid.uuid4().hex[:12]}"


def _can_write_dashboard(ws: dict[str, Any]) -> bool:
    role = (ws.get("access_role") or "owner").strip().lower()
    if role == "viewer":
        return False
    if ws.get("access_scope") == "granular":
        return ws.get("granular_can_write") is True
    return role in ("owner", "co_owner", "editor")


def _allowed_list_top_keys(ws: dict[str, Any]) -> set[str] | None:
    """``None`` = full dashboard; else only these top-level data keys are writable."""
    if ws.get("access_scope") != "granular":
        return None
    ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
    blocks = ul.get("blocks") if isinstance(ul.get("blocks"), list) else []
    keys: set[str] = set()
    for dp in data_paths_from_blocks(blocks):
        if dp:
            keys.add(top_level_key(dp))
    return keys


def _assert_list_path_allowed(ws: dict[str, Any], list_path: str) -> str | None:
    allowed = _allowed_list_top_keys(ws)
    if allowed is None:
        return None
    top = top_level_key(list_path)
    if top not in allowed:
        return f"granular share cannot write data.{top!r}"
    return None


def resolve_list_path(
    ws: dict[str, Any],
    list_path: str | None,
    *,
    fallback: str = "items",
) -> str:
    explicit = (list_path or "").strip()
    if explicit:
        return explicit
    ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None
    return primary_list_data_path(ul, fallback=fallback)


def _normalize_row(entry: dict[str, Any], *, id_field: str = "id") -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    out = dict(entry)
    rid = str(out.get(id_field) or "").strip()
    if not rid:
        out[id_field] = _new_row_id()
    return out


def append_list_rows(
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    list_path: str | None = None,
    rows: list[dict[str, Any]],
    list_fallback: str = "items",
    dedupe_field: str | None = None,
) -> dict[str, Any]:
    ws = dashboard_db.dashboard_get(user_id, tenant_id, dashboard_id)
    if ws is None:
        return {"ok": False, "error": "dashboard not found"}
    if not _can_write_dashboard(ws):
        return {"ok": False, "error": "read-only access"}

    dp = resolve_list_path(ws, list_path, fallback=list_fallback)
    allow_err = _assert_list_path_allowed(ws, dp)
    if allow_err:
        return {"ok": False, "error": allow_err}

    data = dict(ws.get("data") or {}) if isinstance(ws.get("data"), dict) else {}
    raw = get_path(data, dp)
    current = list(raw) if isinstance(raw, list) else []

    if len(current) + len(rows) > _MAX_ROWS:
        return {"ok": False, "error": f"at most {_MAX_ROWS} rows per list ({dp!r})"}

    dedupe_key = (dedupe_field or "").strip()
    existing: set[str] = set()
    if dedupe_key:
        for item in current:
            if isinstance(item, dict):
                val = str(item.get(dedupe_key) or "").strip().lower()
                if val:
                    existing.add(val)

    added: list[dict[str, Any]] = []
    skipped: list[str] = []
    for entry in rows[:_MAX_BATCH]:
        norm = _normalize_row(entry)
        if not norm:
            continue
        if dedupe_key:
            val = str(norm.get(dedupe_key) or "").strip().lower()
            if val and val in existing:
                skipped.append(val)
                continue
            if val:
                existing.add(val)
        current.append(norm)
        added.append(norm)

    if not added and skipped:
        return {
            "ok": False,
            "error": f"all rows skipped (duplicate {dedupe_key!r})",
            "skipped_count": len(skipped),
            "skipped": skipped,
        }
    if not added:
        return {"ok": False, "error": "no valid rows (each row must be a non-empty object)"}

    out_data = set_path(data, dp, current)
    layout = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None
    out_data = finalize_dashboard_data(out_data, layout)

    updated = dashboard_db.dashboard_update(user_id, tenant_id, dashboard_id, data=out_data)
    if updated is None:
        return {"ok": False, "error": "could not update dashboard"}

    out: dict[str, Any] = {
        "ok": True,
        "dashboard_id": str(dashboard_id),
        "list_path": dp,
        "added_count": len(added),
        "added": added,
        "total_count": len(current),
    }
    if skipped:
        out["skipped_count"] = len(skipped)
        out["skipped"] = skipped
    return out


def update_list_row(
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    list_path: str | None = None,
    row_id: str,
    patch: dict[str, Any],
    list_fallback: str = "items",
) -> dict[str, Any]:
    ws = dashboard_db.dashboard_get(user_id, tenant_id, dashboard_id)
    if ws is None:
        return {"ok": False, "error": "dashboard not found"}
    if not _can_write_dashboard(ws):
        return {"ok": False, "error": "read-only access"}

    rid = (row_id or "").strip()
    if not rid:
        return {"ok": False, "error": "row_id is required"}
    if not isinstance(patch, dict) or not patch:
        return {"ok": False, "error": "patch must be a non-empty object"}
    if len(patch) > _MAX_ROW_KEYS:
        return {"ok": False, "error": f"patch too large (max {_MAX_ROW_KEYS} keys)"}

    dp = resolve_list_path(ws, list_path, fallback=list_fallback)
    data = dict(ws.get("data") or {}) if isinstance(ws.get("data"), dict) else {}
    raw = get_path(data, dp)
    current = list(raw) if isinstance(raw, list) else []

    idx = next(
        (i for i, r in enumerate(current) if isinstance(r, dict) and str(r.get("id") or "") == rid),
        -1,
    )
    if idx < 0:
        return {"ok": False, "error": f"row not found: {rid}"}

    merged = {**dict(current[idx]), **patch, "id": rid}
    current[idx] = merged
    out_data = set_path(data, dp, current)
    layout = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None
    out_data = finalize_dashboard_data(out_data, layout)

    updated = dashboard_db.dashboard_update(user_id, tenant_id, dashboard_id, data=out_data)
    if updated is None:
        return {"ok": False, "error": "could not update dashboard"}

    return {
        "ok": True,
        "dashboard_id": str(dashboard_id),
        "list_path": dp,
        "row_id": rid,
        "row": merged,
    }


def delete_list_row(
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    list_path: str | None = None,
    row_id: str,
    list_fallback: str = "items",
) -> dict[str, Any]:
    ws = dashboard_db.dashboard_get(user_id, tenant_id, dashboard_id)
    if ws is None:
        return {"ok": False, "error": "dashboard not found"}
    if not _can_write_dashboard(ws):
        return {"ok": False, "error": "read-only access"}

    rid = (row_id or "").strip()
    if not rid:
        return {"ok": False, "error": "row_id is required"}

    dp = resolve_list_path(ws, list_path, fallback=list_fallback)
    allow_err = _assert_list_path_allowed(ws, dp)
    if allow_err:
        return {"ok": False, "error": allow_err}

    data = dict(ws.get("data") or {}) if isinstance(ws.get("data"), dict) else {}
    raw = get_path(data, dp)
    current = list(raw) if isinstance(raw, list) else []

    before = len(current)
    current = [
        r for r in current if not (isinstance(r, dict) and str(r.get("id") or "") == rid)
    ]
    if len(current) == before:
        return {"ok": False, "error": f"row not found: {rid}"}

    out_data = set_path(data, dp, current)
    layout = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None
    out_data = finalize_dashboard_data(out_data, layout)

    updated = dashboard_db.dashboard_update(user_id, tenant_id, dashboard_id, data=out_data)
    if updated is None:
        return {"ok": False, "error": "could not update dashboard"}

    return {
        "ok": True,
        "dashboard_id": str(dashboard_id),
        "list_path": dp,
        "row_id": rid,
        "total_count": len(current),
    }
