"""CRUD for ``agent_artifacts`` (durable outputs referenced by tasks and delegates)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db

_MAX_CONTENT_CHARS = 120_000
_MAX_SUMMARY_CHARS = 2000


def row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def create_artifact(
    *,
    tenant_id: int,
    created_by_user_id: uuid.UUID,
    kind: str,
    summary: str,
    content: dict[str, Any] | None = None,
    workspace_id: uuid.UUID | None = None,
    content_ref: str | None = None,
    created_by_task_id: uuid.UUID | None = None,
    created_by_run_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = dict(content or {})
    text_field = body.get("text")
    if isinstance(text_field, str) and len(text_field) > _MAX_CONTENT_CHARS:
        body["text"] = text_field[:_MAX_CONTENT_CHARS]
        body["truncated"] = True
    summ = (summary or "").strip()[:_MAX_SUMMARY_CHARS] or kind[:200]
    task_fk = created_by_task_id
    if task_fk is not None:
        from apps.backend.infrastructure.agent_runtime import agent_tasks_store

        if not agent_tasks_store.get_task(task_id=task_fk, tenant_id=tenant_id):
            task_fk = None
    run_fk = created_by_run_id
    if run_fk is not None:
        from apps.backend.infrastructure.agent_runtime import agent_runs_store

        if not agent_runs_store.run_exists(run_id=run_fk, tenant_id=tenant_id):
            run_fk = None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO agent_artifacts (
                  tenant_id, created_by_user_id, workspace_id, kind, summary,
                  content, content_ref, created_by_task_id, created_by_run_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    tenant_id,
                    created_by_user_id,
                    workspace_id,
                    (kind or "report").strip()[:64],
                    summ,
                    Json(body),
                    (content_ref or "").strip()[:2000] or None,
                    task_fk,
                    run_fk,
                    Json(dict(metadata or {})),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def get_artifact(*, artifact_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM agent_artifacts WHERE id = %s AND tenant_id = %s",
                (artifact_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def list_artifacts_for_task(
    *,
    tenant_id: int,
    task_id: uuid.UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(100, int(limit)))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM agent_artifacts
                WHERE tenant_id = %s AND created_by_task_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, task_id, lim),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]
