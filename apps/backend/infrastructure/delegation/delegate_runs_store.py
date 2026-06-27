"""Audit log for delegate auto-respond executions."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.db import db


def insert_delegate_run(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    trigger: str,
    decision_summary: str,
    synthetic_user_message: str,
    agent_run_id: uuid.UUID | str | None = None,
    outcome: str = "started",
    chain_index: int = 0,
) -> dict[str, Any]:
    rid = None
    if agent_run_id:
        try:
            rid = (
                agent_run_id
                if isinstance(agent_run_id, uuid.UUID)
                else uuid.UUID(str(agent_run_id).strip())
            )
        except ValueError:
            rid = None
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO delegate_runs (
                  tenant_id, user_id, conversation_id, trigger,
                  decision_summary, synthetic_user_message, agent_run_id,
                  outcome, chain_index
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    tenant_id,
                    user_id,
                    conversation_id,
                    (trigger or "idle").strip()[:32],
                    (decision_summary or "")[:4000],
                    (synthetic_user_message or "")[:8000],
                    rid,
                    (outcome or "started").strip()[:64],
                    max(0, int(chain_index)),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("delegate_runs insert returned no row")
    return {"id": str(row[0]), "created_at": row[1].isoformat() if row[1] else None}


def finish_delegate_run(
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    outcome: str,
    agent_run_id: uuid.UUID | str | None = None,
) -> None:
    rid = None
    if agent_run_id:
        try:
            rid = (
                agent_run_id
                if isinstance(agent_run_id, uuid.UUID)
                else uuid.UUID(str(agent_run_id).strip())
            )
        except ValueError:
            rid = None
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            if rid is not None:
                cur.execute(
                    """
                    UPDATE delegate_runs
                    SET outcome = %s, agent_run_id = COALESCE(%s, agent_run_id), finished_at = now()
                    WHERE id = %s AND user_id = %s
                    """,
                    ((outcome or "done").strip()[:64], rid, run_id, user_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE delegate_runs
                    SET outcome = %s, finished_at = now()
                    WHERE id = %s AND user_id = %s
                    """,
                    ((outcome or "done").strip()[:64], run_id, user_id),
                )
        conn.commit()


def list_delegate_runs(*, user_id: uuid.UUID, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 200))
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, conversation_id, trigger, decision_summary,
                       synthetic_user_message, agent_run_id, outcome, chain_index,
                       created_at, finished_at
                FROM delegate_runs
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, lim),
            )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": str(r[0]),
                "conversation_id": str(r[1]),
                "trigger": r[2],
                "decision_summary": r[3],
                "synthetic_user_message": r[4],
                "agent_run_id": str(r[5]) if r[5] else None,
                "outcome": r[6],
                "chain_index": int(r[7]),
                "created_at": r[8].isoformat() if r[8] else None,
                "finished_at": r[9].isoformat() if r[9] else None,
            }
        )
    return out
