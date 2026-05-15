"""User memory tools: structured facts + semantic notes (pgvector).

Opt-in writes: call when user explicitly asks to remember / store something.
Reads: retrieval can be used for answering, but do not hallucinate memory.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Callable

from apps.backend.api import memory as memory_api

__version__ = "1.0.0"
TOOL_ID = "memory"
TOOL_BUCKET = "knowledge"
TOOL_DOMAIN = "memory"
TOOL_LABEL = "Memory"
TOOL_DESCRIPTION = (
    "Opt-in persistent user memory: structured facts (key/value JSON) and semantic notes (pgvector). "
    "Use when the user asks to save/remember something (name, preferences, facts) or to recall stored memory."
)
# Router: substring match on lowercased user text → ``memory`` category → memory_* tools (not in ``tool_routing.py``).
TOOL_TRIGGERS = (
    "remember",
    "merke",
    "merken",
    "memory",
    "profil",
    "preferences",
    "speichern",
    "abspeichern",
    "einprägen",
    "notiere",
    "gedächtnis",
)
TOOL_CAPABILITIES = ("knowledge.memory",)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


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


def memory_fact_upsert(arguments: dict[str, Any]) -> str:
    key = (arguments.get("key") or "").strip()
    if not key:
        return _err("key is required")
    value_json = arguments.get("value_json")
    if value_json is None:
        return _err("value_json is required")
    wid = _parse_uuid(arguments.get("dashboard_id"))
    confidence = arguments.get("confidence")
    source = arguments.get("source")
    exp_raw = arguments.get("expires_at")
    expires_at: datetime | None = None
    if isinstance(exp_raw, str) and exp_raw.strip():
        try:
            expires_at = datetime.fromisoformat(exp_raw.strip())
        except ValueError:
            return _err("expires_at must be ISO timestamp")
    try:
        row = memory_api.fact_upsert_for_identity(
            key=key,
            value_json=value_json,
            dashboard_id=wid,
            confidence=float(confidence) if confidence is not None else None,
            source=str(source) if source is not None else None,
            expires_at=expires_at,
        )
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "fact": row}, ensure_ascii=False)


def memory_fact_list(arguments: dict[str, Any]) -> str:
    wid = _parse_uuid(arguments.get("dashboard_id"))
    prefix = arguments.get("prefix")
    try:
        limit = int(arguments.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    try:
        rows = memory_api.fact_list_for_identity(
            dashboard_id=wid,
            prefix=str(prefix) if isinstance(prefix, str) else None,
            limit=limit,
        )
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "facts": rows, "count": len(rows)}, ensure_ascii=False)


def memory_fact_delete(arguments: dict[str, Any]) -> str:
    key = (arguments.get("key") or "").strip()
    if not key:
        return _err("key is required")
    wid = _parse_uuid(arguments.get("dashboard_id"))
    try:
        ok = memory_api.fact_delete_for_identity(key=key, dashboard_id=wid)
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "deleted": bool(ok)}, ensure_ascii=False)


def memory_note_add(arguments: dict[str, Any]) -> str:
    text = (arguments.get("text") or "").strip()
    if not text:
        return _err("text is required")
    wid = _parse_uuid(arguments.get("dashboard_id"))
    tags = arguments.get("tags")
    tag_list: list[str] | None = None
    if isinstance(tags, list):
        tag_list = [str(x).strip() for x in tags if str(x).strip()]
    source = arguments.get("source")
    try:
        out = memory_api.note_add_for_identity(
            text=text,
            dashboard_id=wid,
            tags=tag_list,
            source=str(source) if isinstance(source, str) else None,
        )
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, **out}, ensure_ascii=False)


def memory_note_search(arguments: dict[str, Any]) -> str:
    q = (arguments.get("query") or "").strip()
    if not q:
        return _err("query is required")
    wid = _parse_uuid(arguments.get("dashboard_id"))
    tags = arguments.get("tags")
    tag_list: list[str] | None = None
    if isinstance(tags, list):
        tag_list = [str(x).strip() for x in tags if str(x).strip()]
    try:
        limit = int(arguments.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    try:
        hits = memory_api.note_search_for_identity(query=q, dashboard_id=wid, tags=tag_list, limit=limit)
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "hits": hits, "count": len(hits)}, ensure_ascii=False)


def memory_note_delete(arguments: dict[str, Any]) -> str:
    try:
        nid = int(arguments.get("note_id"))
    except (TypeError, ValueError):
        return _err("note_id must be an integer")
    try:
        ok = memory_api.note_delete_for_identity(note_id=nid)
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "deleted": bool(ok)}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "memory_fact_upsert": memory_fact_upsert,
    "memory_fact_list": memory_fact_list,
    "memory_fact_delete": memory_fact_delete,
    "memory_note_add": memory_note_add,
    "memory_note_search": memory_note_search,
    "memory_note_delete": memory_note_delete,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "memory_fact_upsert",
            "TOOL_DESCRIPTION": "Upsert one structured memory fact (key/value JSON). Use only on explicit user request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string", "TOOL_DESCRIPTION": "Optional dashboard UUID scope"},
                    "key": {"type": "string"},
                    "value_json": {"type": "object"},
                    "confidence": {"type": "number"},
                    "source": {"type": "string"},
                    "expires_at": {"type": "string", "TOOL_DESCRIPTION": "Optional ISO timestamp"},
                },
                "required": ["key", "value_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_fact_list",
            "TOOL_DESCRIPTION": "List this user's memory facts (active, not expired).",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "prefix": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_fact_delete",
            "TOOL_DESCRIPTION": "Delete one memory fact by key (soft-delete).",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "key": {"type": "string"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_note_add",
            "TOOL_DESCRIPTION": "Add a semantic memory note (embedded server-side). Use only on explicit user request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "text": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_note_search",
            "TOOL_DESCRIPTION": "Semantic search over previously stored memory notes for this user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "query": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_note_delete",
            "TOOL_DESCRIPTION": "Delete one memory note by id (soft-delete).",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer"},
                },
                "required": ["note_id"],
            },
        },
    },
]

