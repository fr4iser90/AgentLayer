"""Persistence for scoped agent access governance policies."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

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


def list_agent_policies(
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = ["scope = 'global'"]
    params: list[Any] = []
    if tenant_id is not None:
        clauses.append("(scope = 'tenant' AND tenant_id = %s)")
        params.append(int(tenant_id))
    if user_id is not None:
        clauses.append("(scope = 'user' AND user_id = %s)")
        params.append(user_id)
    where = f"({' OR '.join(clauses)})"
    if agent_id:
        where += " AND agent_id = %s"
        params.append(str(agent_id).strip())

    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT id, scope, tenant_id, user_id, agent_id, direct_state,
                       delegate_state, notes, updated_at, updated_by
                FROM agent_access_policies
                WHERE {where}
                ORDER BY
                  CASE scope WHEN 'global' THEN 0 WHEN 'tenant' THEN 1 ELSE 2 END,
                  agent_id
                """,
                tuple(params),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(row) for row in rows]


def upsert_agent_policy(
    *,
    scope: str,
    agent_id: str,
    direct_state: str,
    delegate_state: str,
    tenant_id: int | None,
    user_id: uuid.UUID | None,
    notes: str | None,
    updated_by: uuid.UUID | None,
) -> dict[str, Any]:
    scope_s = str(scope or "").strip().lower()
    aid = str(agent_id or "").strip()
    direct = str(direct_state or "inherit").strip().lower()
    delegate = str(delegate_state or "inherit").strip().lower()
    if scope_s not in ("global", "tenant", "user"):
        raise ValueError("scope must be global, tenant, or user")
    if direct not in ("inherit", "allow", "deny"):
        raise ValueError("direct_state must be inherit, allow, or deny")
    if delegate not in ("inherit", "allow", "deny"):
        raise ValueError("delegate_state must be inherit, allow, or deny")
    if not aid:
        raise ValueError("agent_id required")

    if scope_s == "global":
        tenant = None
        user = None
        match_where = "scope = 'global' AND agent_id = %s"
        match_params: tuple[Any, ...] = (aid,)
    elif scope_s == "tenant":
        if tenant_id is None:
            raise ValueError("tenant_id required for tenant scope")
        tenant = int(tenant_id)
        user = None
        match_where = "scope = 'tenant' AND tenant_id = %s AND agent_id = %s"
        match_params = (tenant, aid)
    else:
        if user_id is None:
            raise ValueError("user_id required for user scope")
        tenant = int(tenant_id) if tenant_id is not None else None
        user = user_id
        match_where = "scope = 'user' AND user_id = %s AND agent_id = %s"
        match_params = (user, aid)

    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                UPDATE agent_access_policies
                SET tenant_id = %s,
                    direct_state = %s,
                    delegate_state = %s,
                    notes = %s,
                    updated_at = now(),
                    updated_by = %s
                WHERE {match_where}
                RETURNING id, scope, tenant_id, user_id, agent_id, direct_state,
                          delegate_state, notes, updated_at, updated_by
                """,
                (tenant, direct, delegate, notes, updated_by, *match_params),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    INSERT INTO agent_access_policies (
                      scope, tenant_id, user_id, agent_id, direct_state, delegate_state, notes, updated_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, scope, tenant_id, user_id, agent_id, direct_state,
                              delegate_state, notes, updated_at, updated_by
                    """,
                    (scope_s, tenant, user, aid, direct, delegate, notes, updated_by),
                )
                row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("agent policy upsert failed")
    return _ser(dict(row))


def delete_agent_policy(
    *,
    scope: str,
    agent_id: str,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> bool:
    scope_s = str(scope or "").strip().lower()
    aid = str(agent_id or "").strip()
    if scope_s == "global":
        where = "scope = 'global' AND agent_id = %s"
        params: tuple[Any, ...] = (aid,)
    elif scope_s == "tenant":
        if tenant_id is None:
            raise ValueError("tenant_id required for tenant scope")
        where = "scope = 'tenant' AND tenant_id = %s AND agent_id = %s"
        params = (int(tenant_id), aid)
    elif scope_s == "user":
        if user_id is None:
            raise ValueError("user_id required for user scope")
        where = "scope = 'user' AND user_id = %s AND agent_id = %s"
        params = (user_id, aid)
    else:
        raise ValueError("scope must be global, tenant, or user")

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM agent_access_policies WHERE {where}", params)
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted
