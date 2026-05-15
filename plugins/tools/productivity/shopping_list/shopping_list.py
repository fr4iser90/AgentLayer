"""Agent tools for ``kind: shopping_list`` dashboards — list, read, items, preferences, price log."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.tool_dashboard_resolve import (
    resolve_dashboard_id_for_kind,
    dashboard_rows_for_kind,
)

__version__ = "1.1.0"
TOOL_ID = "shopping_list"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "shopping"
TOOL_LABEL = "Shopping list"
TOOL_DESCRIPTION = (
    "Read and update shopping list dashboards (kind shopping_list): lists, items, notes, "
    "store/brand preferences (data.preferences), and append-only price snapshots (data.price_log). "
    "dashboard_id is optional when the user has exactly one shopping_list board; if several exist, "
    "call shopping_list_dashboards or pass dashboard_id. Prefer [Dashboard context] when present. "
    "Does not fetch live prices from the internet — stored prefs and documented research only."
)
TOOL_TRIGGERS = (
    "shopping",
    "einkauf",
    "einkaufsliste",
    "shopping list",
    "groceries",
    # Avoid bare "liste" — it matches "To-do-Liste" / task lists (wrong category).
)
TOOL_CAPABILITIES = ("dashboard.shopping.read", "dashboard.shopping.write")

_MAX_ITEMS = 500
_MAX_BATCH = 40
_MAX_NAME_LEN = 400


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (tid, uid)


def _ensure_shopping(ws: dict[str, Any]) -> str | None:
    if (ws.get("kind") or "").strip() != "shopping_list":
        return "dashboard is not a shopping_list kind"
    return None


def _normalize_row(entry: dict[str, Any]) -> dict[str, Any] | None:
    name = (entry.get("name") or "").strip()
    if not name:
        return None
    if len(name) > _MAX_NAME_LEN:
        name = name[:_MAX_NAME_LEN]
    qty_raw = entry.get("qty")
    if qty_raw is None or qty_raw == "":
        qty: float | int = 1
    else:
        try:
            q = float(qty_raw)
            qty = int(q) if q == int(q) else round(q, 3)
        except (TypeError, ValueError):
            qty = 1
    store = (entry.get("store") or "").strip() or "—"
    if len(store) > 120:
        store = store[:120]
    return {
        "id": str(uuid.uuid4()),
        "checked": bool(entry.get("checked", False)),
        "name": name,
        "qty": qty,
        "store": store,
    }


def shopping_list_dashboards(arguments: dict[str, Any]) -> str:
    """List shopping_list dashboards for the current user."""
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — shopping list tools need an authenticated chat user.")
    tid, uid = ident
    rows = dashboard_rows_for_kind(uid, tid, "shopping_list")
    out = [{"id": str(r.get("id", "")), "title": (r.get("title") or "").strip()} for r in rows]
    return json.dumps({"ok": True, "dashboards": out}, ensure_ascii=False)


def shopping_list_read(arguments: dict[str, Any]) -> str:
    """Return items and notes for one shopping list dashboard."""
    ident = _identity()
    if ident is None:
        return _err("No user identity — shopping list tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="shopping_list", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_shopping(ws)
    if bad:
        return _err(bad)

    data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    notes = data.get("notes")
    if not isinstance(notes, str):
        notes = ""
    pref = data.get("preferences")
    if not isinstance(pref, dict):
        pref = {}
    plog = data.get("price_log")
    if not isinstance(plog, list):
        plog = []

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "title": ws.get("title") or "",
            "items": items,
            "notes": notes,
            "preferences": pref,
            "price_log": plog,
        },
        ensure_ascii=False,
    )


def shopping_list_add_items(arguments: dict[str, Any]) -> str:
    """Append items to a shopping_list dashboard."""
    raw_items = arguments.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return _err("items must be a non-empty array of {name, qty?, store?}")

    ident = _identity()
    if ident is None:
        return _err("No user identity — shopping list tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="shopping_list", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_shopping(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    cur = data.get("items")
    if not isinstance(cur, list):
        cur = []
    if len(cur) >= _MAX_ITEMS:
        return _err(f"list already has max {_MAX_ITEMS} items — remove or archive rows in the UI first")

    new_rows: list[dict[str, Any]] = []
    for entry in raw_items[:_MAX_BATCH]:
        if not isinstance(entry, dict):
            continue
        row = _normalize_row(entry)
        if row:
            new_rows.append(row)
    if not new_rows:
        return _err("no valid items — each needs a non-empty name")

    if len(cur) + len(new_rows) > _MAX_ITEMS:
        return _err(
            f"would exceed {_MAX_ITEMS} items — add fewer items or trim the list first"
        )

    merged = list(cur) + new_rows
    data["items"] = merged
    if "notes" not in data:
        data["notes"] = ""

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "added": len(new_rows),
            "items_count": len(merged),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "shopping_list_dashboards": shopping_list_dashboards,
    "shopping_list_read": shopping_list_read,
    "shopping_list_add_items": shopping_list_add_items,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "shopping_list_dashboards",
            "TOOL_DESCRIPTION": (
                "List shopping list dashboards the user can open (kind shopping_list). "
                "Call when which list is unclear and there is no [Dashboard context] dashboard_id, "
                "or the user may mean a list other than the default context."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shopping_list_read",
            "TOOL_DESCRIPTION": (
                "Read the current items and markdown notes for one shopping list dashboard. "
                "Omit dashboard_id when the user has exactly one shopping_list board; else pass UUID or list dashboards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single shopping_list dashboard).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shopping_list_add_items",
            "TOOL_DESCRIPTION": (
                "Add one or more rows to a shopping list (name, optional qty, optional store). "
                "Omit dashboard_id when the user has exactly one shopping_list dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single shopping_list dashboard).",
                    },
                    "items": {
                        "type": "array",
                        "TOOL_DESCRIPTION": "Objects with name (required), optional qty (number), optional store (string)",
                        "items": {"type": "object"},
                    },
                },
                "required": ["items"],
            },
        },
    },
]
