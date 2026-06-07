"""Read/delete user_attachments with owner, collection-share, and dashboard access."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db

FILE_REF_PREFIX = "file:"


def parse_file_ref(value: str) -> str | None:
    s = (value or "").strip()
    if s.startswith(FILE_REF_PREFIX):
        fid = s[len(FILE_REF_PREFIX) :].strip()
        return fid or None
    return None


def file_ids_in_value(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, str):
        fid = parse_file_ref(obj)
        if fid:
            out.add(fid)
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= file_ids_in_value(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= file_ids_in_value(v)
    return out


def _row(r: dict[str, Any]) -> dict[str, Any]:
    ca = r.get("created_at")
    return {
        "id": str(r.get("id") or ""),
        "owner_user_id": str(r.get("owner_user_id") or ""),
        "collection_id": str(r["collection_id"]) if r.get("collection_id") else None,
        "storage_relpath": r.get("storage_relpath") or "",
        "content_type": r.get("content_type") or "",
        "size_bytes": int(r.get("size_bytes") or 0),
        "original_name": r.get("original_name") or "",
        "created_at": ca.isoformat() if isinstance(ca, datetime) else str(ca or ""),
    }


def attachment_get_with_access(
    file_id: uuid.UUID, user_id: uuid.UUID, tenant_id: int
) -> dict[str, Any] | None:
    """Owner, collection share grantee, or dashboard member (bound collection) may read."""
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.owner_user_id, a.collection_id, a.storage_relpath,
                       a.content_type, a.size_bytes, a.original_name, a.created_at
                FROM user_attachments a
                WHERE a.id = %s AND a.tenant_id = %s
                  AND (
                    a.owner_user_id = %s
                    OR EXISTS (
                      SELECT 1 FROM share_permissions sp
                      JOIN user_collections uc ON uc.owner_user_id = sp.owner_user_id
                        AND uc.id = a.collection_id
                      WHERE sp.grantee_user_id = %s
                        AND sp.owner_user_id = a.owner_user_id
                        AND sp.resource_type = 'collection'
                        AND sp.is_allowed = TRUE
                        AND sp.revoked_at IS NULL
                        AND lower(sp.resource_identifier) = uc.slug
                    )
                    OR EXISTS (
                      SELECT 1 FROM user_dashboards w
                      WHERE w.id = a.dashboard_id AND w.tenant_id = a.tenant_id
                        AND (
                          w.owner_user_id = %s
                          OR EXISTS (
                            SELECT 1 FROM dashboard_members m
                            WHERE m.dashboard_id = w.id AND m.user_id = %s
                          )
                          OR EXISTS (
                            SELECT 1 FROM dashboard_block_share_grants g
                            WHERE g.dashboard_id = w.id
                              AND g.viewer_user_id = %s
                              AND g.tenant_id = w.tenant_id
                          )
                          OR EXISTS (
                            SELECT 1 FROM share_permissions sp
                            WHERE sp.grantee_user_id = %s
                              AND sp.owner_user_id = w.owner_user_id
                              AND sp.resource_type = 'dashboard'
                              AND sp.is_allowed = TRUE
                              AND sp.revoked_at IS NULL
                              AND lower(sp.resource_identifier) = lower(w.id::text)
                          )
                        )
                    )
                  )
                """,
                (file_id, tenant_id, user_id, user_id, user_id, user_id, user_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _row(dict(row)) if row else None


def attachment_delete_with_access(
    file_id: uuid.UUID, user_id: uuid.UUID, tenant_id: int
) -> str | None:
    """Only the attachment owner may delete."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM user_attachments
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                RETURNING storage_relpath
                """,
                (file_id, tenant_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    return str(row[0])
