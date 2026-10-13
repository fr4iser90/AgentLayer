"""Attachment list queries for dashboard-scoped files."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.persistence.postgres.collection_rows import attachment_row


def attachment_list_for_dashboard(
    dashboard_id: uuid.UUID,
    tenant_id: int,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 200), 500))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.owner_user_id, a.collection_id, a.dashboard_id,
                       a.storage_relpath, a.content_type, a.size_bytes,
                       a.original_name, a.created_at
                FROM user_attachments a
                WHERE a.dashboard_id = %s AND a.tenant_id = %s
                ORDER BY a.created_at DESC
                LIMIT %s
                """,
                (dashboard_id, tenant_id, lim),
            )
            rows = cur.fetchall() or []
        conn.commit()
    out: list[dict[str, Any]] = []
    for row in rows:
        mapped = attachment_row(dict(row))
        fid = mapped.get("id") or ""
        mapped["dashboard_id"] = str(row.get("dashboard_id") or dashboard_id)
        mapped["file_ref"] = f"file:{fid}" if fid else ""
        mapped["gallery_ref"] = mapped["file_ref"]
        out.append(mapped)
    return out
