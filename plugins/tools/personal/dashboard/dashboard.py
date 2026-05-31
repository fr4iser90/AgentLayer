"""Generic dashboard tools: list, read, patch data paths, patch layout (guarded ops)."""

from __future__ import annotations

import builtins
import json
import uuid
from copy import deepcopy
from typing import Any, Callable

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.data_paths import apply_data_patches, top_level_key
from apps.backend.dashboard.tool_dashboard_resolve import resolve_dashboard_id
from apps.backend.domain.identity import get_identity

__version__ = "1.0.0"
TOOL_ID = "dashboard_core"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "dashboard"
TOOL_LABEL = "Dashboards (generic)"
TOOL_DESCRIPTION = (
    "List dashboards, read ui_layout + data, patch block data by path, and adjust layout "
    "(add/remove blocks, grid, props). Works for any kind; prefer kind-specific tools "
    "(ideas_*, pets_*, shopping_list_*) when available. Use dashboard_id from [Dashboard context] "
    "when the user has the board open. Does not create new dashboards — use the app catalog."
)
TOOL_TRIGGERS = (
    "dashboard",
    "dashboards",
    "board",
    "ui layout",
    "layout",
    "kanban",
    "chart block",
    "widget",
)
TOOL_CAPABILITIES = ("dashboard.read", "dashboard.write")

_MAX_PATCHES = 40
_MAX_LAYOUT_OPS = 20
_MAX_BLOCKS = 48
_MAX_READ_JSON = 200_000

_BLOCK_TYPES = frozenset({
    "table",
    "markdown",
    "rich_markdown",
    "gallery",
    "hero",
    "timeline",
    "stat",
    "chart",
    "sparkline",
    "kanban",
    "embed",
})

_BLOCK_PREFIX = {
    "table": "items",
    "markdown": "notes",
    "gallery": "photos",
    "hero": "hero",
    "timeline": "timeline",
    "stat": "stat",
    "chart": "chart",
    "sparkline": "sparkline",
    "kanban": "kanban",
    "rich_markdown": "rich_md",
    "embed": "embed",
}

_DEFAULT_TABLE_COLUMNS = [
    {"field": "done", "kind": "checkbox", "label": ""},
    {"field": "name", "kind": "text", "label": "Item"},
]


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (tid, uid)


def _new_block_id() -> str:
    return f"blk_{uuid.uuid4().hex[:10]}"


def _allowed_data_keys(ws: dict[str, Any]) -> set[str] | None:
    """``None`` = full dashboard access; else top-level keys editable via granular share."""
    if ws.get("access_scope") != "granular":
        return None
    ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
    blocks = ul.get("blocks") if isinstance(ul.get("blocks"), builtins.list) else []
    keys: set[str] = set()
    for b in blocks:
        if not isinstance(b, dict):
            continue
        props = b.get("props")
        if isinstance(props, dict):
            dp = str(props.get("dataPath") or "").strip()
            if dp:
                keys.add(top_level_key(dp))
    return keys


def _can_write(ws: dict[str, Any]) -> bool:
    role = (ws.get("access_role") or "owner").strip().lower()
    if role == "viewer":
        return False
    if ws.get("access_scope") == "granular":
        return ws.get("granular_can_write") is True
    return role in ("owner", "co_owner", "editor")


def _truncate_for_read(obj: Any) -> Any:
    raw = json.dumps(obj, ensure_ascii=False, default=str)
    if len(raw) <= _MAX_READ_JSON:
        return obj
    return {
        "_truncated": True,
        "chars": len(raw),
        "hint": "Use narrower paths or kind-specific read tools; data too large for one response.",
    }


def _unique_data_path(prefix: str, blocks: list[Any], data: dict[str, Any]) -> str:
    used: set[str] = set()
    for b in blocks:
        if not isinstance(b, dict):
            continue
        props = b.get("props")
        if isinstance(props, dict):
            dp = str(props.get("dataPath") or "").strip()
            if dp:
                used.add(dp)
    for k in data:
        used.add(k)
    for _ in range(80):
        p = f"{prefix}_{uuid.uuid4().hex[:6]}"
        if p not in used:
            return p
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _default_data_for_block(block_type: str, data_path: str) -> dict[str, Any]:
    if block_type == "table":
        return {data_path: []}
    if block_type in ("markdown", "rich_markdown"):
        return {data_path: ""}
    if block_type == "gallery":
        return {data_path: []}
    if block_type == "hero":
        return {data_path: {"url": "", "caption": "", "headline": ""}}
    if block_type == "timeline":
        return {data_path: {"events": []}}
    if block_type == "stat":
        return {data_path: {"label": "KPI", "value": 0}}
    if block_type == "chart":
        return {
            data_path: {
                "chartType": "line",
                "labels": ["A", "B", "C"],
                "series": [{"label": "Serie 1", "data": [0, 0, 0]}],
            }
        }
    if block_type == "sparkline":
        return {data_path: {"values": [0, 0, 0, 0]}}
    if block_type == "kanban":
        return {
            data_path: {
                "columns": [
                    {"id": "todo", "title": "Todo", "cards": []},
                    {"id": "done", "title": "Done", "cards": []},
                ]
            }
        }
    if block_type == "embed":
        return {data_path: {"url": "", "title": ""}}
    return {}


def _make_block(
    block_type: str,
    data_path: str,
    y: int,
    *,
    grid: dict[str, Any] | None = None,
    props: dict[str, Any] | None = None,
) -> dict[str, Any]:
    g = grid if isinstance(grid, dict) else {}
    x = int(g.get("x", 0) or 0)
    wy = int(g.get("y", y) or y)
    w = int(g.get("w", 6) or 6)
    h = int(g.get("h", 6) or 6)
    x = max(0, min(11, x))
    wy = max(0, wy)
    w = max(1, min(12, w))
    h = max(2, min(40, h))
    if block_type == "hero":
        w, h = max(w, 4), max(h, 4)
        base_props: dict[str, Any] = {"dataPath": data_path, "title": "Hero"}
    elif block_type == "timeline":
        w, h = max(w, 4), max(h, 5)
        base_props = {"dataPath": data_path, "title": "Timeline"}
    elif block_type == "stat":
        w, h = max(w, 2), max(h, 3)
        base_props = {"dataPath": data_path, "title": "KPI"}
    elif block_type == "chart":
        w, h = max(w, 4), max(h, 6)
        base_props = {"dataPath": data_path, "title": "Chart"}
    elif block_type == "sparkline":
        w, h = max(w, 2), max(h, 3)
        base_props = {"dataPath": data_path, "title": "Sparkline"}
    elif block_type == "kanban":
        w, h = max(w, 6), max(h, 6)
        base_props = {"dataPath": data_path, "title": "Kanban"}
    elif block_type == "rich_markdown":
        w, h = max(w, 4), max(h, 6)
        base_props = {
            "dataPath": data_path,
            "title": "Rich Markdown",
            "placeholder": "Markdown…",
        }
    elif block_type == "embed":
        w, h = max(w, 4), max(h, 6)
        base_props = {"dataPath": data_path, "title": "Embed"}
    elif block_type == "table":
        base_props = {"dataPath": data_path, "columns": list(_DEFAULT_TABLE_COLUMNS)}
    elif block_type == "markdown":
        base_props = {"dataPath": data_path, "placeholder": "Notes"}
    else:
        base_props = {"dataPath": data_path, "title": "Photos"}
    if isinstance(props, dict):
        for k, v in props.items():
            if k in ("dataPath",):
                continue
            base_props[k] = v
    return {
        "id": _new_block_id(),
        "type": block_type,
        "grid": {"x": x, "y": wy, "w": w, "h": h},
        "props": base_props,
    }


def _clamp_grid(grid: dict[str, Any]) -> dict[str, int]:
    return {
        "x": max(0, min(11, int(grid.get("x", 0) or 0))),
        "y": max(0, int(grid.get("y", 0) or 0)),
        "w": max(1, min(12, int(grid.get("w", 6) or 6))),
        "h": max(2, min(40, int(grid.get("h", 6) or 6))),
    }


def _apply_layout_ops(
    ui_layout: dict[str, Any],
    data: dict[str, Any],
    ops: list[dict[str, Any]],
    *,
    allowed_block_ids: frozenset[str] | None,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    ul = deepcopy(ui_layout) if isinstance(ui_layout, dict) else {"version": 1, "blocks": []}
    dt = deepcopy(data) if isinstance(data, dict) else {}
    blocks = ul.get("blocks")
    if not isinstance(blocks, builtins.list):
        blocks = []
        ul["blocks"] = blocks
    ul["version"] = 1

    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            return ul, dt, f"ops[{i}] must be an object"
        kind = str(op.get("op") or "").strip().lower()
        if kind == "add_block":
            btype = str(op.get("type") or "").strip().lower()
            if btype not in _BLOCK_TYPES:
                return ul, dt, f"ops[{i}]: invalid type {btype!r}"
            if len(blocks) >= _MAX_BLOCKS:
                return ul, dt, f"ops[{i}]: max {_MAX_BLOCKS} blocks"
            prefix = _BLOCK_PREFIX.get(btype, "block")
            dp = str(op.get("data_path") or "").strip()
            if not dp:
                dp = _unique_data_path(prefix, blocks, dt)
            y = max((int(b.get("grid", {}).get("y", 0) or 0) + int(b.get("grid", {}).get("h", 0) or 0)) for b in blocks if isinstance(b, dict)) if blocks else 0
            nb = _make_block(
                btype,
                dp,
                y,
                grid=op.get("grid") if isinstance(op.get("grid"), dict) else None,
                props=op.get("props") if isinstance(op.get("props"), dict) else None,
            )
            blocks.append(nb)
            for k, v in _default_data_for_block(btype, dp).items():
                if k not in dt:
                    dt[k] = v
        elif kind == "remove_block":
            bid = str(op.get("block_id") or "").strip()
            if not bid:
                return ul, dt, f"ops[{i}]: block_id required"
            if allowed_block_ids is not None and bid not in allowed_block_ids:
                return ul, dt, f"ops[{i}]: block_id not in allowed blocks"
            blocks[:] = [b for b in blocks if isinstance(b, dict) and str(b.get("id") or "") != bid]
        elif kind == "set_grid":
            bid = str(op.get("block_id") or "").strip()
            grid = op.get("grid")
            if not bid or not isinstance(grid, dict):
                return ul, dt, f"ops[{i}]: block_id and grid object required"
            if allowed_block_ids is not None and bid not in allowed_block_ids:
                return ul, dt, f"ops[{i}]: block_id not in allowed blocks"
            found = False
            for b in blocks:
                if isinstance(b, dict) and str(b.get("id") or "") == bid:
                    b["grid"] = _clamp_grid(grid)
                    found = True
                    break
            if not found:
                return ul, dt, f"ops[{i}]: unknown block_id {bid!r}"
        elif kind == "set_props":
            bid = str(op.get("block_id") or "").strip()
            props = op.get("props")
            if not bid or not isinstance(props, dict):
                return ul, dt, f"ops[{i}]: block_id and props object required"
            if allowed_block_ids is not None and bid not in allowed_block_ids:
                return ul, dt, f"ops[{i}]: block_id not in allowed blocks"
            found = False
            for b in blocks:
                if isinstance(b, dict) and str(b.get("id") or "") == bid:
                    cur = b.get("props") if isinstance(b.get("props"), dict) else {}
                    merged = dict(cur)
                    for k, v in props.items():
                        if k == "dataPath":
                            continue
                        merged[k] = v
                    b["props"] = merged
                    found = True
                    break
            if not found:
                return ul, dt, f"ops[{i}]: unknown block_id {bid!r}"
        else:
            return ul, dt, f"ops[{i}]: unknown op {kind!r} (use add_block, remove_block, set_grid, set_props)"
    ul["blocks"] = blocks
    return ul, dt, None


def list(arguments: dict[str, Any]) -> str:
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    rows = dashboard_db.dashboard_list(uid, tid, limit=200)
    out = [
        {
            "id": str(r.get("id", "")),
            "kind": (r.get("kind") or "").strip(),
            "title": (r.get("title") or "").strip(),
            "access_role": (r.get("access_role") or "owner").strip(),
        }
        for r in rows
    ]
    return json.dumps({"ok": True, "dashboards": out}, ensure_ascii=False)


def read(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    wid, res_err = resolve_dashboard_id(uid, tid, arguments.get("dashboard_id"))
    if wid is None:
        return _err(res_err or "dashboard_id required")
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    include_layout = arguments.get("include_layout") is not False
    include_data = arguments.get("include_data") is not False
    body: dict[str, Any] = {
        "ok": True,
        "dashboard_id": str(wid),
        "kind": ws.get("kind") or "",
        "title": ws.get("title") or "",
        "access_role": ws.get("access_role") or "owner",
        "access_scope": ws.get("access_scope") or "full",
    }
    if include_layout:
        body["ui_layout"] = _truncate_for_read(ws.get("ui_layout") or {})
    if include_data:
        body["data"] = _truncate_for_read(ws.get("data") or {})
    blocks = (ws.get("ui_layout") or {}).get("blocks") if isinstance(ws.get("ui_layout"), dict) else []
    if isinstance(blocks, builtins.list):
        body["block_ids"] = [
            str(b.get("id") or "")
            for b in blocks
            if isinstance(b, dict) and str(b.get("id") or "").strip()
        ]
    return json.dumps(body, ensure_ascii=False)


def patch_data(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    wid, res_err = resolve_dashboard_id(uid, tid, arguments.get("dashboard_id"))
    if wid is None:
        return _err(res_err or "dashboard_id required")
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    if not _can_write(ws):
        return _err("read-only access — cannot patch data")
    patches = arguments.get("patches")
    if not isinstance(patches, builtins.list) or not patches:
        return _err("patches must be a non-empty array of {path, value}")
    if len(patches) > _MAX_PATCHES:
        return _err(f"at most {_MAX_PATCHES} patches per call")
    data = dict(ws.get("data") or {})
    allowed = _allowed_data_keys(ws)
    new_data, perr = apply_data_patches(data, patches, allowed_top_keys=allowed)
    if perr:
        return _err(perr)
    updated = dashboard_db.dashboard_update(uid, tid, wid, data=new_data)
    if updated is None:
        return _err("could not update dashboard (viewer or conflict)")
    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "patches_applied": len(patches),
        },
        ensure_ascii=False,
    )


def patch_layout(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    wid, res_err = resolve_dashboard_id(uid, tid, arguments.get("dashboard_id"))
    if wid is None:
        return _err(res_err or "dashboard_id required")
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    if not _can_write(ws):
        return _err("read-only access — cannot patch layout")
    if ws.get("access_scope") == "granular":
        return _err("granular block share cannot change layout — only data on shared blocks")
    ops = arguments.get("ops")
    if not isinstance(ops, builtins.list) or not ops:
        return _err("ops must be a non-empty array of layout operations")
    if len(ops) > _MAX_LAYOUT_OPS:
        return _err(f"at most {_MAX_LAYOUT_OPS} ops per call")
    ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {"version": 1, "blocks": []}
    data = dict(ws.get("data") or {})
    new_ul, new_data, lerr = _apply_layout_ops(ul, data, ops, allowed_block_ids=None)
    if lerr:
        return _err(lerr)
    updated = dashboard_db.dashboard_update(uid, tid, wid, ui_layout=new_ul, data=new_data)
    if updated is None:
        return _err("could not update dashboard (viewer or conflict)")
    blocks = new_ul.get("blocks") if isinstance(new_ul.get("blocks"), builtins.list) else []
    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "ops_applied": len(ops),
            "block_count": len(blocks),
            "block_ids": [
                str(b.get("id") or "")
                for b in blocks
                if isinstance(b, dict) and str(b.get("id") or "").strip()
            ],
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "list": list,
    "read": read,
    "patch_data": patch_data,
    "patch_layout": patch_layout,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list",
            "TOOL_DESCRIPTION": (
                "List dashboards the user can access (id, kind, title, access_role). "
                "Use when dashboard_id is unknown and [Dashboard context] is missing."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "TOOL_DESCRIPTION": (
                "Read one dashboard: kind, title, ui_layout, data JSON, block_ids. "
                "Omit dashboard_id only when the user has exactly one board. "
                "Prefer kind-specific read tools (ideas_read, pets_read) when kind matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "UUID; omit if unambiguous (single dashboard).",
                    },
                    "include_layout": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Include ui_layout (default true).",
                    },
                    "include_data": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Include data payload (default true).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_data",
            "TOOL_DESCRIPTION": (
                "Patch dashboard data by dotted paths (e.g. notes, tasks, chart labels). "
                "Each patch: {path, value}. Does not change layout. "
                "For ideas/pets/shopping_list prefer ideas_*, pets_*, shopping_list_* when available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "UUID; omit if unambiguous.",
                    },
                    "patches": {
                        "type": "array",
                        "TOOL_DESCRIPTION": "Objects with path (string) and value (any JSON)",
                        "items": {"type": "object"},
                    },
                },
                "required": ["patches"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_layout",
            "TOOL_DESCRIPTION": (
                "Change dashboard layout with guarded ops: add_block, remove_block, set_grid, set_props. "
                "add_block types: table, markdown, rich_markdown, gallery, hero, timeline, stat, chart, "
                "sparkline, kanban, embed. Initializes empty data for new blocks. "
                "Not for granular block-only shares."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "UUID; omit if unambiguous.",
                    },
                    "ops": {
                        "type": "array",
                        "TOOL_DESCRIPTION": (
                            "add_block: {op,type,data_path?,grid?,props?}; "
                            "remove_block: {op,block_id}; set_grid: {op,block_id,grid}; "
                            "set_props: {op,block_id,props}"
                        ),
                        "items": {"type": "object"},
                    },
                },
                "required": ["ops"],
            },
        },
    },
]
