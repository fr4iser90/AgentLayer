from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.db.db import pool


def _require_user_uuid() -> tuple[int, uuid.UUID]:
    tenant_id, user_id = get_identity()
    if user_id is None:
        raise ValueError("no user identity in this context (chat/tool requests need user/tenant headers)")
    return tenant_id, user_id


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"

def memory_graph_node_insert(
    *,
    dashboard_id: uuid.UUID | None,
    kind: str,
    label: str,
    summary: str,
    payload: dict[str, Any] | None,
    importance: float,
    embedding: list[float] | None = None,
    confidence: float | None = None,
    source: str | None = None,
    last_verified: datetime | None = None,
    subject_key: str | None = None,
    stability: str | None = None,
    priority: float | None = None,
) -> dict[str, Any]:
    """Insert one graph memory node for the current identity. Optional ``embedding`` (768-dim pgvector)."""
    tenant_id, user_id = _require_user_uuid()
    k = (kind or "event").strip() or "event"
    lab = (label or "").strip()
    if not lab:
        raise ValueError("label is required")
    summ = (summary or "").strip()
    pl = payload if isinstance(payload, dict) else {}
    imp = float(importance) if importance is not None else 1.0
    imp = max(0.0, min(imp, 10.0))
    conf = max(0.0, min(1.0, float(confidence) if confidence is not None else 1.0))
    src = (source or "user").strip() or "user"
    sk = (subject_key or "").strip() or None
    stab = (stability or "normal").strip().lower() or "normal"
    if stab not in ("volatile", "normal", "stable"):
        stab = "normal"
    prio = float(priority) if priority is not None else 0.0
    prio = max(-50.0, min(50.0, prio))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if embedding:
                ev = _vector_literal(embedding)
                cur.execute(
                    """
                    INSERT INTO user_memory_graph_nodes (
                      tenant_id, user_id, dashboard_id, kind, label, summary, payload, importance,
                      confidence, source, last_verified, subject_key, stability, priority,
                      embedding, deleted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s::vector, NULL)
                    RETURNING id, kind, label, summary, payload, importance, confidence, source,
                      last_verified, subject_key, stability, priority, dashboard_id, created_at, updated_at
                    """,
                    (
                        tenant_id,
                        user_id,
                        dashboard_id,
                        k,
                        lab,
                        summ,
                        Json(pl),
                        imp,
                        conf,
                        src,
                        last_verified,
                        sk,
                        stab,
                        prio,
                        ev,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO user_memory_graph_nodes (
                      tenant_id, user_id, dashboard_id, kind, label, summary, payload, importance,
                      confidence, source, last_verified, subject_key, stability, priority, deleted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, NULL)
                    RETURNING id, kind, label, summary, payload, importance, confidence, source,
                      last_verified, subject_key, stability, priority, dashboard_id, created_at, updated_at
                    """,
                    (
                        tenant_id,
                        user_id,
                        dashboard_id,
                        k,
                        lab,
                        summ,
                        Json(pl),
                        imp,
                        conf,
                        src,
                        last_verified,
                        sk,
                        stab,
                        prio,
                    ),
                )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("insert failed")
    return _memory_graph_node_row(row)


def memory_graph_edge_insert(
    *,
    src_node_id: int,
    dst_node_id: int,
    rel_type: str,
    weight: float,
) -> dict[str, Any]:
    """Insert an edge if both endpoints belong to the current user."""
    tenant_id, user_id = _require_user_uuid()
    if int(src_node_id) == int(dst_node_id):
        raise ValueError("src and dst must differ")
    rt = (rel_type or "related").strip() or "related"
    w = float(weight) if weight is not None else 1.0
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS c FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND id IN (%s, %s)
                """,
                (tenant_id, user_id, int(src_node_id), int(dst_node_id)),
            )
            cnt = cur.fetchone()
            if not cnt or int(cnt["c"]) != 2:
                raise ValueError("both nodes must exist and belong to this user")
            cur.execute(
                """
                INSERT INTO user_memory_graph_edges (
                  tenant_id, user_id, src_node_id, dst_node_id, rel_type, weight
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (src_node_id, dst_node_id, rel_type) DO UPDATE SET
                  weight = EXCLUDED.weight
                RETURNING id, src_node_id, dst_node_id, rel_type, weight, created_at
                """,
                (tenant_id, user_id, int(src_node_id), int(dst_node_id), rt, w),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("edge insert failed")
    return {
        "id": int(row["id"]),
        "src_node_id": int(row["src_node_id"]),
        "dst_node_id": int(row["dst_node_id"]),
        "rel_type": row["rel_type"],
        "weight": float(row["weight"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
    }


def memory_graph_node_soft_delete(*, node_id: int) -> bool:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_memory_graph_nodes
                SET deleted_at = now(), updated_at = now()
                WHERE id = %s AND tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (int(node_id), tenant_id, user_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def memory_graph_list_nodes(
    *,
    dashboard_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 100), 500))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, kind, label, left(summary, 4000) AS summary, payload, importance,
                  confidence, source, last_verified, subject_key, stability, priority,
                  dashboard_id, created_at, updated_at
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND (dashboard_id IS NULL OR (%s::uuid IS NOT NULL AND dashboard_id = %s::uuid))
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (tenant_id, user_id, dashboard_id, dashboard_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_memory_graph_node_row(r) for r in rows]


def _memory_graph_node_row(row: Any) -> dict[str, Any]:
    lv = row.get("last_verified")
    cr = row.get("created_at")
    return {
        "id": int(row["id"]),
        "kind": row.get("kind") or "event",
        "label": row.get("label") or "",
        "summary": row.get("summary") or "",
        "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
        "importance": float(row.get("importance") or 1.0),
        "confidence": float(row.get("confidence") if row.get("confidence") is not None else 1.0),
        "source": str(row.get("source") or "user"),
        "last_verified": lv.isoformat() if lv else None,
        "subject_key": (str(row["subject_key"]).strip() if row.get("subject_key") is not None else None),
        "stability": str(row.get("stability") or "normal"),
        "priority": float(row.get("priority") if row.get("priority") is not None else 0.0),
        "dashboard_id": str(row["dashboard_id"]) if row.get("dashboard_id") else None,
        "created_at": cr.isoformat() if cr else "",
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
    }


_GRAPH_NODE_SELECT = """
  id, kind, label, left(summary, 4000) AS summary, payload, importance,
  confidence, source, last_verified, subject_key, stability, priority,
  dashboard_id, created_at, updated_at
"""


def memory_graph_activate(
    *,
    dashboard_id: uuid.UUID | None,
    tokens: list[str],
    query_embedding: list[float] | None = None,
    vec_seed_limit: int = 8,
    keyword_seed_limit: int = 6,
    max_nodes: int = 14,
    max_hops: int = 2,
) -> list[dict[str, Any]]:
    """Hybrid activation: vector + keyword seeds, then multi-hop BFS along edges (cap ``max_nodes``)."""
    tenant_id, user_id = _require_user_uuid()
    clean: list[str] = []
    for t in tokens:
        s = str(t).strip().lower()[:80]
        if len(s) >= 2:
            clean.append(s)
    clean = clean[:24]

    qemb = query_embedding if query_embedding and len(query_embedding) >= 8 else None
    if not clean and not qemb:
        return []

    vec_seed_limit = max(1, min(int(vec_seed_limit), 50))
    keyword_seed_limit = max(1, min(int(keyword_seed_limit), 50))
    max_nodes = max(1, min(int(max_nodes), 50))
    max_hops = max(0, min(int(max_hops), 4))

    vec_rows: list[Any] = []
    seed_rows: list[Any] = []

    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if qemb:
                qv = _vector_literal(qemb)
                cur.execute(
                    f"""
                    SELECT {_GRAPH_NODE_SELECT.strip()},
                      (embedding <=> %s::vector) AS distance
                    FROM user_memory_graph_nodes
                    WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                      AND (dashboard_id IS NULL OR (%s::uuid IS NOT NULL AND dashboard_id = %s::uuid))
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dashboard_id, dashboard_id, qv, vec_seed_limit),
                )
                vec_rows = cur.fetchall()

            if clean:
                or_parts: list[str] = []
                args: list[Any] = [tenant_id, user_id, dashboard_id, dashboard_id]
                for tok in clean:
                    pat = f"%{tok}%"
                    or_parts.append("(label ILIKE %s OR summary ILIKE %s)")
                    args.extend([pat, pat])
                or_sql = " OR ".join(or_parts)
                cur.execute(
                    f"""
                    SELECT {_GRAPH_NODE_SELECT.strip()}
                    FROM user_memory_graph_nodes
                    WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                      AND (dashboard_id IS NULL OR (%s::uuid IS NOT NULL AND dashboard_id = %s::uuid))
                      AND ({or_sql})
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (*args, keyword_seed_limit),
                )
                seed_rows = cur.fetchall()

        ordered_ids: list[int] = []
        for r in vec_rows:
            nid = int(r["id"])
            if nid not in ordered_ids:
                ordered_ids.append(nid)
        for r in seed_rows:
            nid = int(r["id"])
            if nid not in ordered_ids:
                ordered_ids.append(nid)

        seen: set[int] = set(ordered_ids)
        frontier = list(ordered_ids)
        for _hop in range(max_hops):
            if not frontier or len(seen) >= max_nodes:
                break
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT src_node_id, dst_node_id
                    FROM user_memory_graph_edges
                    WHERE tenant_id = %s AND user_id = %s
                      AND (src_node_id = ANY(%s::bigint[]) OR dst_node_id = ANY(%s::bigint[]))
                    """,
                    (tenant_id, user_id, frontier, frontier),
                )
                nxt: list[int] = []
                for row_e in cur.fetchall():
                    a, b = int(row_e[0]), int(row_e[1])
                    for u, v in ((a, b), (b, a)):
                        if u in frontier and v not in seen:
                            seen.add(v)
                            ordered_ids.append(v)
                            nxt.append(v)
                            if len(seen) >= max_nodes:
                                break
                    if len(seen) >= max_nodes:
                        break
            frontier = nxt

        ordered_ids = ordered_ids[:max_nodes]
        if not ordered_ids:
            conn.commit()
            return []

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {_GRAPH_NODE_SELECT.strip()}
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND id = ANY(%s::bigint[])
                """,
                (tenant_id, user_id, ordered_ids),
            )
            by_id = {int(r["id"]): r for r in cur.fetchall()}
        conn.commit()

    rank = {nid: i for i, nid in enumerate(ordered_ids)}
    out: list[dict[str, Any]] = []
    for nid in sorted(by_id.keys(), key=lambda x: rank.get(x, 999)):
        out.append(_memory_graph_node_row(by_id[nid]))
    return out


def memory_graph_stats() -> dict[str, Any]:
    """Counts for the current user (diagnostics / Admin)."""
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  count(*) FILTER (WHERE deleted_at IS NULL)::bigint AS nodes_active,
                  count(*) FILTER (WHERE deleted_at IS NULL AND embedding IS NULL)::bigint AS nodes_no_embedding,
                  count(*) FILTER (WHERE deleted_at IS NULL AND subject_key IS NOT NULL)::bigint AS nodes_with_subject,
                  count(*) FILTER (WHERE deleted_at IS NULL AND kind = 'goal')::bigint AS nodes_goal
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s
                """,
                (tenant_id, user_id),
            )
            row = cur.fetchone()
            cur.execute(
                """
                SELECT COALESCE(subject_key, ''), count(*)::bigint AS c
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND subject_key IS NOT NULL
                GROUP BY subject_key
                HAVING count(*) > 1
                """,
                (tenant_id, user_id),
            )
            conf_groups = cur.fetchall()
        conn.commit()
    if not row:
        return {}
    conflict_keys = int(len(conf_groups or []))
    return {
        "nodes_active": int(row.get("nodes_active") or 0),
        "nodes_no_embedding": int(row.get("nodes_no_embedding") or 0),
        "nodes_with_subject": int(row.get("nodes_with_subject") or 0),
        "nodes_goal": int(row.get("nodes_goal") or 0),
        "subject_keys_with_conflicts": conflict_keys,
    }


def memory_graph_activation_log_insert(
    *,
    dashboard_id: uuid.UUID | None,
    node_ids: list[int],
    query_sha256: str | None,
    meta: dict[str, Any],
) -> int:
    """Append one activation record for the current user."""
    tenant_id, user_id = _require_user_uuid()
    nids = [int(x) for x in node_ids if int(x) > 0][:200]
    qh = (query_sha256 or "").strip().lower()
    if qh and len(qh) != 64:
        qh = qh[:64]
    m = meta if isinstance(meta, dict) else {}
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_memory_graph_activation_log (
                  tenant_id, user_id, dashboard_id, node_ids, query_sha256, meta
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (tenant_id, user_id, dashboard_id, nids, qh or None, Json(m)),
            )
            rid = cur.fetchone()
        conn.commit()
    return int(rid[0]) if rid else 0


def memory_graph_activation_log_list(*, limit: int = 100) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 100), 500))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, dashboard_id, node_ids, query_sha256, meta, created_at
                FROM user_memory_graph_activation_log
                WHERE tenant_id = %s AND user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, user_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        w = r.get("dashboard_id")
        out.append(
            {
                "id": int(r["id"]),
                "dashboard_id": str(w) if w else None,
                "node_ids": [int(x) for x in (r.get("node_ids") or [])],
                "query_sha256": r.get("query_sha256"),
                "meta": r.get("meta") if isinstance(r.get("meta"), dict) else {},
                "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
            }
        )
    return out


