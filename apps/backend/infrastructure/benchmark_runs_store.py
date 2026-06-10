"""DB store for admin benchmark runs."""

from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def create_run(
    *,
    tenant_id: int,
    user_id: uuid.UUID | None,
    suite: str,
    manifest_path: str,
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    run_id = uuid.uuid4()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO benchmark_runs (
                  id, tenant_id, user_id, status, suite, manifest_path, profiles_json
                ) VALUES (%s, %s, %s, 'queued', %s, %s, %s::jsonb)
                RETURNING *
                """,
                (
                    run_id,
                    tenant_id,
                    user_id,
                    suite,
                    manifest_path,
                    json.dumps(profiles),
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _serialize(row)


def update_run(run_id: uuid.UUID, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "status",
        "report_json",
        "summary_json",
        "error_text",
        "resource_prefix",
        "started_at",
        "finished_at",
    }
    sets: list[str] = []
    params: list[Any] = []
    for key, val in fields.items():
        if key not in allowed:
            continue
        if key in ("report_json", "summary_json") and val is not None:
            sets.append(f"{key} = %s::jsonb")
            params.append(json.dumps(val))
        else:
            sets.append(f"{key} = %s")
            params.append(val)
    if not sets:
        return get_run(run_id)
    params.append(run_id)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"UPDATE benchmark_runs SET {', '.join(sets)} WHERE id = %s RETURNING *",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def get_run(run_id: uuid.UUID) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM benchmark_runs WHERE id = %s", (run_id,))
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def list_runs(*, tenant_id: int, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(100, int(limit)))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, user_id, status, suite, manifest_path,
                       profiles_json, summary_json, error_text, resource_prefix,
                       started_at, finished_at, created_at
                FROM benchmark_runs
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, lim),
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return [_serialize(r) for r in rows]


_INTERRUPTED_ERROR = (
    "Benchmark interrupted: server restarted while this run was queued or in progress."
)


def reconcile_orphaned_runs_on_startup() -> int:
    """Mark queued/running rows failed after process restart (in-memory worker is gone)."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_runs
                SET status = 'failed',
                    finished_at = COALESCE(finished_at, now()),
                    error_text = COALESCE(NULLIF(TRIM(error_text), ''), %s)
                WHERE status IN ('queued', 'running')
                """,
                (_INTERRUPTED_ERROR,),
            )
            count = int(cur.rowcount or 0)
        conn.commit()
    return count


def any_running(*, tenant_id: int) -> bool:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM benchmark_runs
                WHERE tenant_id = %s AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (tenant_id,),
            )
            found = cur.fetchone() is not None
        conn.commit()
    return found


def delete_run(*, run_id: uuid.UUID, tenant_id: int) -> str:
    """Delete a finished benchmark run. Returns ``deleted``, ``not_found``, or ``running``."""
    row = get_run(run_id)
    if not row or int(row.get("tenant_id") or 0) != tenant_id:
        return "not_found"
    if str(row.get("status") or "") in ("queued", "running"):
        return "running"
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM benchmark_runs WHERE id = %s AND tenant_id = %s",
                (run_id, tenant_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return "deleted" if deleted else "not_found"
