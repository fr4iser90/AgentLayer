"""Persistence for versioned tenant agent prompt drafts."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db


def _ser(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            out[key] = str(value)
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def list_prompt_versions(*, tenant_id: int, agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
    lim = max(1, min(100, int(limit)))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, agent_id, version, status, prompt_text, notes,
                       created_at, created_by, published_at, published_by, archived_at
                FROM agent_prompt_versions
                WHERE tenant_id = %s AND agent_id = %s
                ORDER BY version DESC
                LIMIT %s
                """,
                (tenant_id, agent_id, lim),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(row) for row in rows]


def get_published_prompt(*, tenant_id: int, agent_id: str) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, agent_id, version, status, prompt_text, notes,
                       created_at, created_by, published_at, published_by, archived_at
                FROM agent_prompt_versions
                WHERE tenant_id = %s AND agent_id = %s AND status = 'published'
                """,
                (tenant_id, agent_id),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def get_prompt_version(
    *, tenant_id: int, agent_id: str, version_id: uuid.UUID
) -> dict[str, Any] | None:
    """One version by id, whatever its status — the gate needs the draft text."""
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, agent_id, version, status, prompt_text, notes,
                       created_at, created_by, published_at, published_by, archived_at
                FROM agent_prompt_versions
                WHERE id = %s AND tenant_id = %s AND agent_id = %s
                """,
                (version_id, tenant_id, str(agent_id or "").strip()),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def create_prompt_draft(
    *,
    tenant_id: int,
    agent_id: str,
    prompt_text: str,
    notes: str | None,
    created_by: uuid.UUID | None,
) -> dict[str, Any]:
    aid = str(agent_id or "").strip()
    prompt = str(prompt_text or "").strip()
    if not aid:
        raise ValueError("agent_id required")
    if not prompt:
        raise ValueError("prompt_text required")
    if len(prompt) > 12000:
        raise ValueError("prompt_text exceeds 12000 characters")
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                FROM agent_prompt_versions
                WHERE tenant_id = %s AND agent_id = %s
                """,
                (tenant_id, aid),
            )
            next_version = int(cur.fetchone()["next_version"])
            cur.execute(
                """
                INSERT INTO agent_prompt_versions (
                  tenant_id, agent_id, version, status, prompt_text, notes, created_by
                ) VALUES (%s, %s, %s, 'draft', %s, %s, %s)
                RETURNING id, tenant_id, agent_id, version, status, prompt_text, notes,
                          created_at, created_by, published_at, published_by, archived_at
                """,
                (tenant_id, aid, next_version, prompt, notes, created_by),
            )
            row = cur.fetchone()
        conn.commit()
    return _ser(dict(row))


def publish_prompt_version(
    *,
    tenant_id: int,
    agent_id: str,
    version_id: uuid.UUID,
    published_by: uuid.UUID | None,
    risk_level: str = "unassessed",
    risk_reasons: list[str] | None = None,
    override_by: uuid.UUID | None = None,
    override_reason: str | None = None,
) -> dict[str, Any]:
    aid = str(agent_id or "").strip()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id FROM agent_prompt_versions
                WHERE id = %s AND tenant_id = %s AND agent_id = %s
                """,
                (version_id, tenant_id, aid),
            )
            if not cur.fetchone():
                raise ValueError("prompt version not found")
            cur.execute(
                """
                UPDATE agent_prompt_versions
                SET status = 'archived', archived_at = COALESCE(archived_at, now())
                WHERE tenant_id = %s AND agent_id = %s AND status = 'published'
                """,
                (tenant_id, aid),
            )
            cur.execute(
                """
                UPDATE agent_prompt_versions
                SET status = 'published',
                    published_at = now(),
                    published_by = %s,
                    archived_at = NULL,
                    risk_level = %s,
                    risk_reasons = %s,
                    assessed_at = now(),
                    override_by = %s,
                    override_reason = %s
                WHERE id = %s AND tenant_id = %s AND agent_id = %s
                RETURNING id, tenant_id, agent_id, version, status, prompt_text, notes,
                          created_at, created_by, published_at, published_by, archived_at,
                          risk_level, risk_reasons, assessed_at, override_by, override_reason
                """,
                (
                    published_by,
                    risk_level,
                    Json(list(risk_reasons or [])),
                    override_by,
                    override_reason,
                    version_id,
                    tenant_id,
                    aid,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("prompt version publish failed")
    return _ser(dict(row))
