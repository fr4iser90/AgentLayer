"""Domain collection tools — source of truth without dashboards."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.collections import access as col_access
from apps.backend.domain.collections import db as col_db
from apps.backend.domain.identity import get_identity

__version__ = "1.0.0"
TOOL_ID = "collection"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "collection"
TOOL_LABEL = "Collections"
TOOL_DESCRIPTION = (
    "Domain source of truth for user data (pets, tasks, lists, metadata). "
    "Dashboards are views — write here; boards project this data for display."
)
TOOL_TRIGGERS = (
    "collection",
    "pets",
    "items",
    "domain data",
    "remember list",
)
TOOL_CAPABILITIES = ("domain.collection.read", "domain.collection.write")
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "ensure": {"min_role": "user", "capabilities": ("domain.collection.write",)},
    "list_collections": {"min_role": "user", "capabilities": ("domain.collection.read",)},
    "item_append": {"min_role": "user", "capabilities": ("domain.collection.write",)},
    "item_update": {"min_role": "user", "capabilities": ("domain.collection.write",)},
    "item_delete": {"min_role": "user", "capabilities": ("domain.collection.write",)},
    "metadata_patch": {"min_role": "user", "capabilities": ("domain.collection.write",)},
    "items_list": {"min_role": "user", "capabilities": ("domain.collection.read",)},
}


def _err(msg: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False)


def _uid_tid() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return int(tid), uid


def ensure(arguments: dict[str, Any]) -> str:
    ident = _uid_tid()
    if ident is None:
        return _err("No user identity")
    tid, uid = ident
    slug = str(arguments.get("slug") or "").strip()
    if not slug:
        return _err("slug required")
    try:
        row = col_db.collection_ensure(
            tenant_id=tid,
            owner_user_id=uid,
            slug=slug,
            title=str(arguments.get("title") or "").strip(),
            schema_hint=str(arguments.get("schema_hint") or "").strip() or None,
        )
    except ValueError as e:
        return _err(str(e))
    return json.dumps({"ok": True, "collection": row}, ensure_ascii=False)


def list_collections(arguments: dict[str, Any]) -> str:
    ident = _uid_tid()
    if ident is None:
        return _err("No user identity")
    _tid, uid = ident
    try:
        limit = int(arguments.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    rows = col_db.collection_list(uid, limit=limit)
    return json.dumps({"ok": True, "collections": rows, "count": len(rows)}, ensure_ascii=False)


def item_append(arguments: dict[str, Any]) -> str:
    ident = _uid_tid()
    if ident is None:
        return _err("No user identity")
    tid, uid = ident
    slug = str(arguments.get("slug") or "").strip()
    list_key = str(arguments.get("list_key") or arguments.get("list_path") or "items").strip()
    rows = arguments.get("rows")
    if not slug:
        return _err("slug required")
    if not isinstance(rows, list) or not rows:
        return _err("rows must be a non-empty array")
    acc, col_or_err = col_access.resolve_collection(uid, slug, need_write=True)
    if acc is None:
        if col_or_err != "collection not found or no access":
            return _err(col_or_err)
        try:
            col = col_db.collection_ensure(tenant_id=tid, owner_user_id=uid, slug=slug, title=slug)
        except ValueError as e:
            return _err(str(e))
    else:
        col = col_or_err
    cid = uuid.UUID(str(col["id"]))
    added = col_db.items_append(cid, list_key, [r for r in rows if isinstance(r, dict)])
    return json.dumps(
        {
            "ok": True,
            "source": "domain",
            "slug": slug,
            "list_key": list_key,
            "added_count": len(added),
            "added": added,
            "total_count": len(col_db.items_list(cid, list_key)),
        },
        ensure_ascii=False,
    )


def item_update(arguments: dict[str, Any]) -> str:
    ident = _uid_tid()
    if ident is None:
        return _err("No user identity")
    _tid, uid = ident
    slug = str(arguments.get("slug") or "").strip()
    list_key = str(arguments.get("list_key") or arguments.get("list_path") or "items").strip()
    row_id = str(arguments.get("row_id") or "").strip()
    patch = arguments.get("patch")
    if not slug or not row_id:
        return _err("slug and row_id required")
    if not isinstance(patch, dict) or not patch:
        return _err("patch must be a non-empty object")
    acc, col_or_err = col_access.resolve_collection(uid, slug, need_write=True)
    if acc is None:
        return _err(col_or_err)
    col = col_or_err
    updated = col_db.item_update(uuid.UUID(str(col["id"])), list_key, row_id, patch)
    if not updated:
        return _err("row not found")
    return json.dumps(
        {"ok": True, "source": "domain", "slug": slug, "row_id": row_id, "row": updated},
        ensure_ascii=False,
    )


def item_delete(arguments: dict[str, Any]) -> str:
    ident = _uid_tid()
    if ident is None:
        return _err("No user identity")
    _tid, uid = ident
    slug = str(arguments.get("slug") or "").strip()
    list_key = str(arguments.get("list_key") or arguments.get("list_path") or "items").strip()
    row_id = str(arguments.get("row_id") or "").strip()
    acc, col_or_err = col_access.resolve_collection(uid, slug, need_write=True)
    if acc is None:
        return _err(col_or_err)
    col = col_or_err
    if not col_db.item_delete(uuid.UUID(str(col["id"])), list_key, row_id):
        return _err("row not found")
    return json.dumps(
        {"ok": True, "source": "domain", "slug": slug, "list_key": list_key, "row_id": row_id},
        ensure_ascii=False,
    )


def metadata_patch(arguments: dict[str, Any]) -> str:
    ident = _uid_tid()
    if ident is None:
        return _err("No user identity")
    _tid, uid = ident
    slug = str(arguments.get("slug") or "").strip()
    patches = arguments.get("patches")
    if not slug:
        return _err("slug required")
    if not isinstance(patches, list) or not patches:
        return _err("patches required")
    acc, col_or_err = col_access.resolve_collection(uid, slug, need_write=True)
    if acc is None:
        return _err(col_or_err)
    fields: dict[str, Any] = {}
    for p in patches:
        if isinstance(p, dict) and str(p.get("path") or "").strip():
            fields[str(p["path"]).strip()] = p.get("value")
    if not fields:
        return _err("no valid patches")
    row = col_db.collection_metadata_patch(acc.owner_user_id, acc.slug, fields)
    if not row:
        return _err("collection not found")
    return json.dumps({"ok": True, "source": "domain", "slug": slug, "collection": row}, ensure_ascii=False)


def items_list(arguments: dict[str, Any]) -> str:
    ident = _uid_tid()
    if ident is None:
        return _err("No user identity")
    _tid, uid = ident
    slug = str(arguments.get("slug") or "").strip()
    list_key = str(arguments.get("list_key") or arguments.get("list_path") or "items").strip()
    acc, col_or_err = col_access.resolve_collection(uid, slug, need_write=False)
    if acc is None:
        return _err(col_or_err)
    col = col_or_err
    rows = col_db.items_list(uuid.UUID(str(col["id"])), list_key)
    meta = col.get("metadata") if isinstance(col.get("metadata"), dict) else {}
    return json.dumps(
        {
            "ok": True,
            "source": "domain",
            "slug": slug,
            "list_key": list_key,
            "items": rows,
            "metadata": meta,
            "count": len(rows),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "ensure": ensure,
    "list_collections": list_collections,
    "item_append": item_append,
    "item_update": item_update,
    "item_delete": item_delete,
    "metadata_patch": metadata_patch,
    "items_list": items_list,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "ensure",
            "description": "Create or get a domain collection by slug (e.g. pets, shopping).",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                    "schema_hint": {"type": "string"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_collections",
            "description": "List domain collections for the user.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "item_append",
            "description": "Append rows to a collection list (source of truth). No dashboard required.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "list_key": {"type": "string", "description": "e.g. pets, items, albums.0.photos"},
                    "rows": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["slug", "rows"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "items_list",
            "description": "Read items from a collection list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "list_key": {"type": "string"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "metadata_patch",
            "description": "Patch scalar/metadata fields (hero, notes, latest_summary).",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "patches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "value": {},
                            },
                        },
                    },
                },
                "required": ["slug", "patches"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "item_update",
            "description": "Update one row by row_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "list_key": {"type": "string"},
                    "row_id": {"type": "string"},
                    "patch": {"type": "object"},
                },
                "required": ["slug", "row_id", "patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "item_delete",
            "description": "Delete one row by row_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "list_key": {"type": "string"},
                    "row_id": {"type": "string"},
                },
                "required": ["slug", "row_id"],
            },
        },
    },
]
