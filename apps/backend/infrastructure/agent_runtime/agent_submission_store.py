"""Persistence for user-submitted agent drafts (P7a staging + review queue).

Mirrors ``agent_access_policy_store``: dict-row cursor, ``Json`` wrapper for the
JSONB payload, inline validation, ``_ser`` serialisation (UUID -> str, datetimes
-> isoformat). The review lifecycle is ``pending`` -> ``approved`` / ``rejected``.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db

_RISK_KEYWORDS = (
    "secret", "token", "api key", "password", "credential", "ssh", "gpg",
    "shell", "exec", "subprocess", "eval", "os.system", "delete", "rm -",
    "curl", "wget", "nc ", "nmap", "sudo", "root", "privilege",
)
_SLUG_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _slug(raw: str, fallback: str = "imported_agent") -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw or "").strip().lower()).strip("_")
    if not base or not _SLUG_RE.match(base):
        base = f"agent_{base}" or fallback
    return base[:64]


def _assess_risk(yaml_payload: dict[str, Any], system_prompt: str | None) -> str:
    needle = " ".join([
        str(v).lower()
        for v in (
            yaml_payload.get("description") or "",
            yaml_payload.get("system_prompt") or "",
            *([str(t).lower() for t in (yaml_payload.get("tool_allowlist") or [])]),
        )
        if v
    ])
    if system_prompt:
        needle += " " + system_prompt.lower()
    hits = [kw for kw in _RISK_KEYWORDS if kw in needle]
    if any(kw in needle for kw in ("sudo", "root", "privilege", "exec", "subprocess", "os.system", "eval")):
        return "high"
    if len(hits) >= 2:
        return "high"
    if hits:
        return "medium"
    return "low"


def _validate_payload(
    *,
    agent_id: str,
    agent_yaml: Any,
    system_prompt: str | None,
    risk_level: str | None,
) -> dict[str, Any]:
    if not agent_id or not str(agent_id).strip():
        raise ValueError("agent_id is required")
    slug = _slug(agent_id)
    if not isinstance(agent_yaml, dict) or not agent_yaml:
        raise ValueError("agent_yaml must be a non-empty object")
    if not str(agent_yaml.get("id", slug)).strip():
        agent_yaml = {**agent_yaml, "id": slug}
    if risk_level is None:
        risk_level = _assess_risk(agent_yaml, system_prompt)
    if risk_level not in ("low", "medium", "high"):
        raise ValueError("risk_level must be low, medium, or high")
    return {"slug": slug, "agent_yaml": agent_yaml, "risk_level": risk_level}


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


def assess_submission(
    *,
    agent_id: str,
    agent_yaml: dict[str, Any],
    system_prompt: str | None = None,
    risk_level: str | None = None,
) -> dict[str, Any]:
    """Assess a draft for storage without writing anything (KI pre-filter backing).

    Reuses the same validation/slug/risk logic as ``create_submission`` so the
    pre-filter and the persisted row agree on the resulting slug, agent_id and
    risk level.
    """
    validated = _validate_payload(
        agent_id=agent_id, agent_yaml=agent_yaml, system_prompt=system_prompt, risk_level=risk_level
    )
    return {
        "slug": validated["slug"],
        "agent_yaml": validated["agent_yaml"],
        "risk_level": validated["risk_level"],
        "target_dir": f"plugins/agents/{validated['slug']}",
    }


def create_submission(
    *,
    agent_id: str,
    agent_yaml: dict[str, Any],
    title: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    target_dir: str | None = None,
    author_id: str,
    risk_level: str | None = None,
) -> dict[str, Any]:
    validated = _validate_payload(
        agent_id=agent_id, agent_yaml=agent_yaml, system_prompt=system_prompt, risk_level=risk_level
    )
    uid = uuid.uuid4()
    payload: dict[str, Any] = dict(agent_yaml)
    params: tuple[Any, ...] = (
        uid,
        validated["slug"],
        (title or payload.get("name") or None),
        (description or payload.get("description") or None),
        system_prompt,
        Json(payload),
        (target_dir or f"plugins/agents/{validated['slug']}"),
        validated["risk_level"],
        str(author_id),
    )
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO agent_submissions (
                      id, agent_id, title, description, system_prompt, agent_yaml,
                      target_dir, risk_level, status, author_id
                    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, 'pending', %s)
                    RETURNING *
                    """,
                    params,
                )
                row = cur.fetchone()
            except UniqueViolation:
                raise ValueError(
                    "a pending submission already exists for agent_id "
                    f"{validated['slug']!r}; reject or approve it first"
                ) from None
        conn.commit()
    if not row:
        raise ValueError("agent submission create failed")
    return _ser(dict(row))


def list_submissions(
    *,
    status: str | None = None,
    author_id: str | None = None,
    agent_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        status_s = str(status).strip().lower()
        if status_s not in ("pending", "approved", "rejected"):
            raise ValueError("status must be pending, approved, or rejected")
        clauses.append("status = %s")
        params.append(status_s)
    if author_id is not None:
        clauses.append("author_id = %s")
        params.append(str(author_id))
    if agent_id is not None:
        clauses.append("agent_id = %s")
        params.append(str(agent_id).strip())
    where = f"({' AND '.join(clauses)})" if clauses else "true"
    lim = max(1, min(200, int(limit)))
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT id, agent_id, title, description, system_prompt, agent_yaml,
                       target_dir, risk_level, status, author_id, reviewed_by,
                       reviewed_at, review_notes, materialize_error,
                       created_at, updated_at
                FROM agent_submissions
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(row) for row in rows]


def get_submission(submission_id: str | uuid.UUID) -> dict[str, Any] | None:
    sid = uuid.UUID(str(submission_id))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM agent_submissions WHERE id = %s",
                (sid,),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def review_submission(
    *,
    submission_id: str | uuid.UUID,
    decision: str,
    reviewed_by: str,
    review_notes: str | None = None,
) -> dict[str, Any]:
    decision_s = str(decision).strip().lower()
    if decision_s not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")
    sid = uuid.UUID(str(submission_id))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE agent_submissions
                SET status = CASE WHEN %s::text = 'approve' THEN 'approved' ELSE 'rejected' END,
                    reviewed_by = %s,
                    reviewed_at = now(),
                    review_notes = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (decision_s, str(reviewed_by), review_notes, sid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("agent submission not found")
    return _ser(dict(row))


def set_materialize_error(submission_id: str | uuid.UUID, error: str | None) -> None:
    sid = uuid.UUID(str(submission_id))
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE agent_submissions SET materialize_error = %s, updated_at = now() WHERE id = %s",
                (error, sid),
            )
            if cur.rowcount == 0:
                raise ValueError("agent submission not found")
        conn.commit()
