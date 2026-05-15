"""Persist ``coding_workspace_verify`` outcomes (Postgres)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)


def insert_verify_run(
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_run_id: str | None,
    command: str,
    exit_code: int,
    ok: bool,
    output_preview: str | None,
    error_message: str | None = None,
) -> uuid.UUID | None:
    """Insert one row; returns new id or ``None`` on failure."""
    rid = uuid.uuid4()
    cmd_stored = (command or "").strip()
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workspace_verify_runs (
                      id, workspace_id, user_id, agent_run_id, command,
                      exit_code, ok, output_preview, error_message
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        rid,
                        workspace_id,
                        user_id,
                        (agent_run_id or "").strip() or None,
                        cmd_stored[:8000] if cmd_stored else "(not configured)",
                        int(exit_code),
                        bool(ok),
                        (output_preview or "")[:12000] if output_preview else None,
                        (error_message or "")[:4000] if error_message else None,
                    ),
                )
            conn.commit()
        return rid
    except Exception:
        logger.exception("workspace_verify_store.insert_verify_run failed")
        return None


def list_verify_runs(*, workspace_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50) -> list[dict[str, Any]]:
    """Last N runs for a workspace (owner/editor/viewer access checked by caller)."""
    lim = max(1, min(200, int(limit)))
    out: list[dict[str, Any]] = []
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.id, r.workspace_id, r.user_id, r.agent_run_id, r.command, r.exit_code, r.ok,
                           r.output_preview, r.error_message, r.created_at
                    FROM workspace_verify_runs r
                    INNER JOIN project_workspaces w ON w.id = r.workspace_id
                    WHERE r.workspace_id = %s
                      AND (w.owner_user_id = %s OR w.access_role IN ('editor', 'viewer'))
                    ORDER BY r.created_at DESC
                    LIMIT %s
                    """,
                    (workspace_id, user_id, lim),
                )
                rows = cur.fetchall() or []
        for row in rows:
            out.append(
                {
                    "id": str(row[0]),
                    "workspace_id": str(row[1]),
                    "user_id": str(row[2]),
                    "agent_run_id": row[3],
                    "command": row[4],
                    "exit_code": row[5],
                    "ok": row[6],
                    "output_preview": row[7],
                    "error_message": row[8],
                    "created_at": row[9].isoformat() if row[9] else None,
                }
            )
    except Exception:
        logger.exception("workspace_verify_store.list_verify_runs failed")
    return out
