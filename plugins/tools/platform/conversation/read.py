"""Read stored conversation history on demand (full transcript; not the compacted LLM context)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.infrastructure.conversations_db import conversation_get

__version__ = "1.0.0"
TOOL_ID = "conversation"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "conversation"
TOOL_LABEL = "Conversation history"
TOOL_DESCRIPTION = (
    "Read verbatim messages from the current or a specified chat conversation. "
    "Use when older turns were compacted from the LLM context but you need exact wording, paths, or details."
)
# Router phrases: co-located read.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("meta.conversation.read",)
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "read": {"min_role": "user", "capabilities": ("meta.conversation.read",)},
}


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _parse_uuid(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return uuid.UUID(s)
    except ValueError:
        return None


def _content_preview(content: Any, max_len: int = 4000) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, dict) and p.get("type") == "image_url":
                parts.append("[image]")
        text = "\n".join(parts)
    else:
        text = json.dumps(content, ensure_ascii=False) if content is not None else ""
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


def read(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    from apps.backend.domain.identity import get_identity

    _tenant_id, user_id = get_identity()
    if user_id is None:
        return _err("not authenticated")

    ctx = context or {}
    conv_id = _parse_uuid(arguments.get("conversation_id"))
    if conv_id is None:
        conv_id = _parse_uuid(ctx.get("conversation_id"))
    if conv_id is None:
        return _err("conversation_id is required (or bind this chat with conversation_id in context)")

    conv = conversation_get(user_id, conv_id)
    if not conv:
        return _err("conversation not found or access denied")

    messages = conv.get("messages") or []
    if not isinstance(messages, list):
        messages = []

    offset = 0
    try:
        offset = max(0, int(arguments.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    limit = 20
    try:
        limit = max(1, min(100, int(arguments.get("limit") or 20)))
    except (TypeError, ValueError):
        limit = 20

    role_filter = str(arguments.get("role") or "").strip().lower()
    if role_filter and role_filter not in ("user", "assistant"):
        return _err("role must be user, assistant, or omitted")

    sliced = messages[offset:]
    if role_filter:
        sliced = [m for m in sliced if isinstance(m, dict) and m.get("role") == role_filter]

    page = sliced[:limit]
    rows: list[dict[str, Any]] = []
    for i, m in enumerate(page):
        if not isinstance(m, dict):
            continue
        rows.append(
            {
                "index": offset + i,
                "role": m.get("role"),
                "content": _content_preview(m.get("content")),
                "created_at": m.get("created_at") or "",
            }
        )

    summary = str(conv.get("context_summary") or "").strip()
    summary_covers = int(conv.get("context_summary_message_count") or 0)

    return _ok(
        {
            "conversation_id": str(conv_id),
            "title": conv.get("title") or "",
            "offset": offset,
            "limit": limit,
            "returned": len(rows),
            "total_messages": len(messages),
            "context_summary_covers_messages": summary_covers,
            "has_context_summary": bool(summary),
            "messages": rows,
        }
    )


HANDLERS: dict[str, Any] = {
    "read": read,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "TOOL_DESCRIPTION": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "Optional UUID; defaults to current chat."},
                    "offset": {"type": "integer", "description": "Message offset (default 0)."},
                    "limit": {"type": "integer", "description": "Max messages (1-100, default 20)."},
                    "role": {"type": "string", "enum": ["user", "assistant"], "description": "Optional role filter."},
                },
            },
        },
    },
]
