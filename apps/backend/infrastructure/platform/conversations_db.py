"""Persistence for server-side chat conversations (first-party UI)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Json

from apps.backend.domain.agent_runtime.task_access import user_may_access_task_row
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.dashboards import dashboard_persistence as dashboard_db


def _serialize_message_content(content: Any) -> str:
    """Store plain string or JSON-encode multimodal / structured content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _deserialize_message_content(raw: str | None) -> Any:
    """Restore OpenAI-style multimodal arrays saved as JSON text."""
    s = raw or ""
    st = s.strip()
    if not st:
        return ""
    if st.startswith("["):
        try:
            out = json.loads(s)
            if isinstance(out, list):
                return out
        except json.JSONDecodeError:
            pass
    return s


def _parse_message_created_at(raw: Any) -> datetime | None:
    """Parse client ``created_at`` (ISO-8601 string or Unix ms)."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return _ensure_utc(raw)
    if isinstance(raw, (int, float)):
        try:
            n = float(raw)
            if n > 1e12:
                n /= 1000.0
            return datetime.fromtimestamp(n, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = f"{s[:-1]}+00:00"
            return _ensure_utc(datetime.fromisoformat(s))
        except ValueError:
            return None
    return None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _created_at_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return _ensure_utc(dt).isoformat()


def _insert_chat_message(
    cur: Any,
    conversation_id: uuid.UUID,
    position: int,
    m: dict[str, Any],
) -> None:
    role = m.get("role") or "user"
    content = _serialize_message_content(m.get("content"))
    if role not in ("user", "assistant", "system"):
        role = "user"
    created = _parse_message_created_at(m.get("created_at"))
    if created is not None:
        cur.execute(
            """
            INSERT INTO chat_messages (conversation_id, position, role, content, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, position, role, content, created),
        )
    else:
        cur.execute(
            """
            INSERT INTO chat_messages (conversation_id, position, role, content)
            VALUES (%s, %s, %s, %s)
            """,
            (conversation_id, position, role, content),
        )


def _user_tenant_id(user_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("user not found")
            return int(row[0])


def _ingress_conversation_messages_if_enabled(
    messages: list[dict[str, Any]],
    *,
    user_id: uuid.UUID,
    tenant_id: int,
) -> list[dict[str, Any]]:
    from apps.backend.infrastructure.platform.chat_secret_ingress import ingress_messages_list_copy

    return ingress_messages_list_copy(messages, tenant_id=tenant_id, user_id=user_id)


def _shared_chat_can_write(user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID) -> bool:
    role = dashboard_db.dashboard_access(user_id, tenant_id, dashboard_id)
    return role is not None and role != "viewer"


def _normalize_model_catalog_owned_by(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    out = "".join(c for c in s if c.isalnum() or c in "_-")[:64]
    return out or None


def _conversation_source_from_bridge(provider: Any) -> str:
    """First-party chats have no ``bridge_agent_sessions`` row → ``web``.

    Any non-empty ``provider`` from the bridge table is returned normalized (lowercase)
    so new gateways (slack, matrix, …) need no Python enum updates.
    """
    if provider is None:
        return "web"
    if isinstance(provider, str):
        s = provider.strip().lower()
        return s if s else "web"
    return "web"


def _row_to_list_item(
    r: tuple[Any, ...],
) -> dict[str, Any]:
    cid = r[0]
    if not isinstance(cid, uuid.UUID):
        cid = uuid.UUID(str(cid))
    wid = r[6]
    ws_out: str | None = None
    if wid is not None:
        ws_out = str(wid) if isinstance(wid, uuid.UUID) else str(uuid.UUID(str(wid)))
    shared = bool(r[7])
    pref_agent = r[8]
    pref_ws = r[9]
    pref_owned = r[10]
    bridge_provider = r[11]
    pref_ws_out: str | None = None
    if pref_ws is not None:
        pref_ws_out = str(pref_ws) if isinstance(pref_ws, uuid.UUID) else str(uuid.UUID(str(pref_ws)))
    owned_out = _normalize_model_catalog_owned_by(pref_owned)
    return {
        "id": str(cid),
        "title": r[1] or "",
        "mode": r[2],
        "model": r[3] or "",
        "updated_at": r[4].isoformat() if isinstance(r[4], datetime) else str(r[4]),
        "message_count": int(r[5] or 0),
        "dashboard_id": ws_out,
        "shared": shared,
        "agent_id": str(pref_agent).strip() if pref_agent else None,
        "workspace_id": pref_ws_out,
        "model_catalog_owned_by": owned_out,
        "source": _conversation_source_from_bridge(bridge_provider),
    }


def conversations_list(
    user_id: uuid.UUID, *, dashboard_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    tenant_id = _user_tenant_id(user_id)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            if dashboard_id is not None:
                cur.execute(
                    """
                    SELECT c.id, c.title, c.mode, c.model, c.updated_at,
                      (SELECT COUNT(*)::int FROM chat_messages m WHERE m.conversation_id = c.id),
                      c.dashboard_id, c.shared,
                      c.pref_agent_id, c.pref_workspace_id, c.pref_model_catalog_owned_by,
                      (SELECT b.provider FROM bridge_agent_sessions b
                       WHERE b.conversation_id = c.id LIMIT 1)
                    FROM chat_conversations c
                    WHERE c.dashboard_id = %s
                      AND (
                        (c.shared = true AND EXISTS (
                          SELECT 1 FROM user_dashboards w
                          LEFT JOIN dashboard_members m
                            ON m.dashboard_id = w.id AND m.user_id = %s
                          WHERE w.id = c.dashboard_id AND w.tenant_id = c.tenant_id
                            AND (w.owner_user_id = %s OR m.user_id IS NOT NULL)
                        ))
                        OR (c.shared = false AND c.user_id = %s)
                      )
                    ORDER BY c.shared DESC, c.updated_at DESC
                    """,
                    (dashboard_id, user_id, user_id, user_id),
                )
            else:
                cur.execute(
                    """
                    SELECT c.id, c.title, c.mode, c.model, c.updated_at,
                      (SELECT COUNT(*)::int FROM chat_messages m WHERE m.conversation_id = c.id),
                      c.dashboard_id, c.shared,
                      c.pref_agent_id, c.pref_workspace_id, c.pref_model_catalog_owned_by,
                      (SELECT b.provider FROM bridge_agent_sessions b
                       WHERE b.conversation_id = c.id LIMIT 1)
                    FROM chat_conversations c
                    WHERE c.tenant_id = %s
                      AND (
                        (c.user_id = %s AND c.shared = false)
                        OR (
                          c.shared = true
                          AND c.dashboard_id IS NOT NULL
                          AND (
                            EXISTS (
                              SELECT 1 FROM user_dashboards w
                              WHERE w.id = c.dashboard_id
                                AND w.tenant_id = c.tenant_id
                                AND w.owner_user_id = %s
                            )
                            OR EXISTS (
                              SELECT 1 FROM dashboard_members m
                              WHERE m.dashboard_id = c.dashboard_id AND m.user_id = %s
                            )
                          )
                        )
                      )
                    ORDER BY c.updated_at DESC
                    """,
                    (tenant_id, user_id, user_id, user_id),
                )
            rows = cur.fetchall()
    return [_row_to_list_item(r) for r in rows]


def _pref_workspace_allowed(cur: Any, user_id: uuid.UUID, wid: uuid.UUID) -> bool:
    cur.execute(
        "SELECT 1 FROM project_workspaces WHERE id = %s AND owner_user_id = %s",
        (wid, user_id),
    )
    return cur.fetchone() is not None


def _pref_active_task_allowed(
    cur: Any, user_id: uuid.UUID, tenant_id: int, tid: uuid.UUID
) -> bool:
    cur.execute(
        """
        SELECT tenant_id, created_by_user_id, workspace_id
        FROM agent_tasks WHERE id = %s
        """,
        (tid,),
    )
    row = cur.fetchone()
    if not row:
        return False
    return user_may_access_task_row(
        user_id=user_id,
        tenant_id=tenant_id,
        row={
            "tenant_id": row[0],
            "created_by_user_id": row[1],
            "workspace_id": row[2],
        },
    )


def _fetch_messages(cur: Any, conversation_id: uuid.UUID) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT role, content, created_at FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY position ASC
        """,
        (conversation_id,),
    )
    mrows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for mr in mrows:
        ca = mr[2]
        if isinstance(ca, datetime):
            created_s = _created_at_iso(ca)
        elif isinstance(ca, str) and ca.strip():
            created_s = ca.strip()
        else:
            created_s = ""
        out.append(
            {
                "role": mr[0],
                "content": _deserialize_message_content(mr[1]),
                "created_at": created_s,
            }
        )
    return out


def conversation_get(user_id: uuid.UUID, conversation_id: uuid.UUID) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, mode, model, agent_log, updated_at, created_at, dashboard_id,
                       user_id, tenant_id, shared, pref_agent_id, pref_workspace_id,
                       pref_model_catalog_owned_by, active_task_id,
                       context_summary, context_summary_message_count, context_summary_updated_at,
                       delegate_auto_respond_enabled, delegate_auto_respond_after_sec,
                       delegate_max_chain_turns
                FROM chat_conversations
                WHERE id = %s
                """,
                (conversation_id,),
            )
            crow = cur.fetchone()
            if not crow:
                return None
            cid_raw = crow[0]
            wid = crow[7]
            row_user = crow[8]
            tenant_id = int(crow[9])
            shared = bool(crow[10])
            pref_agent_raw = crow[11]
            pref_ws_raw = crow[12]
            pref_owned_raw = crow[13]
            active_task_raw = crow[14]
            context_summary_raw = crow[15]
            context_summary_count_raw = crow[16]
            context_summary_updated_raw = crow[17]
            delegate_auto_enabled = bool(crow[18]) if len(crow) > 18 and crow[18] is not None else False
            delegate_auto_sec = int(crow[19]) if len(crow) > 19 and crow[19] is not None else 60
            delegate_max_chain = int(crow[20]) if len(crow) > 20 and crow[20] is not None else 3
            if shared and wid is not None:
                if not dashboard_db.dashboard_has_full_access(user_id, tenant_id, wid):
                    return None
            elif row_user != user_id:
                return None
            messages = _fetch_messages(cur, conversation_id)
            cur.execute(
                """
                SELECT provider FROM bridge_agent_sessions
                WHERE conversation_id = %s LIMIT 1
                """,
                (conversation_id,),
            )
            brow = cur.fetchone()
            bridge_provider = brow[0] if brow else None
    agent_log = crow[4]
    if isinstance(agent_log, str):
        try:
            agent_log = json.loads(agent_log)
        except Exception:
            agent_log = []
    if not isinstance(agent_log, (list, dict)):
        agent_log = []
    cid = cid_raw
    ws_out: str | None = None
    if wid is not None:
        ws_out = str(wid) if isinstance(wid, uuid.UUID) else str(uuid.UUID(str(wid)))
    pref_ws_out: str | None = None
    if pref_ws_raw is not None:
        pref_ws_out = (
            str(pref_ws_raw)
            if isinstance(pref_ws_raw, uuid.UUID)
            else str(uuid.UUID(str(pref_ws_raw)))
        )
    pref_agent_out = (
        str(pref_agent_raw).strip() if pref_agent_raw and str(pref_agent_raw).strip() else None
    )
    pref_owned_out = _normalize_model_catalog_owned_by(pref_owned_raw)
    active_task_out: str | None = None
    if active_task_raw is not None:
        active_task_out = (
            str(active_task_raw)
            if isinstance(active_task_raw, uuid.UUID)
            else str(uuid.UUID(str(active_task_raw)))
        )
    return {
        "id": str(cid if isinstance(cid, uuid.UUID) else uuid.UUID(str(cid))),
        "title": crow[1] or "",
        "mode": crow[2],
        "model": crow[3] or "",
        "agent_log": agent_log,
        "messages": messages,
        "updated_at": crow[5].isoformat() if isinstance(crow[5], datetime) else str(crow[5]),
        "created_at": crow[6].isoformat() if isinstance(crow[6], datetime) else str(crow[6]),
        "dashboard_id": ws_out,
        "shared": shared,
        "agent_id": pref_agent_out,
        "workspace_id": pref_ws_out,
        "model_catalog_owned_by": pref_owned_out,
        "active_task_id": active_task_out,
        "source": _conversation_source_from_bridge(bridge_provider),
        "context_summary": str(context_summary_raw or "").strip(),
        "context_summary_message_count": int(context_summary_count_raw or 0),
        "context_summary_updated_at": (
            context_summary_updated_raw.isoformat()
            if isinstance(context_summary_updated_raw, datetime)
            else (str(context_summary_updated_raw) if context_summary_updated_raw else "")
        ),
        "delegate_auto_respond_enabled": delegate_auto_enabled,
        "delegate_auto_respond_after_sec": max(15, min(delegate_auto_sec, 600)),
        "delegate_max_chain_turns": max(1, min(delegate_max_chain, 10)),
    }


from apps.backend.infrastructure.platform.conversation_mutations_db import (
    conversation_append_message,
    conversation_create,
    conversation_delete,
    conversation_replace,
    conversation_update_delegate_prefs,
)
