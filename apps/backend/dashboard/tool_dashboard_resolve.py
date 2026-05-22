"""Resolve ``dashboard_id`` for agent tools when the user omits it (single board of that ``kind``)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.dashboard import db as dashboard_db


def parse_dashboard_uuid_arg(raw: str | None) -> uuid.UUID | None:
    if not raw or not str(raw).strip():
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except ValueError:
        return None


def dashboard_rows_for_kind(
    user_id: uuid.UUID, tenant_id: int, kind: str, *, limit: int = 200
) -> list[dict[str, Any]]:
    want = (kind or "").strip().lower()
    rows = dashboard_db.dashboard_list(user_id, tenant_id, limit=limit)
    return [r for r in rows if (r.get("kind") or "").strip().lower() == want]


def resolve_dashboard_id_for_kind(
    user_id: uuid.UUID,
    tenant_id: int,
    *,
    kind: str,
    raw_dashboard_id: Any,
) -> tuple[uuid.UUID | None, str | None]:
    """
    If ``raw_dashboard_id`` is non-empty, it must be a valid UUID.
    If omitted or empty, pick the dashboard when exactly one row matches ``kind``;
    otherwise return an error string (no board, or ambiguous list).
    """
    if raw_dashboard_id is not None and str(raw_dashboard_id).strip():
        wid = parse_dashboard_uuid_arg(str(raw_dashboard_id).strip())
        if wid is None:
            return None, "dashboard_id must be a valid UUID when provided"
        return wid, None
    rows = dashboard_rows_for_kind(user_id, tenant_id, kind)
    label = (kind or "").strip() or "dashboard"
    if not rows:
        return None, f"No {label} dashboard yet — create one in the app first."
    if len(rows) == 1:
        rid = rows[0].get("id")
        try:
            return (rid if isinstance(rid, uuid.UUID) else uuid.UUID(str(rid))), None
        except (ValueError, TypeError):
            return None, "internal error: invalid dashboard id in list"
    opts = [
        {"id": str(r.get("id", "")), "title": (r.get("title") or "").strip()}
        for r in rows[:40]
    ]
    return None, (
        f"Multiple {label} dashboards — pass dashboard_id (UUID). Boards: "
        + json.dumps(opts, ensure_ascii=False)
    )


def resolve_dashboard_id(
    user_id: uuid.UUID,
    tenant_id: int,
    raw_dashboard_id: Any,
    *,
    limit: int = 200,
) -> tuple[uuid.UUID | None, str | None]:
    """
    Resolve ``dashboard_id`` when omitted: use the board only if the user has exactly one.
    """
    if raw_dashboard_id is not None and str(raw_dashboard_id).strip():
        wid = parse_dashboard_uuid_arg(str(raw_dashboard_id).strip())
        if wid is None:
            return None, "dashboard_id must be a valid UUID when provided"
        return wid, None
    rows = dashboard_db.dashboard_list(user_id, tenant_id, limit=limit)
    if not rows:
        return None, "No dashboards yet — create one in the app first."
    if len(rows) == 1:
        rid = rows[0].get("id")
        try:
            return (rid if isinstance(rid, uuid.UUID) else uuid.UUID(str(rid))), None
        except (ValueError, TypeError):
            return None, "internal error: invalid dashboard id in list"
    opts = [
        {"id": str(r.get("id", "")), "kind": (r.get("kind") or "").strip(), "title": (r.get("title") or "").strip()}
        for r in rows[:40]
    ]
    return None, (
        "Multiple dashboards — pass dashboard_id (UUID) or use [Dashboard context]. Boards: "
        + json.dumps(opts, ensure_ascii=False)
    )
