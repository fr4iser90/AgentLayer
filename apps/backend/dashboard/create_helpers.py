"""Shared ``create_dashboard`` logic for the generic dashboard tools (any catalog kind)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.bundle import _fallback_label, bundles_by_kind
from apps.backend.dashboard.setup import setup_tool_payload
from apps.backend.dashboard.tool_dashboard_resolve import dashboard_rows_for_kind


def default_title_for_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    b = bundles_by_kind().get(k)
    if b is not None and b.label and b.label.strip():
        return b.label.strip()
    return _fallback_label(k)


def validate_create_kind(kind: str) -> str | None:
    """Return an error message, or ``None`` when ``kind`` is allowed."""
    k = (kind or "").strip().lower()
    if not k:
        return "kind is required (e.g. pets, projects, ideas, shopping_list, todo, feeds, friends, photo_album, personal_dashboard, custom)"
    if k == "custom":
        return None
    if k not in bundles_by_kind():
        known = ", ".join(sorted(bundles_by_kind().keys()))
        return f"unknown kind {kind!r} — known kinds: {known}, custom"
    return None


def parse_only_if_none(arguments: dict[str, Any]) -> bool:
    raw = arguments.get("only_if_none")
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def create_dashboard_payload(
    uid: uuid.UUID,
    tid: int,
    *,
    kind: str,
    default_title: str,
    arguments: dict[str, Any],
    max_title_len: int = 500,
) -> dict[str, Any] | None:
    """
    Create or reuse a dashboard row. Returns payload dict, or ``None`` if caller should error
    (multiple boards exist with only_if_none).
    """
    k = (kind or "").strip().lower()
    only_if_none = parse_only_if_none(arguments)
    existing = dashboard_rows_for_kind(uid, tid, k)

    if only_if_none and len(existing) == 1:
        r = existing[0]
        payload: dict[str, Any] = {
            "ok": True,
            "created": False,
            "dashboard_id": str(r.get("id", "")),
            "title": (r.get("title") or "").strip(),
            "kind": k,
            "hint": f"Single {k} dashboard already exists — reused it.",
        }
        extra = setup_tool_payload(k)
        if extra:
            payload.update(extra)
        return payload

    if only_if_none and len(existing) > 1:
        return None

    title = str(arguments.get("title") or default_title).strip()
    if len(title) > max_title_len:
        title = title[:max_title_len]
    if not title:
        title = default_title

    row = dashboard_db.dashboard_create(uid, tid, kind=k, title=title)
    payload = {
        "ok": True,
        "created": True,
        "dashboard_id": str(row.get("id", "")),
        "title": row.get("title") or title,
        "kind": row.get("kind") or k,
    }
    extra = setup_tool_payload(k)
    if extra:
        payload.update(extra)
    return payload
