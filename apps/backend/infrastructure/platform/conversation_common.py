"""Shared persistence helpers for chat conversation readers and mutations."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from apps.backend.domain.agent_runtime.task_access import user_may_access_task_row
from apps.backend.infrastructure.dashboards import dashboard_persistence as dashboard_db
from apps.backend.infrastructure.db import db


def serialize_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def deserialize_message_content(raw: str | None) -> Any:
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


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_message_created_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return ensure_utc(raw)
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
            return ensure_utc(datetime.fromisoformat(s))
        except ValueError:
            return None
    return None


def created_at_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return ensure_utc(dt).isoformat()


def insert_chat_message(
    cur: Any,
    conversation_id: uuid.UUID,
    position: int,
    message: dict[str, Any],
) -> None:
    role = message.get("role") or "user"
    content = serialize_message_content(message.get("content"))
    if role not in ("user", "assistant", "system"):
        role = "user"
    created = parse_message_created_at(message.get("created_at"))
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


def user_tenant_id(user_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("user not found")
            return int(row[0])


def ingress_conversation_messages_if_enabled(
    messages: list[dict[str, Any]],
    *,
    user_id: uuid.UUID,
    tenant_id: int,
) -> list[dict[str, Any]]:
    from apps.backend.infrastructure.platform.chat_secret_ingress import ingress_messages_list_copy

    return ingress_messages_list_copy(messages, tenant_id=tenant_id, user_id=user_id)


def shared_chat_can_write(user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID) -> bool:
    role = dashboard_db.dashboard_access(user_id, tenant_id, dashboard_id)
    return role is not None and role != "viewer"


def pref_workspace_allowed(cur: Any, user_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
    cur.execute(
        "SELECT 1 FROM project_workspaces WHERE id = %s AND owner_user_id = %s",
        (workspace_id, user_id),
    )
    return cur.fetchone() is not None


def pref_active_task_allowed(
    cur: Any,
    user_id: uuid.UUID,
    tenant_id: int,
    task_id: uuid.UUID,
) -> bool:
    cur.execute(
        """
        SELECT tenant_id, created_by_user_id, workspace_id
        FROM agent_tasks WHERE id = %s
        """,
        (task_id,),
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


def normalize_model_catalog_owned_by(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    out = "".join(c for c in s if c.isalnum() or c in "_-")[:64]
    return out or None


def conversation_source_from_bridge(provider: Any) -> str:
    if provider is None:
        return "web"
    if isinstance(provider, str):
        s = provider.strip().lower()
        return s if s else "web"
    return "web"


def row_to_list_item(row: tuple[Any, ...]) -> dict[str, Any]:
    cid = row[0]
    if not isinstance(cid, uuid.UUID):
        cid = uuid.UUID(str(cid))
    wid = row[6]
    ws_out: str | None = None
    if wid is not None:
        ws_out = str(wid) if isinstance(wid, uuid.UUID) else str(uuid.UUID(str(wid)))
    shared = bool(row[7])
    pref_agent = row[8]
    pref_ws = row[9]
    pref_owned = row[10]
    bridge_provider = row[11]
    pref_ws_out: str | None = None
    if pref_ws is not None:
        pref_ws_out = str(pref_ws) if isinstance(pref_ws, uuid.UUID) else str(uuid.UUID(str(pref_ws)))
    return {
        "id": str(cid),
        "title": row[1] or "",
        "mode": row[2],
        "model": row[3] or "",
        "updated_at": row[4].isoformat() if isinstance(row[4], datetime) else str(row[4]),
        "message_count": int(row[5] or 0),
        "dashboard_id": ws_out,
        "shared": shared,
        "agent_id": str(pref_agent).strip() if pref_agent else None,
        "workspace_id": pref_ws_out,
        "model_catalog_owned_by": normalize_model_catalog_owned_by(pref_owned),
        "source": conversation_source_from_bridge(bridge_provider),
    }


def fetch_messages(cur: Any, conversation_id: uuid.UUID) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT role, content, created_at FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY position ASC
        """,
        (conversation_id,),
    )
    out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        created = row[2]
        if isinstance(created, datetime):
            created_s = created_at_iso(created)
        elif isinstance(created, str) and created.strip():
            created_s = created.strip()
        else:
            created_s = ""
        out.append(
            {
                "role": row[0],
                "content": deserialize_message_content(row[1]),
                "created_at": created_s,
            }
        )
    return out
