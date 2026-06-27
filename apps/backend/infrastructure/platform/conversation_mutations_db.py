"""Write-side persistence for chat conversations."""
from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Json

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.conversation_common import (
    ingress_conversation_messages_if_enabled,
    insert_chat_message,
    normalize_model_catalog_owned_by,
    pref_active_task_allowed,
    pref_workspace_allowed,
    serialize_message_content,
    shared_chat_can_write,
    user_tenant_id,
)


def _conversation_get(user_id: uuid.UUID, conversation_id: uuid.UUID) -> dict[str, Any] | None:
    from apps.backend.infrastructure.platform.conversations_db import conversation_get

    return conversation_get(user_id, conversation_id)

def conversation_update_delegate_prefs(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    delegate_auto_respond_enabled: bool | None = None,
    delegate_auto_respond_after_sec: int | None = None,
    delegate_max_chain_turns: int | None = None,
) -> dict[str, Any] | None:
    parts: list[str] = []
    args: list[Any] = []
    if delegate_auto_respond_enabled is not None:
        parts.append("delegate_auto_respond_enabled = %s")
        args.append(bool(delegate_auto_respond_enabled))
    if delegate_auto_respond_after_sec is not None:
        sec = max(15, min(int(delegate_auto_respond_after_sec), 600))
        parts.append("delegate_auto_respond_after_sec = %s")
        args.append(sec)
    if delegate_max_chain_turns is not None:
        turns = max(1, min(int(delegate_max_chain_turns), 10))
        parts.append("delegate_max_chain_turns = %s")
        args.append(turns)
    if not parts:
        return _conversation_get(user_id, conversation_id)
    parts.append("updated_at = now()")
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            args.extend([conversation_id, user_id])
            # SECURITY: Column names in `parts` come from function parameters
            # (e.g. is_auto_respond_enabled, delegate_auto_respond_after_sec).
            # All values are parameterized via %s placeholders.
            cur.execute(
                f"""
                UPDATE chat_conversations SET {", ".join(parts)}
                WHERE id = %s AND user_id = %s AND shared = false
                """,
                args,
            )
            if cur.rowcount < 1:
                return None
        conn.commit()
    return _conversation_get(user_id, conversation_id)


def conversation_create(
    user_id: uuid.UUID,
    *,
    title: str,
    mode: str,
    model: str,
    messages: list[dict[str, Any]],
    agent_log: list[Any] | dict[str, Any],
    dashboard_id: uuid.UUID | None = None,
    shared: bool = False,
    agent_id: str | None = None,
    workspace_id: uuid.UUID | None = None,
    model_catalog_owned_by: str | None = None,
    benchmark_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    tenant_id = user_tenant_id(user_id)
    messages = ingress_conversation_messages_if_enabled(messages, user_id=user_id, tenant_id=tenant_id)
    pref_agent: str | None = None
    if isinstance(agent_id, str) and agent_id.strip():
        pref_agent = agent_id.strip()[:128]
    pref_ws: uuid.UUID | None = None
    if workspace_id is not None:
        pref_ws = workspace_id if isinstance(workspace_id, uuid.UUID) else uuid.UUID(str(workspace_id))
    pref_owned = normalize_model_catalog_owned_by(model_catalog_owned_by)
    from apps.backend.domain.shared.identity import get_benchmark_run_id

    bench_run_id = benchmark_run_id or get_benchmark_run_id()
    if shared:
        pref_agent = None
        pref_ws = None
        if dashboard_id is None:
            raise ValueError("shared conversation requires dashboard_id")
        if not shared_chat_can_write(user_id, tenant_id, dashboard_id):
            raise PermissionError("cannot create shared dashboard chat for this user")
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT owner_user_id, tenant_id FROM user_dashboards
                    WHERE id = %s AND tenant_id = %s
                    """,
                    (dashboard_id, tenant_id),
                )
                ws_row = cur.fetchone()
                if ws_row is None:
                    conn.commit()
                    raise ValueError("dashboard not found")
                owner_uid = ws_row[0]
                if not isinstance(owner_uid, uuid.UUID):
                    owner_uid = uuid.UUID(str(owner_uid))
                conv_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO chat_conversations (
                      id, user_id, tenant_id, dashboard_id, title, mode, model, agent_log, shared,
                      pref_model_catalog_owned_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, true, %s)
                    """,
                    (
                        conv_id,
                        owner_uid,
                        tenant_id,
                        dashboard_id,
                        title,
                        mode,
                        model,
                        Json(agent_log),
                        pref_owned,
                    ),
                )
                for i, m in enumerate(messages):
                    insert_chat_message(cur, conv_id, i, m)
            conn.commit()
        got = _conversation_get(user_id, conv_id)
        if not got:
            raise RuntimeError("conversation_create: row missing after insert")
        return got

    conv_id = uuid.uuid4()
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            ws_bind: uuid.UUID | None = pref_ws
            if ws_bind is not None and not pref_workspace_allowed(cur, user_id, ws_bind):
                ws_bind = None
            cur.execute(
                """
                INSERT INTO chat_conversations (
                  id, user_id, tenant_id, dashboard_id, title, mode, model, agent_log, shared,
                  pref_agent_id, pref_workspace_id, pref_model_catalog_owned_by, benchmark_run_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, false, %s, %s, %s, %s)
                """,
                (
                    conv_id,
                    user_id,
                    tenant_id,
                    dashboard_id,
                    title,
                    mode,
                    model,
                    Json(agent_log),
                    pref_agent,
                    ws_bind,
                    pref_owned,
                    bench_run_id,
                ),
            )
            for i, m in enumerate(messages):
                insert_chat_message(cur, conv_id, i, m)
        conn.commit()
    got = _conversation_get(user_id, conv_id)
    if not got:
        raise RuntimeError("conversation_create: row missing after insert")
    return got


def conversation_replace(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    title: str | None,
    mode: str | None,
    model: str | None,
    messages: list[dict[str, Any]] | None,
    agent_log: list[Any] | dict[str, Any] | None,
    composer_prefs: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, tenant_id, dashboard_id, shared
                FROM chat_conversations WHERE id = %s
                """,
                (conversation_id,),
            )
            meta = cur.fetchone()
            if meta is None:
                return None
            row_user, tenant_id, ws_id, shared = (
                meta[0],
                int(meta[1]),
                meta[2],
                bool(meta[3]),
            )
            if shared and ws_id is not None:
                if not shared_chat_can_write(user_id, tenant_id, ws_id):
                    return None
            elif row_user != user_id:
                return None
            parts: list[str] = []
            args: list[Any] = []
            if title is not None:
                parts.append("title = %s")
                args.append(title)
            if mode is not None:
                parts.append("mode = %s")
                args.append(mode if mode in ("chat", "agent") else "chat")
            if model is not None:
                parts.append("model = %s")
                args.append(model)
            if agent_log is not None:
                parts.append("agent_log = %s::jsonb")
                args.append(Json(agent_log))
            if composer_prefs is not None and not shared:
                if "agent_id" in composer_prefs:
                    raw_a = composer_prefs.get("agent_id")
                    if raw_a is None or (isinstance(raw_a, str) and not str(raw_a).strip()):
                        parts.append("pref_agent_id = NULL")
                    elif isinstance(raw_a, str):
                        parts.append("pref_agent_id = %s")
                        args.append(raw_a.strip()[:128])
                if "model_catalog_owned_by" in composer_prefs:
                    owned = normalize_model_catalog_owned_by(
                        composer_prefs.get("model_catalog_owned_by")
                    )
                    if owned:
                        parts.append("pref_model_catalog_owned_by = %s")
                        args.append(owned)
                    else:
                        parts.append("pref_model_catalog_owned_by = NULL")
                if "workspace_id" in composer_prefs:
                    raw_w = composer_prefs.get("workspace_id")
                    if raw_w is None:
                        parts.append("pref_workspace_id = NULL")
                    else:
                        try:
                            wid = (
                                raw_w
                                if isinstance(raw_w, uuid.UUID)
                                else uuid.UUID(str(raw_w))
                            )
                        except (ValueError, TypeError):
                            parts.append("pref_workspace_id = NULL")
                        else:
                            if pref_workspace_allowed(cur, user_id, wid):
                                parts.append("pref_workspace_id = %s")
                                args.append(wid)
                            else:
                                parts.append("pref_workspace_id = NULL")
                if "active_task_id" in composer_prefs:
                    raw_t = composer_prefs.get("active_task_id")
                    if raw_t is None:
                        parts.append("active_task_id = NULL")
                    else:
                        try:
                            tid = (
                                raw_t
                                if isinstance(raw_t, uuid.UUID)
                                else uuid.UUID(str(raw_t))
                            )
                        except (ValueError, TypeError):
                            parts.append("active_task_id = NULL")
                        else:
                            if pref_active_task_allowed(cur, user_id, tenant_id, tid):
                                parts.append("active_task_id = %s")
                                args.append(tid)
                            else:
                                parts.append("active_task_id = NULL")
            parts.append("updated_at = now()")
            # SECURITY: Column names in `parts` come from function parameters
            # (is_auto_respond_enabled, delegate_auto_respond_after_sec, etc.).
            # All values are parameterized via %s placeholders.
            if shared:
                args.append(conversation_id)
                cur.execute(  # nosec B608
                    f"""
                    UPDATE chat_conversations SET {", ".join(parts)}
                    WHERE id = %s
                    """,
                    args,
                )
            else:
                args.extend([conversation_id, user_id])
                cur.execute(  # nosec B608
                    f"""
                    UPDATE chat_conversations SET {", ".join(parts)}
                    WHERE id = %s AND user_id = %s
                    """,
                    args,
                )
            if messages is not None:
                msgs_ing = ingress_conversation_messages_if_enabled(
                    messages, user_id=user_id, tenant_id=int(tenant_id)
                )
                cur.execute(
                    "DELETE FROM chat_messages WHERE conversation_id = %s",
                    (conversation_id,),
                )
                for i, m in enumerate(msgs_ing):
                    insert_chat_message(cur, conversation_id, i, m)
                msg_count = len(msgs_ing)
                cur.execute(
                    """
                    UPDATE chat_conversations
                    SET context_summary = CASE
                          WHEN context_summary_message_count > %s THEN '' ELSE context_summary END,
                        context_summary_message_count = CASE
                          WHEN context_summary_message_count > %s THEN 0
                          ELSE context_summary_message_count END,
                        context_summary_updated_at = CASE
                          WHEN context_summary_message_count > %s THEN NULL
                          ELSE context_summary_updated_at END
                    WHERE id = %s
                    """,
                    (msg_count, msg_count, msg_count, conversation_id),
                )
        conn.commit()
    return _conversation_get(user_id, conversation_id)


def conversation_delete(user_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, tenant_id, dashboard_id, shared
                FROM chat_conversations WHERE id = %s
                """,
                (conversation_id,),
            )
            meta = cur.fetchone()
            if meta is None:
                return False
            row_user, tenant_id, ws_id, shared = (
                meta[0],
                int(meta[1]),
                meta[2],
                bool(meta[3]),
            )
            if shared and ws_id is not None:
                if not shared_chat_can_write(user_id, tenant_id, ws_id):
                    return False
                cur.execute(
                    "DELETE FROM chat_conversations WHERE id = %s RETURNING id",
                    (conversation_id,),
                )
            elif row_user != user_id:
                return False
            else:
                cur.execute(
                    "DELETE FROM chat_conversations WHERE id = %s AND user_id = %s RETURNING id",
                    (conversation_id, user_id),
                )
            row = cur.fetchone()
        conn.commit()
    return row is not None


def conversation_append_message(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    role: str,
    content: Any,
) -> bool:
    """Append one message to a conversation (next ``position``). Personal chats only (same checks as delete)."""
    if role not in ("user", "assistant", "system"):
        return False
    serialized = serialize_message_content(content)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, dashboard_id, shared FROM chat_conversations WHERE id = %s
                """,
                (conversation_id,),
            )
            meta = cur.fetchone()
            if meta is None:
                return False
            row_user, _ws_id, shared = meta[0], meta[1], bool(meta[2])
            if shared:
                return False
            if row_user != user_id:
                return False
            cur.execute(
                """
                SELECT COALESCE(MAX(position), -1) + 1 FROM chat_messages
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
            pos_row = cur.fetchone()
            pos = int(pos_row[0]) if pos_row else 0
            cur.execute(
                """
                INSERT INTO chat_messages (conversation_id, position, role, content)
                VALUES (%s, %s, %s, %s)
                """,
                (conversation_id, pos, role, serialized),
            )
            cur.execute(
                "UPDATE chat_conversations SET updated_at = now() WHERE id = %s",
                (conversation_id,),
            )
        conn.commit()
    return True
