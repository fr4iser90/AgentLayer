"""Persist operator tool policy (admin UI); manifest defaults live in tool modules."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.plugin_system.tool_manifest_dimensions import (
    normalize_execution_context,
    normalize_min_role,
    parse_allowed_tenant_ids,
)
from apps.backend.infrastructure.db import db


def list_policies() -> list[dict[str, Any]]:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT package_id, tool_name, enabled, min_role, allowed_tenant_ids,
                       execution_context, updated_at
                FROM operator_tool_policies
                ORDER BY package_id, tool_name
                """
            )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        ex = r[5]
        if isinstance(ex, str) and ex.strip():
            ex = normalize_execution_context(ex.strip())
        else:
            ex = None
        tids = r[4]
        if tids is not None:
            tids = parse_allowed_tenant_ids(list(tids))
        out.append(
            {
                "package_id": r[0],
                "tool_name": r[1],
                "enabled": bool(r[2]),
                "min_role": normalize_min_role(str(r[3]) if r[3] is not None else None),
                "allowed_tenant_ids": tids,
                "execution_context": ex,
                "updated_at": r[6].isoformat() if r[6] else None,
            }
        )
    return out


def _policy_key(package_id: str, tool_name: str) -> tuple[str, str]:
    return (package_id.strip(), (tool_name or "*").strip() or "*")


def policies_map() -> dict[tuple[str, str], dict[str, Any]]:
    """(package_id, tool_name) -> row dict for policy merge."""
    m: dict[tuple[str, str], dict[str, Any]] = {}
    for row in list_policies():
        k = _policy_key(row["package_id"], row["tool_name"])
        m[k] = row
    return m


def upsert_policy(
    package_id: str,
    tool_name: str,
    *,
    enabled: bool,
    min_role: str,
    allowed_tenant_ids: list[int] | None,
    execution_context: str | None = None,
) -> None:
    pkg = package_id.strip()
    tn = (tool_name or "*").strip() or "*"
    mr = normalize_min_role(min_role)
    tids = parse_allowed_tenant_ids(allowed_tenant_ids)
    ex = execution_context
    if isinstance(ex, str) and ex.strip():
        ex = normalize_execution_context(ex.strip())
    else:
        ex = None
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO operator_tool_policies
                    (package_id, tool_name, enabled, min_role, allowed_tenant_ids,
                     execution_context, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (package_id, tool_name) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    min_role = EXCLUDED.min_role,
                    allowed_tenant_ids = EXCLUDED.allowed_tenant_ids,
                    execution_context = EXCLUDED.execution_context,
                    updated_at = now()
                """,
                (pkg, tn, enabled, mr, tids, ex),
            )
        conn.commit()


def replace_all_policies(rows: list[dict[str, Any]]) -> None:
    """Replace table contents with validated rows (admin save-all)."""
    cleaned: list[
        tuple[str, str, bool, str, list[int] | None, str | None]
    ] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        pid = str(r.get("package_id") or "").strip()
        if not pid:
            continue
        tn = str(r.get("tool_name") or "*").strip() or "*"
        en = r.get("enabled")
        if not isinstance(en, bool):
            en = True
        mr = normalize_min_role(str(r.get("min_role") or "user"))
        tids = parse_allowed_tenant_ids(r.get("allowed_tenant_ids"))
        ex = r.get("execution_context")
        if isinstance(ex, str) and ex.strip():
            ex = normalize_execution_context(ex.strip())
        else:
            ex = None
        cleaned.append((pid, tn, en, mr, tids, ex))
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM operator_tool_policies")
            for pid, tn, en, mr, tids, ex in cleaned:
                cur.execute(
                    """
                    INSERT INTO operator_tool_policies
                        (package_id, tool_name, enabled, min_role, allowed_tenant_ids,
                         execution_context, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    """,
                    (pid, tn, en, mr, tids, ex),
                )
        conn.commit()
