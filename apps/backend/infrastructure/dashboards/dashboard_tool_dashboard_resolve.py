"""Resolve ``dashboard_id`` for agent tools (no ``kind`` gate on behavior)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.infrastructure.dashboards import dashboard_db


def parse_dashboard_uuid_arg(raw: str | None) -> uuid.UUID | None:
    if not raw or not str(raw).strip():
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except ValueError:
        return None


def filter_dashboard_gallery_rows(
    rows: list[dict[str, Any]],
    *,
    kind: str | None = None,
    template_id: str | None = None,
) -> list[dict[str, Any]]:
    """Filter listed boards by ``template_id`` (preferred) or legacy ``kind`` mirror."""
    k = (kind or "").strip().lower()
    tid = (template_id or "").strip().lower()
    out: list[dict[str, Any]] = []
    for r in rows:
        rk = (r.get("kind") or "").strip().lower()
        rt = (r.get("template_id") or "").strip().lower()
        if tid and rt == tid:
            out.append(r)
        elif tid and not rt and k and rk == k:
            out.append(r)
        elif not tid and k and rk == k:
            out.append(r)
    return out


def dashboard_rows_for_gallery(
    user_id: uuid.UUID,
    tenant_id: int,
    *,
    kind: str | None = None,
    template_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    rows = dashboard_db.dashboard_list(user_id, tenant_id, limit=limit)
    return filter_dashboard_gallery_rows(rows, kind=kind, template_id=template_id)


def resolve_dashboard_id(
    user_id: uuid.UUID,
    tenant_id: int,
    raw_dashboard_id: Any,
    *,
    limit: int = 200,
) -> tuple[uuid.UUID | None, str | None]:
    """
    Resolve ``dashboard_id`` when omitted: use the board only if the user has exactly one.
    Prefer explicit ``dashboard_id`` or [Dashboard context] on multi-board users.
    """
    if raw_dashboard_id is not None and str(raw_dashboard_id).strip():
        wid = parse_dashboard_uuid_arg(str(raw_dashboard_id).strip())
        if wid is None:
            return None, "dashboard_id must be a valid UUID when provided"
        return wid, None
    rows = dashboard_db.dashboard_list(user_id, tenant_id, limit=limit)
    if not rows:
        return None, (
            "No dashboards yet — call dashboard.create_dashboard with template_id "
            "(e.g. pets-v1, custom) or create one in the app first."
        )
    if len(rows) == 1:
        rid = rows[0].get("id")
        try:
            return (rid if isinstance(rid, uuid.UUID) else uuid.UUID(str(rid))), None
        except (ValueError, TypeError):
            return None, "internal error: invalid dashboard id in list"
    opts = [
        {
            "id": str(r.get("id", "")),
            "kind": (r.get("kind") or "").strip(),
            "template_id": r.get("template_id"),
            "title": (r.get("title") or "").strip(),
        }
        for r in rows[:40]
    ]
    return None, (
        "Multiple dashboards — pass dashboard_id (UUID) or use [Dashboard context]. Boards: "
        + json.dumps(opts, ensure_ascii=False)
    )
