from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.db.db import pool



def _ilike_contains(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _require_user_uuid() -> tuple[int, uuid.UUID]:
    tenant_id, user_id = get_identity()
    if user_id is None:
        raise ValueError("no user identity in this context (chat/tool requests need user/tenant headers)")
    return tenant_id, user_id

def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def memory_fact_upsert(
    *,
    key: str,
    value_json: Any,
    dashboard_id: uuid.UUID | None = None,
    confidence: float | None = None,
    source: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Upsert one structured memory fact for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    k = (key or "").strip()
    if not k:
        raise ValueError("key is required")
    conf = float(confidence) if confidence is not None else 1.0
    conf = max(0.0, min(conf, 1.0))
    src = (source or "user").strip() or "user"
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if dashboard_id is None:
                cur.execute(
                    """
                    INSERT INTO user_memory_facts
                      (tenant_id, user_id, dashboard_id, key, value_json, confidence, source, expires_at, deleted_at)
                    VALUES (%s, %s, NULL, %s, %s::jsonb, %s, %s, %s, NULL)
                    ON CONFLICT (tenant_id, user_id, key)
                      WHERE dashboard_id IS NULL AND deleted_at IS NULL
                    DO UPDATE SET
                      value_json = EXCLUDED.value_json,
                      confidence = EXCLUDED.confidence,
                      source = EXCLUDED.source,
                      expires_at = EXCLUDED.expires_at,
                      updated_at = now(),
                      deleted_at = NULL
                    RETURNING id, key, value_json, confidence, source, dashboard_id, expires_at, updated_at
                    """,
                    (tenant_id, user_id, k, Json(value_json), conf, src, expires_at),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO user_memory_facts
                      (tenant_id, user_id, dashboard_id, key, value_json, confidence, source, expires_at, deleted_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, NULL)
                    ON CONFLICT (tenant_id, user_id, dashboard_id, key)
                      WHERE dashboard_id IS NOT NULL AND deleted_at IS NULL
                    DO UPDATE SET
                      value_json = EXCLUDED.value_json,
                      confidence = EXCLUDED.confidence,
                      source = EXCLUDED.source,
                      expires_at = EXCLUDED.expires_at,
                      updated_at = now(),
                      deleted_at = NULL
                    RETURNING id, key, value_json, confidence, source, dashboard_id, expires_at, updated_at
                    """,
                    (tenant_id, user_id, dashboard_id, k, Json(value_json), conf, src, expires_at),
                )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("upsert failed")
    return {
        "id": row["id"],
        "key": row["key"],
        "value_json": row["value_json"],
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else 1.0,
        "source": row["source"],
        "dashboard_id": str(row["dashboard_id"]) if row.get("dashboard_id") else None,
        "expires_at": row["expires_at"].isoformat() if row.get("expires_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def memory_fact_list(
    *,
    dashboard_id: uuid.UUID | None = None,
    prefix: str | None = None,
    limit: int = 50,
    include_expired: bool = False,
) -> list[dict[str, Any]]:
    """List active facts for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 50), 200))
    pre = (prefix or "").strip()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, key, value_json, confidence, source, dashboard_id, expires_at, updated_at
                FROM user_memory_facts
                WHERE tenant_id = %s
                  AND user_id = %s
                  AND (%s::uuid IS NULL AND dashboard_id IS NULL OR dashboard_id = %s::uuid)
                  AND deleted_at IS NULL
                  AND (%s OR expires_at IS NULL OR expires_at > now())
                  AND (%s = '' OR key ILIKE %s ESCAPE '\\')
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (
                    tenant_id,
                    user_id,
                    dashboard_id,
                    dashboard_id,
                    bool(include_expired),
                    pre,
                    _ilike_contains(pre) if pre else "",
                    limit,
                ),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "key": r["key"],
                "value_json": r["value_json"],
                "confidence": float(r.get("confidence") or 1.0),
                "source": r.get("source") or "",
                "dashboard_id": str(r["dashboard_id"]) if r.get("dashboard_id") else None,
                "expires_at": r["expires_at"].isoformat() if r.get("expires_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            }
        )
    return out


def memory_fact_delete(*, key: str, dashboard_id: uuid.UUID | None = None) -> bool:
    """Soft-delete one fact by key for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    k = (key or "").strip()
    if not k:
        raise ValueError("key is required")
    with pool().connection() as conn:
        with conn.cursor() as cur:
            if dashboard_id is None:
                cur.execute(
                    """
                    UPDATE user_memory_facts
                    SET deleted_at = now(), updated_at = now()
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND dashboard_id IS NULL
                      AND key = %s
                      AND deleted_at IS NULL
                    """,
                    (tenant_id, user_id, k),
                )
            else:
                cur.execute(
                    """
                    UPDATE user_memory_facts
                    SET deleted_at = now(), updated_at = now()
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND dashboard_id = %s
                      AND key = %s
                      AND deleted_at IS NULL
                    """,
                    (tenant_id, user_id, dashboard_id, k),
                )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def memory_note_insert(
    *,
    text: str,
    embedding: list[float],
    tags: list[str] | None = None,
    source: str | None = None,
    dashboard_id: uuid.UUID | None = None,
) -> int:
    """Insert one semantic memory note for the current identity (embedding provided by caller)."""
    tenant_id, user_id = _require_user_uuid()
    t = (text or "").strip()
    if not t:
        raise ValueError("text is required")
    tg = [str(x).strip() for x in (tags or []) if str(x).strip()]
    src = (source or "user").strip() or "user"
    ev = _vector_literal(embedding)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_memory_notes
                  (tenant_id, user_id, dashboard_id, text, tags, source, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                RETURNING id
                """,
                (tenant_id, user_id, dashboard_id, t, tg, src, ev),
            )
            nid = int(cur.fetchone()[0])
        conn.commit()
    return nid


def memory_note_soft_delete(note_id: int) -> bool:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_memory_notes
                SET deleted_at = now(), updated_at = now()
                WHERE id = %s AND tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (int(note_id), tenant_id, user_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def memory_note_vector_search(
    *,
    query_embedding: list[float],
    dashboard_id: uuid.UUID | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Vector search over semantic memory notes for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 10), 50))
    qv = _vector_literal(query_embedding)
    tg = [str(x).strip() for x in (tags or []) if str(x).strip()]
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if tg:
                cur.execute(
                    """
                    SELECT
                      id,
                      left(text, 4000) AS text,
                      tags,
                      source,
                      dashboard_id,
                      updated_at,
                      (embedding <=> %s::vector) AS distance
                    FROM user_memory_notes
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND deleted_at IS NULL
                      AND (%s::uuid IS NULL AND dashboard_id IS NULL OR dashboard_id = %s::uuid)
                      AND tags && %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dashboard_id, dashboard_id, tg, qv, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT
                      id,
                      left(text, 4000) AS text,
                      tags,
                      source,
                      dashboard_id,
                      updated_at,
                      (embedding <=> %s::vector) AS distance
                    FROM user_memory_notes
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND deleted_at IS NULL
                      AND (%s::uuid IS NULL AND dashboard_id IS NULL OR dashboard_id = %s::uuid)
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dashboard_id, dashboard_id, qv, limit),
                )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "text": r["text"],
                "tags": r.get("tags") or [],
                "source": r.get("source") or "",
                "dashboard_id": str(r["dashboard_id"]) if r.get("dashboard_id") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
                "distance": float(r.get("distance")) if r.get("distance") is not None else None,
            }
        )
    return out


from apps.backend.infrastructure.db.memory_graph_persistence import (
    memory_graph_activation_log_insert,
    memory_graph_activation_log_list,
    memory_graph_activate,
    memory_graph_edge_insert,
    memory_graph_list_nodes,
    memory_graph_node_insert,
    memory_graph_node_soft_delete,
    memory_graph_stats,
)
