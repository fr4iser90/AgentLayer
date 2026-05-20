"""Rolling chat context for out-of-band gateways (Telegram, Discord, …) → ``chat_messages``.

The Web UI and HTTP ``/v1/chat/completions`` already send full ``messages[]`` from the client;
only bridges that used to pass a single user turn need this persistence.

**Workspace / agent (bridges):** After migration ``schema_044``, ``bridge_agent_sessions`` may store
``workspace_id`` and ``default_agent_id``. Users set them with slash commands (see
:func:`bridge_try_slash_command`). ``bridge_chat_completion_extras`` merges ``workspace_id`` /
``agent_id`` into the ``chat_completion`` body.

**Adding a new gateway:** implement a module under ``apps/backend/integrations/`` that calls
``bridge_agent_conversation_ensure`` → ``bridge_try_slash_command`` (optional) →
``messages_for_bridge_completion`` → merge ``bridge_chat_completion_extras`` → ``chat_completion``
→ ``conversation_append_message`` (see ``telegram_bridge.py`` / ``discord_bridge.py``).
Step-by-step: ``apps/backend/integrations/bridges/README.md``.
"""

from __future__ import annotations

import logging
import re
import uuid
from types import SimpleNamespace
from typing import Any

from psycopg.types.json import Json

from apps.backend.infrastructure.conversations_db import conversation_get
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

# Stored in ``bridge_agent_sessions.provider`` (TEXT) and surfaced on conversations as ``source``.
# Use stable lowercase ids (e.g. telegram, discord, slack); no extra allowlist in ``conversations_db``.
BridgeProvider = str

BRIDGE_TELEGRAM: BridgeProvider = "telegram"
BRIDGE_DISCORD: BridgeProvider = "discord"

# Cap messages sent to the LLM (user + assistant turns); avoids huge prompts on long chats.
MAX_CONTEXT_MESSAGES = 48

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _thread_key(thread_id: int | None) -> int:
    return int(thread_id) if thread_id is not None else 0


def bridge_agent_conversation_ensure(
    user_id: uuid.UUID,
    tenant_id: int,
    *,
    provider: BridgeProvider,
    scope_chat_id: int,
    scope_thread_id: int | None,
    model: str,
) -> uuid.UUID:
    """Return ``conversation_id`` for this peer, creating an empty conversation if needed.

    ``provider`` is stored as-is (normalized to lowercase in API ``source``) and groups chats
    in the web UI. New gateways: see ``apps/backend/integrations/bridges/README.md`` — no central
    allowlist beyond this insert.
    """
    tk = _thread_key(scope_thread_id)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT conversation_id FROM bridge_agent_sessions
                WHERE user_id = %s AND provider = %s AND scope_chat_id = %s AND scope_thread_id = %s
                """,
                (user_id, provider, scope_chat_id, tk),
            )
            row = cur.fetchone()
            if row:
                cid = row[0]
                return cid if isinstance(cid, uuid.UUID) else uuid.UUID(str(cid))
            conv_id = uuid.uuid4()
            title = f"{provider} {scope_chat_id}" + (f" · thread {tk}" if tk else "")
            cur.execute(
                """
                INSERT INTO chat_conversations (
                  id, user_id, tenant_id, dashboard_id, title, mode, model, agent_log, shared
                )
                VALUES (%s, %s, %s, NULL, %s, 'agent', %s, %s::jsonb, false)
                """,
                (conv_id, user_id, tenant_id, title, model, Json([])),
            )
            cur.execute(
                """
                INSERT INTO bridge_agent_sessions (
                  user_id, provider, scope_chat_id, scope_thread_id, conversation_id
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, provider, scope_chat_id, tk, conv_id),
            )
        conn.commit()
    return conv_id


def bridge_agent_session_reset(
    user_id: uuid.UUID,
    *,
    provider: BridgeProvider,
    scope_chat_id: int,
    scope_thread_id: int | None,
) -> bool:
    """Clear stored **messages** for this bridge session; keeps conversation + workspace/agent prefs."""
    tk = _thread_key(scope_thread_id)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT conversation_id FROM bridge_agent_sessions
                WHERE user_id = %s AND provider = %s AND scope_chat_id = %s AND scope_thread_id = %s
                """,
                (user_id, provider, scope_chat_id, tk),
            )
            row = cur.fetchone()
            if not row:
                return False
            cid = row[0]
            conv_id = cid if isinstance(cid, uuid.UUID) else uuid.UUID(str(cid))
            cur.execute("DELETE FROM chat_messages WHERE conversation_id = %s", (conv_id,))
            cur.execute(
                """
                UPDATE chat_conversations
                SET agent_log = %s::jsonb, updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (Json([]), conv_id, user_id),
            )
        conn.commit()
    return True


def bridge_session_get_runtime_prefs(
    user_id: uuid.UUID,
    *,
    provider: BridgeProvider,
    scope_chat_id: int,
    scope_thread_id: int | None,
) -> dict[str, Any]:
    """Return ``workspace_id`` / ``default_agent_id`` for this bridge peer (empty dict if unknown)."""
    tk = _thread_key(scope_thread_id)
    row: Any = None
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT workspace_id, default_agent_id
                    FROM bridge_agent_sessions
                    WHERE user_id = %s AND provider = %s AND scope_chat_id = %s AND scope_thread_id = %s
                    """,
                    (user_id, provider, scope_chat_id, tk),
                )
                row = cur.fetchone()
    except Exception:
        logger.debug("bridge_session_get_runtime_prefs: query failed (migration 044 applied?)", exc_info=True)
        return {}
    if not row:
        return {}
    wid, aid = row[0], row[1]
    out: dict[str, Any] = {}
    if wid is not None:
        out["workspace_id"] = str(wid) if isinstance(wid, uuid.UUID) else str(wid)
    if isinstance(aid, str) and aid.strip():
        out["default_agent_id"] = aid.strip()
    return out


def bridge_chat_completion_extras(
    user_id: uuid.UUID,
    *,
    provider: BridgeProvider,
    scope_chat_id: int,
    scope_thread_id: int | None,
) -> dict[str, Any]:
    """Keys to merge into ``chat_completion`` body: ``workspace_id``, optional ``agent_id``."""
    from apps.backend.domain.agent_access import default_agent_for_workspace

    prefs = bridge_session_get_runtime_prefs(
        user_id,
        provider=provider,
        scope_chat_id=scope_chat_id,
        scope_thread_id=scope_thread_id,
    )
    out: dict[str, Any] = {}
    wid = prefs.get("workspace_id")
    if isinstance(wid, str) and wid.strip():
        out["workspace_id"] = wid.strip()
    aid = prefs.get("default_agent_id")
    role = db.user_role(user_id) or "user"
    if isinstance(aid, str) and aid.strip():
        out["agent_id"] = aid.strip()
    elif out.get("workspace_id"):
        out["agent_id"] = default_agent_for_workspace(role)
    return out


def _bridge_user_like(user_id: uuid.UUID):
    role = (db.user_role(user_id) or "user").strip().lower()
    return SimpleNamespace(id=user_id, role=role if role in ("admin", "user", "guest") else "user")


def _user_may_use_agent(user_id: uuid.UUID, agent_id: str) -> tuple[bool, str]:
    from apps.backend.domain.agent_access import user_may_invoke_agent

    role = db.user_role(user_id) or "user"
    return user_may_invoke_agent(role, agent_id.strip())


def _bridge_update_session_columns(
    user_id: uuid.UUID,
    *,
    provider: BridgeProvider,
    scope_chat_id: int,
    scope_thread_id: int | None,
    workspace_id: uuid.UUID | None = None,
    workspace_clear: bool = False,
    default_agent_id: str | None = None,
    default_agent_clear: bool = False,
) -> bool:
    tk = _thread_key(scope_thread_id)
    sets: list[str] = []
    args: list[Any] = []
    if workspace_clear:
        sets.append("workspace_id = NULL")
    elif workspace_id is not None:
        sets.append("workspace_id = %s")
        args.append(workspace_id)
    if default_agent_clear:
        sets.append("default_agent_id = NULL")
    elif default_agent_id is not None:
        sets.append("default_agent_id = %s")
        args.append(default_agent_id[:64])
    if not sets:
        return True
    args.extend([user_id, provider, scope_chat_id, tk])
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE bridge_agent_sessions
                    SET {", ".join(sets)}
                    WHERE user_id = %s AND provider = %s AND scope_chat_id = %s AND scope_thread_id = %s
                    """,
                    args,
                )
                rc = cur.rowcount
            conn.commit()
        return rc > 0
    except Exception:
        logger.exception("bridge_update_session_columns failed")
        return False


def _bridge_list_workspace_lines(user_id: uuid.UUID, *, limit: int = 25) -> list[str]:
    lines: list[str] = []
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, name
                    FROM project_workspaces
                    WHERE owner_user_id = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall() or []
    except Exception:
        logger.exception("bridge list workspaces failed")
        return ["(could not load workspaces — database error)"]
    if not rows:
        return ["No project workspaces yet. Create one in the web app (Coding / workspaces)."]
    for wid, name in rows:
        lines.append(f"- `{wid}` — {name}")
    return lines


def _bridge_list_agent_lines(user_id: uuid.UUID) -> list[str]:
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    ur = (db.user_role(user_id) or "user").strip().lower()
    lines: list[str] = []
    for aid in sorted(reg.agent_ids()):
        ag = reg.get_agent(aid)
        if not ag:
            continue
        min_r = str(ag.get("min_role") or "user").strip().lower()
        if min_r == "admin" and ur != "admin":
            continue
        nm = str(ag.get("name") or aid)
        lines.append(f"- `{aid}` — {nm}")
    if not lines:
        return ["(no agents available)"]
    return lines


def bridge_try_slash_command(
    prompt: str,
    *,
    user_id: uuid.UUID,
    provider: BridgeProvider,
    scope_chat_id: int,
    scope_thread_id: int | None,
) -> str | None:
    """Handle ``/workspace`` / ``/agent`` bridge commands; return user-facing reply or ``None``."""
    raw = (prompt or "").strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split()
    head = parts[0].lower()

    if head == "/workspace":
        sub = (parts[1].lower() if len(parts) > 1 else "help")
        if sub in ("help", "?"):
            return (
                "**Workspace (this chat)**\n"
                "- `/workspace list` — your project workspaces (id + name)\n"
                "- `/workspace bind <uuid>` — attach a workspace for coding/security tools\n"
                "- `/workspace clear` — remove workspace binding\n"
                "After bind, messages use that repo unless you `/agent` something else. "
                "Use `/clear` to wipe chat history (workspace binding stays)."
            )
        if sub == "list":
            body = "\n".join(_bridge_list_workspace_lines(user_id))
            return "**Your workspaces**\n" + body
        if sub == "clear":
            ok = _bridge_update_session_columns(
                user_id,
                provider=provider,
                scope_chat_id=scope_chat_id,
                scope_thread_id=scope_thread_id,
                workspace_clear=True,
            )
            return "Workspace binding cleared." if ok else "No bridge session row (send a normal message first)."
        if sub == "bind":
            if len(parts) < 3:
                return "Usage: `/workspace bind <workspace-uuid>`"
            wid_s = parts[2].strip()
            if not _UUID_RE.match(wid_s):
                return "Invalid workspace id (expected UUID)."
            try:
                wu = uuid.UUID(wid_s)
            except ValueError:
                return "Invalid workspace id."
            from apps.backend.domain.workspace_resolver import resolve_workspace

            user = _bridge_user_like(user_id)
            ws = resolve_workspace(str(wu), user)
            if not ws:
                return "Workspace not found or not accessible for your account."
            ok = _bridge_update_session_columns(
                user_id,
                provider=provider,
                scope_chat_id=scope_chat_id,
                scope_thread_id=scope_thread_id,
                workspace_id=wu,
            )
            if not ok:
                return "Could not save binding (no bridge session — send any message first to open a session)."
            nm = str(ws.get("name") or "?")
            return f"Bound this chat to workspace **{nm}** (`{wu}`). Default agent for repo work: **coding** (override with `/agent`)."

    if head == "/agent":
        if len(parts) < 2:
            body = "\n".join(_bridge_list_agent_lines(user_id))
            return (
                "**Agent override (this chat)**\n"
                "- `/agent list` — agents you may use\n"
                "- `/agent <id>` — e.g. `/agent coding`, `/agent general`, `/agent security_auditor` (admin only)\n"
                "- `/agent clear` — remove override\n\n"
                + body
            )
        sub = parts[1].lower()
        if sub in ("help", "?"):
            body = "\n".join(_bridge_list_agent_lines(user_id))
            return (
                "**Agent override (this chat)**\n"
                "- `/agent list` — agents you may use\n"
                "- `/agent <id>` — e.g. `/agent coding`, `/agent general`, `/agent security_auditor` (admin only)\n"
                "- `/agent clear` — remove override (with a bound workspace, **coding** is used again)\n\n"
                + body
            )
        if sub == "list":
            body = "\n".join(_bridge_list_agent_lines(user_id))
            return "**Agents**\n" + body
        if sub == "clear":
            ok = _bridge_update_session_columns(
                user_id,
                provider=provider,
                scope_chat_id=scope_chat_id,
                scope_thread_id=scope_thread_id,
                default_agent_clear=True,
            )
            return "Agent override cleared." if ok else "No bridge session row (send a normal message first)."
        aid = parts[1].strip()
        ok_m, err = _user_may_use_agent(user_id, aid)
        if not ok_m:
            return err
        ok = _bridge_update_session_columns(
            user_id,
            provider=provider,
            scope_chat_id=scope_chat_id,
            scope_thread_id=scope_thread_id,
            default_agent_id=aid,
        )
        if not ok:
            return "Could not save agent (no bridge session — send any message first)."
        return f"Default agent for this chat: **{aid}**."

    return None


def messages_for_bridge_completion(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    new_user_text: str,
) -> list[dict[str, Any]]:
    """Load history (trimmed), append the new user turn; roles ``user`` / ``assistant`` only."""
    conv = conversation_get(user_id, conversation_id)
    if not conv:
        return [{"role": "user", "content": new_user_text}]
    raw = conv.get("messages") or []
    out: list[dict[str, Any]] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if content is None:
            continue
        if not isinstance(content, str):
            continue
        if not content.strip():
            continue
        out.append({"role": role, "content": content})
    if len(out) > MAX_CONTEXT_MESSAGES:
        out = out[-MAX_CONTEXT_MESSAGES:]
    out.append({"role": "user", "content": new_user_text})
    return out
