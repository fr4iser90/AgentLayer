"""Shared ``create_dashboard`` logic (template gallery + legacy ``kind`` mirror)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.bundle import (
    _fallback_label,
    bundles_by_kind,
    bundles_by_template_id,
)
from apps.backend.dashboard.setup import setup_tool_payload
from apps.backend.dashboard.tool_dashboard_resolve import filter_dashboard_gallery_rows


def default_title_for_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    b = bundles_by_kind().get(k)
    if b is not None and b.label and b.label.strip():
        return b.label.strip()
    return _fallback_label(k)


def default_title_for_template_id(template_id: str) -> str:
    tid = (template_id or "").strip().lower()
    b = bundles_by_template_id().get(tid)
    if b is not None and b.label and b.label.strip():
        return b.label.strip()
    return _fallback_label(b.kind if b else tid)


def validate_create_kind(kind: str) -> str | None:
    """Return an error message, or ``None`` when ``kind`` is allowed (legacy API)."""
    k = (kind or "").strip().lower()
    if not k:
        return "kind is required (e.g. pets, projects, ideas, shopping_list, todo, feeds, friends, photo_album, personal_dashboard, custom)"
    if k == "custom":
        return None
    if k not in bundles_by_kind():
        known = ", ".join(sorted(bundles_by_kind().keys()))
        return f"unknown kind {kind!r} — known kinds: {known}, custom"
    return None


def validate_template_id(template_id: str) -> str | None:
    """Return an error message, or ``None`` when ``template_id`` is allowed."""
    tid = (template_id or "").strip().lower()
    if not tid:
        return "template_id is required (e.g. projects-v1, personal_dashboard-v1) or use kind=custom"
    if tid == "custom":
        return None
    if tid not in bundles_by_template_id():
        known = ", ".join(sorted(bundles_by_template_id().keys()))
        return f"unknown template_id {template_id!r} — known templates: {known}, custom"
    return None


def resolve_create_target(
    *,
    template_id: str | None = None,
    kind: str | None = None,
) -> tuple[str, str | None, str | None]:
    """
    Resolve ``(kind, template_id, error)`` for create flows.
    ``template_id`` wins when both are passed.
    """
    tid_raw = (template_id or "").strip().lower()
    k_raw = (kind or "").strip().lower()

    if tid_raw:
        terr = validate_template_id(tid_raw)
        if terr:
            return "", None, terr
        if tid_raw == "custom":
            return "custom", None, None
        bundle = bundles_by_template_id()[tid_raw]
        return bundle.kind, tid_raw, None

    if k_raw:
        kerr = validate_create_kind(k_raw)
        if kerr:
            return "", None, kerr
        if k_raw == "custom":
            return "custom", None, None
        bundle = bundles_by_kind().get(k_raw)
        mirror = bundle.template_id if bundle else f"{k_raw}-v1"
        return k_raw, mirror, None

    return "", None, "template_id or kind is required (prefer template_id; kind is legacy)"


def parse_only_if_none(arguments: dict[str, Any]) -> bool:
    raw = arguments.get("only_if_none")
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def _rows_for_create_target(
    uid: uuid.UUID,
    tid: int,
    *,
    kind: str,
    template_id: str | None,
) -> list[dict[str, Any]]:
    rows = dashboard_db.dashboard_list(uid, tid)
    return filter_dashboard_gallery_rows(rows, kind=kind, template_id=template_id)


def create_dashboard_payload(
    uid: uuid.UUID,
    tid: int,
    *,
    kind: str,
    template_id: str | None = None,
    default_title: str,
    arguments: dict[str, Any],
    max_title_len: int = 500,
) -> dict[str, Any] | None:
    """
    Create or reuse a dashboard row. Returns payload dict, or ``None`` if caller should error
    (multiple boards exist with only_if_none).
    """
    k = (kind or "").strip().lower()
    tpl = (template_id or "").strip().lower() or None
    only_if_none = parse_only_if_none(arguments)
    existing = _rows_for_create_target(uid, tid, kind=k, template_id=tpl)

    if only_if_none and len(existing) == 1:
        r = existing[0]
        payload: dict[str, Any] = {
            "ok": True,
            "created": False,
            "dashboard_id": str(r.get("id", "")),
            "title": (r.get("title") or "").strip(),
            "kind": k,
            "template_id": r.get("template_id") or tpl,
            "hint": "Single matching dashboard already exists — reused it.",
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

    row = dashboard_db.dashboard_create(uid, tid, kind=k, title=title, template_id=tpl)
    payload = {
        "ok": True,
        "created": True,
        "dashboard_id": str(row.get("id", "")),
        "title": row.get("title") or title,
        "kind": row.get("kind") or k,
        "template_id": row.get("template_id") or tpl,
    }
    extra = setup_tool_payload(k)
    if extra:
        payload.update(extra)
    return payload
