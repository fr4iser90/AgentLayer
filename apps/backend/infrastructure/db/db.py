"""PostgreSQL pool and persistence helpers. Schema changes: Alembic (see entrypoint)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from apps.backend.infrastructure.platform.config import config
from apps.backend.domain.shared.identity import get_identity

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("database pool not initialized")
    return _pool


def pool_ready() -> bool:
    """True when PostgreSQL pool is initialized (unit tests often run without DB)."""
    return _pool is not None


def init_pool() -> None:
    global _pool
    if not config.DATABASE_URL:
        raise RuntimeError(
            "PostgreSQL connection missing: DATABASE_URL is empty and could not be built from "
            "POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB (and PGHOST defaulting to postgres). "
            "Fix: set DATABASE_URL in docker/.env (see .env.example), or pass the same POSTGRES_* "
            "variables into the agent-layer container as for the postgres service, then restart."
        )
    if _pool is not None:
        return
    _pool = ConnectionPool(
        conninfo=config.DATABASE_URL,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": False},
    )
    logger.info("PostgreSQL pool ready")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


from apps.backend.infrastructure.db.identity_tenants import (
    discord_user_id_normalize,
    scheduler_outbound_count_today_utc,
    scheduler_outbound_increment_utc,
    telegram_user_id_normalize,
    tenant_exists,
    tenant_insert,
    tenants_list,
    user_discord_user_id_get,
    user_discord_user_id_set,
    user_external_sub,
    user_first_admin_id,
    user_id_for_discord_user_id,
    user_id_for_telegram_user_id,
    user_id_tenant_for_discord_global,
    user_id_tenant_for_telegram_global,
    user_role,
    user_telegram_user_id_get,
    user_telegram_user_id_set,
    user_tenant_id,
    user_site_role,
    user_membership_role,
    tenant_membership_upsert,
    tenant_get,
    tenant_update_org_profile,
    tenant_mark_setup_completed,
    user_is_tenant_admin,
)
def _require_user_uuid() -> tuple[int, uuid.UUID]:
    tenant_id, user_id = get_identity()
    if user_id is None:
        raise ValueError(
            "no user identity in this context (chat/tool requests need user/tenant headers)"
        )
    return tenant_id, user_id


def todo_create(title: str) -> int:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO todos (title, tenant_id, user_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (title, tenant_id, user_id),
            )
            row = cur.fetchone()
            tid = int(row[0])
        conn.commit()
        return tid


def todo_list(limit: int = 100) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, title, status, created_at, updated_at
                FROM todos
                WHERE tenant_id = %s AND user_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (tenant_id, user_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def todo_set_status(todo_id: int, status: str) -> bool:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE todos
                SET status = %s, updated_at = now()
                WHERE id = %s AND tenant_id = %s AND user_id = %s
                """,
                (status, todo_id, tenant_id, user_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def log_tool_invocation(
    tool_name: str,
    args: dict[str, Any],
    result_text: str,
    ok: bool,
    *,
    agent_run_id: uuid.UUID | str | None = None,
) -> None:
    excerpt = (result_text or "")[:4000]
    tenant_id, user_id = get_identity()
    if user_id is None:
        return
    args_for_db: Any = args
    if isinstance(args, dict):
        redact = config.tool_log_redact_keys()
        if redact:
            args_for_db = {}
            for k, v in args.items():
                if k in redact and isinstance(v, str):
                    if len(v) > 200:
                        args_for_db[k] = f"<omitted {len(v)} chars>"
                    else:
                        args_for_db[k] = "<redacted>"
                else:
                    args_for_db[k] = v
    try:
        with pool().connection() as conn:
            with conn.cursor() as cur:
                run_uuid: uuid.UUID | None = None
                if agent_run_id is not None:
                    try:
                        run_uuid = (
                            agent_run_id
                            if isinstance(agent_run_id, uuid.UUID)
                            else uuid.UUID(str(agent_run_id).strip())
                        )
                    except (ValueError, TypeError):
                        run_uuid = None
                if run_uuid is not None and tenant_id is not None:
                    from apps.backend.infrastructure.agent_runtime import agent_runs_store

                    if not agent_runs_store.run_exists(
                        run_id=run_uuid, tenant_id=int(tenant_id)
                    ):
                        logger.warning(
                            "tool_invocation %s: agent_run_id %s not in agent_runs; logging without run link",
                            tool_name,
                            run_uuid,
                        )
                        run_uuid = None
                cur.execute(
                    """
                    INSERT INTO tool_invocations
                      (tool_name, args_json, result_excerpt, ok, tenant_id, user_id, agent_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tool_name, Json(args_for_db), excerpt, ok, tenant_id, user_id, run_uuid),
                )
            conn.commit()
    except psycopg.Error:
        logger.exception("failed to log tool_invocation for %s", tool_name)


def recent_tool_invocations(limit: int = 50) -> list[dict[str, Any]]:
    tenant_id, user_id = get_identity()
    if user_id is None:
        return []
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tool_name, args_json, result_excerpt, ok, created_at,
                       tenant_id, user_id
                FROM tool_invocations
                WHERE tenant_id = %s AND user_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (tenant_id, user_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def list_tool_invocations_for_agent_run(
    agent_run_id: uuid.UUID,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    lim = max(1, min(500, int(limit)))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tool_name, args_json, result_excerpt, ok, created_at, agent_run_id
                FROM tool_invocations
                WHERE agent_run_id = %s
                ORDER BY id ASC
                LIMIT %s
                """,
                (agent_run_id, lim),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


from apps.backend.infrastructure.db.user_secrets import (
    secret_upload_otp_create,
    user_secret_delete,
    user_secret_get_plaintext,
    user_secret_list_service_keys,
    user_secret_register_with_otp,
    user_secret_upsert,
)
def kb_note_append(title: str, body: str) -> int:
    tenant_id, user_id = _require_user_uuid()
    title = (title or "").strip()
    body = (body or "").strip()
    if not body:
        raise ValueError("body is required")
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_kb_notes (title, body, tenant_id, user_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (title, body, tenant_id, user_id),
            )
            row = cur.fetchone()
            nid = int(row[0])
        conn.commit()
    return nid


def _ilike_contains(s: str) -> str:
    esc = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def kb_note_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, min(int(limit or 20), 50))
    pat = _ilike_contains(q)
    sql_full = """
                SELECT id, title, left(body, 500) AS body_excerpt, created_at
                FROM user_kb_notes
                WHERE tenant_id = %s
                  AND (
                    user_id = %s
                    OR id IN (
                      SELECT note_id FROM user_kb_note_shares
                      WHERE grantee_user_id = %s
                    )
                  )
                  AND (
                    title ILIKE %s ESCAPE '\\'
                    OR body ILIKE %s ESCAPE '\\'
                    OR search_tsv @@ websearch_to_tsquery('simple', %s)
                  )
                ORDER BY created_at DESC
                LIMIT %s
                """
    sql_ilike = """
                SELECT id, title, left(body, 500) AS body_excerpt, created_at
                FROM user_kb_notes
                WHERE tenant_id = %s
                  AND (
                    user_id = %s
                    OR id IN (
                      SELECT note_id FROM user_kb_note_shares
                      WHERE grantee_user_id = %s
                    )
                  )
                  AND (
                    title ILIKE %s ESCAPE '\\'
                    OR body ILIKE %s ESCAPE '\\'
                  )
                ORDER BY created_at DESC
                LIMIT %s
                """
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    sql_full,
                    (tenant_id, user_id, user_id, pat, pat, q, limit),
                )
            except psycopg.Error:
                logger.debug(
                    "kb_note_search fts fallback for query %r", q[:80], exc_info=True
                )
                conn.rollback()
                cur.execute(
                    sql_ilike,
                    (tenant_id, user_id, user_id, pat, pat, limit),
                )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "title": r["title"],
                "body_excerpt": r["body_excerpt"],
                "created_at": (
                    r["created_at"].isoformat() if r.get("created_at") else None
                ),
            }
        )
    return out


def kb_note_get(note_id: int, max_body_chars: int = 12000) -> dict[str, Any] | None:
    tenant_id, user_id = _require_user_uuid()
    max_body_chars = max(500, min(int(max_body_chars or 12000), 100_000))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, title, body, created_at, updated_at, user_id AS owner_user_id
                FROM user_kb_notes
                WHERE id = %s AND tenant_id = %s
                  AND (
                    user_id = %s
                    OR id IN (
                      SELECT note_id FROM user_kb_note_shares
                      WHERE grantee_user_id = %s
                    )
                  )
                """,
                (note_id, tenant_id, user_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    body = str(row["body"] or "")
    if len(body) > max_body_chars:
        body = body[:max_body_chars] + "\n… (truncated)"
    owner_uid = row.get("owner_user_id")
    return {
        "id": row["id"],
        "title": row["title"],
        "body": body,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "is_owner": owner_uid == user_id,
        "owner_user_id": str(owner_uid) if owner_uid is not None else None,
    }


from apps.backend.infrastructure.db.memory_persistence import (
    memory_fact_delete,
    memory_fact_list,
    memory_fact_upsert,
    memory_graph_activation_log_insert,
    memory_graph_activation_log_list,
    memory_graph_activate,
    memory_graph_edge_insert,
    memory_graph_list_nodes,
    memory_graph_node_insert,
    memory_graph_node_soft_delete,
    memory_graph_stats,
    memory_note_insert,
    memory_note_soft_delete,
    memory_note_vector_search,
)
from apps.backend.infrastructure.db.rag_persistence import (
    rag_delete_document_by_id,
    rag_delete_documents_by_source_uri,
    rag_delete_documents_by_tenant_domain,
    rag_delete_documents_by_workspace,
    rag_document_and_chunks_insert,
    rag_documents_by_tenant_domain_index,
    rag_vector_search,
    rag_vector_search_by_workspace,
)
from apps.backend.infrastructure.db.tenant_content_persistence import (
    tenant_content_audit_insert,
    tenant_content_audit_list,
    tenant_content_get,
    tenant_content_get_published_by_slug,
    tenant_content_insert,
    tenant_content_list,
    tenant_content_slug_exists,
    tenant_content_update,
    tenant_content_version_get,
    tenant_content_version_insert,
    tenant_content_versions_list,
)
from apps.backend.infrastructure.db.tenant_profession_persistence import (
    department_get,
    department_get_by_slug,
    department_insert,
    departments_list,
    profession_assignment_get,
    profession_assignment_upsert,
    profession_assignments_list,
    profession_role_get,
    profession_role_get_by_slug,
    profession_role_insert,
    profession_roles_count,
    profession_roles_list,
    qualification_delete,
    qualification_insert,
    qualifications_list,
    tenant_content_get_by_source_uri,
)
from apps.backend.infrastructure.db.user_profiles import (
    DEFAULT_AGENT_PROFILE,
    user_agent_profile_get,
    user_agent_profile_upsert,
    user_persona_get,
    user_persona_upsert,
    user_resolve_in_tenant,
    user_timezone_persist,
)
from apps.backend.infrastructure.db.kb_note_sharing import (
    kb_note_is_owner,
    kb_note_share_create,
    kb_note_share_delete,
    kb_note_share_list,
)
from apps.backend.infrastructure.db.model_catalog_and_policies import (
    external_llm_endpoint_by_id,
    external_llm_endpoints_enabled_ordered,
    external_llm_endpoints_list_all,
    external_llm_endpoints_sync,
    model_access_policies_for_subject,
    model_access_policies_list,
    model_access_policies_sync,
    model_catalog_prefs_list_all,
    model_catalog_prefs_sync,
    model_catalog_visible_index,
    model_default_policies_for_subject,
    model_default_policies_list,
    model_default_policies_sync,
    provider_capability_policies_for_subject,
    provider_capability_policies_list,
    provider_capability_policies_sync,
)


from apps.backend.infrastructure.db.operator_provider_endpoints import (
    operator_provider_endpoint_by_id,
    operator_provider_endpoints_list_all,
    operator_provider_endpoints_sync,
)
