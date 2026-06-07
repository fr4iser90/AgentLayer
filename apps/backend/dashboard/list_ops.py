"""Generic list row CRUD on dashboard ``data`` (any ``list_path``, any board kind)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.data_paths import top_level_key
from apps.backend.dashboard.layout_tree import data_paths_from_blocks, primary_list_data_path
from apps.backend.domain.collections import service as domain_svc

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

    owner_raw = ws.get("owner_user_id")
    try:
        owner_uid = uuid.UUID(str(owner_raw)) if owner_raw else user_id
    except (ValueError, TypeError):
        owner_uid = user_id
    row_tid = int(ws.get("tenant_id") or tenant_id)

    bindings = domain_svc.resolve_bindings_for_dashboard(ws)
    from apps.backend.domain.collections.bindings import collection_slug_for_path
    from apps.backend.domain.collections import db as col_db

    slug = collection_slug_for_path(bindings, dp)
    existing_vals: set[str] = set()
    dedupe_key = (dedupe_field or "").strip()
    if dedupe_key and slug:
        col = col_db.collection_get(owner_uid, slug)
        if col:
            for item in col_db.items_list(uuid.UUID(str(col["id"])), dp):
                if isinstance(item, dict):
                    v = str(item.get(dedupe_key) or "").strip().lower()
                    if v:
                        existing_vals.add(v)

    norm_rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for entry in rows[:_MAX_BATCH]:
        norm = _normalize_row(entry)
        if not norm:
            continue
        if dedupe_key:
            val = str(norm.get(dedupe_key) or "").strip().lower()
            if val and val in existing_vals:
                skipped.append(val)
                continue
            if val:
                existing_vals.add(val)
        norm_rows.append(norm)
    if not norm_rows and skipped:
        return {
            "ok": False,
            "error": f"all rows skipped (duplicate {dedupe_key!r})",
            "skipped_count": len(skipped),
            "skipped": skipped,
        }
    if not norm_rows:
        return {"ok": False, "error": "no valid rows (each row must be a non-empty object)"}

    result = domain_svc.append_items(
        owner_user_id=owner_uid,
        tenant_id=row_tid,
        bindings=bindings,
        ui_layout=ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None,
        list_path=dp,
        rows=norm_rows,
    )
    if not result.get("ok"):
        return result
    result["dashboard_id"] = str(dashboard_id)
    if skipped:
        result["skipped_count"] = len(skipped)
        result["skipped"] = skipped
    return result


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
    owner_raw = ws.get("owner_user_id")
    try:
        owner_uid = uuid.UUID(str(owner_raw)) if owner_raw else user_id
    except (ValueError, TypeError):
        owner_uid = user_id
    bindings = domain_svc.resolve_bindings_for_dashboard(ws)
    result = domain_svc.update_item(
        owner_user_id=owner_uid,
        bindings=bindings,
        list_path=dp,
        row_id=rid,
        patch=patch,
    )
    if not result.get("ok"):
        return result
    result["dashboard_id"] = str(dashboard_id)
    return result


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

    owner_raw = ws.get("owner_user_id")
    try:
        owner_uid = uuid.UUID(str(owner_raw)) if owner_raw else user_id
    except (ValueError, TypeError):
        owner_uid = user_id
    bindings = domain_svc.resolve_bindings_for_dashboard(ws)
    result = domain_svc.delete_item(
        owner_user_id=owner_uid,
        bindings=bindings,
        list_path=dp,
        row_id=rid,
    )
    if not result.get("ok"):
        return result
    col_slug = result.get("collection_slug")
    total = 0
    if col_slug:
        from apps.backend.domain.collections import db as col_db

        col = col_db.collection_get(owner_uid, str(col_slug))
        if col:
            total = len(col_db.items_list(uuid.UUID(str(col["id"])), dp))
    result["dashboard_id"] = str(dashboard_id)
    result["total_count"] = total
    return result
