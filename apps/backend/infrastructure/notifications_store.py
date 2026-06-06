"""Persisted in-app notifications per user."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db

_KINDS = frozenset(
    {
        "scheduler_job_done",
        "scheduler_job_failed",
        "dashboard_agent_update",
        "dashboard_layout_proposals",
    }
)
_SEVERITIES = frozenset({"info", "warning", "error", "action_required"})


def _row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    ref = row.get("source_ref")
    if not isinstance(ref, dict):
        ref = {}
    created = row.get("created_at")
    read_at = row.get("read_at")
    return {
        "id": str(row["id"]),
        "kind": row.get("kind") or "",
        "severity": row.get("severity") or "info",
        "title": row.get("title") or "",
        "body": row.get("body") or "",
        "link_path": row.get("link_path"),
        "source_ref": ref,
        "read": read_at is not None,
        "created_at": created.isoformat() if created else None,
        "read_at": read_at.isoformat() if read_at else None,
    }


def insert_notification(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    body: str = "",
    severity: str = "info",
    link_path: str | None = None,
    source_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    k = (kind or "").strip()
    if k not in _KINDS:
        raise ValueError(f"unsupported notification kind: {k!r}")
    sev = (severity or "info").strip().lower()
    if sev not in _SEVERITIES:
        sev = "info"
    ref = dict(source_ref or {})
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_notifications (
                  tenant_id, user_id, kind, severity, title, body, link_path, source_ref
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, kind, severity, title, body, link_path, source_ref, read_at, created_at
                """,
                (
                    tenant_id,
                    user_id,
                    k,
                    sev,
                    (title or "")[:500],
                    (body or "")[:4000],
                    (link_path or "")[:500] or None,
                    Json(ref),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("user_notifications insert returned no row")
    return _row_to_public(dict(row))


def list_notifications(
    *,
    user_id: uuid.UUID,
    limit: int = 50,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 200))
    clause = "AND read_at IS NULL" if unread_only else ""
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT id, kind, severity, title, body, link_path, source_ref, read_at, created_at
                FROM user_notifications
                WHERE user_id = %s {clause}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, lim),
            )
            rows = cur.fetchall()
    return [_row_to_public(dict(r)) for r in rows]


def unread_count(*, user_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int FROM user_notifications
                WHERE user_id = %s AND read_at IS NULL
                """,
                (user_id,),
            )
            row = cur.fetchone()
    return int(row[0]) if row else 0


def unread_dashboard_summary(*, user_id: uuid.UUID) -> dict[str, Any]:
    """Return { dashboards: {id: count}, blocks: {dashboard_id: {block_id: count}} }."""
    dashboards: dict[str, int] = {}
    blocks: dict[str, dict[str, int]] = {}
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT source_ref
                FROM user_notifications
                WHERE user_id = %s AND read_at IS NULL
                  AND source_ref ? 'dashboard_id'
                """,
                (user_id,),
            )
            for row in cur.fetchall():
                ref = row.get("source_ref")
                if not isinstance(ref, dict):
                    continue
                did = str(ref.get("dashboard_id") or "").strip()
                if not did:
                    continue
                dashboards[did] = dashboards.get(did, 0) + 1
                bid = str(ref.get("block_id") or "").strip()
                if bid:
                    per = blocks.setdefault(did, {})
                    per[bid] = per.get(bid, 0) + 1
    return {"dashboards": dashboards, "blocks": blocks}


def mark_read(*, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_notifications
                SET read_at = %s
                WHERE id = %s AND user_id = %s AND read_at IS NULL
                """,
                (now, notification_id, user_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def mark_all_read(*, user_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_notifications
                SET read_at = %s
                WHERE user_id = %s AND read_at IS NULL
                """,
                (now, user_id),
            )
            n = cur.rowcount
        conn.commit()
    return int(n)


def mark_dashboard_seen(
    *,
    user_id: uuid.UUID,
    dashboard_id: str,
    block_ids: list[str] | None = None,
) -> int:
    """Mark unread notifications for a dashboard (optionally specific blocks) as read."""
    now = datetime.now(UTC)
    did = (dashboard_id or "").strip()
    if not did:
        return 0
    bids = [b.strip() for b in (block_ids or []) if b and str(b).strip()]
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            if bids:
                cur.execute(
                    """
                    UPDATE user_notifications
                    SET read_at = %s
                    WHERE user_id = %s AND read_at IS NULL
                      AND source_ref->>'dashboard_id' = %s
                      AND source_ref->>'block_id' = ANY(%s)
                    """,
                    (now, user_id, did, bids),
                )
            else:
                cur.execute(
                    """
                    UPDATE user_notifications
                    SET read_at = %s
                    WHERE user_id = %s AND read_at IS NULL
                      AND source_ref->>'dashboard_id' = %s
                      AND COALESCE(source_ref->>'block_id', '') = ''
                    """,
                    (now, user_id, did),
                )
            n = cur.rowcount
        conn.commit()
    return int(n)
