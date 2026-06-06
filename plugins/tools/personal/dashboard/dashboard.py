"""Generic dashboard tools: list, read, patch data paths, patch layout (guarded ops)."""

from __future__ import annotations

import builtins
import json
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard import public_share
from apps.backend.dashboard.bundle import bundles_by_kind
from apps.backend.dashboard.create_helpers import (
    create_dashboard_payload,
    default_title_for_kind,
    validate_create_kind,
)
from apps.backend.dashboard.data_paths import apply_data_patches, top_level_key
from apps.backend.dashboard.tool_dashboard_resolve import resolve_dashboard_id
from apps.backend.dashboard.layout_tree import (
    count_layout_blocks,
    data_paths_from_blocks,
    resolve_blocks_target,
)
from apps.backend.dashboard.pins import pin_block_to_dashboard
from apps.backend.dashboard.projects_kpi import (
    patches_touch_projects_list,
    projects_data_path,
    sync_projects_kpis_in_data,
)
from apps.backend.dashboard.template_ops import export_template_payload, validate_template_import
from apps.backend.domain.identity import get_identity

__version__ = "1.0.0"
TOOL_ID = "dashboard"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "dashboard"
TOOL_LABEL = "Dashboards (generic)"
TOOL_DESCRIPTION = (
    "List dashboards, create boards for any catalog kind, read ui_layout + data, patch block data by path, "
    "adjust layout (add/remove blocks, grid, props), and create public read-only share links. "
    "Works for any kind; prefer kind-specific tools (ideas_*, pets_*, shopping_list_*, projects_*) "
    "for data updates when available. Use dashboard_id from [Dashboard context] when the user has the board open."
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
_MAX_BLOCKS = 64
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
    "section",
    "schedules",
    "card_grid",
    "dashboard_ref",
    "share_widget",
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
    "section": "section",
    "schedules": "schedules",
    "card_grid": "cards",
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
    for dp in data_paths_from_blocks(blocks):
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
    if block_type == "section":
        return {}
    if block_type == "schedules":
        return {}
    if block_type == "card_grid":
        return {data_path: []}
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
    elif block_type == "section":
        w, h = max(w, 4), max(h, 5)
        base_props = {
            "title": "Section",
            "nested": {"version": 2, "blocks": []},
            "collapsed": False,
        }
    elif block_type == "schedules":
        w, h = max(w, 4), max(h, 4)
        base_props = {"scope": "dashboard", "executionTarget": "all"}
    elif block_type == "card_grid":
        w, h = max(w, 4), max(h, 5)
        base_props = {
            "dataPath": data_path,
            "title": "Projects",
            "gridColumns": 3,
            "cardFields": ["title", "remote_url", "tags", "status", "security"],
            "enableSearch": True,
            "enableRowDetail": True,
            "enableRunNow": False,
            "enableWorkspaceLink": True,
        }
    elif block_type == "dashboard_ref":
        w, h = max(w, 4), max(h, 5)
        base_props = {
            "title": "Linked block",
            "sourceDashboardId": "",
            "sourceBlockId": "",
            "sourceLabel": "",
        }
    elif block_type == "share_widget":
        w, h = max(w, 4), max(h, 4)
        base_props = {
            "title": "Friend share",
            "resourceType": "google_calendar",
            "friendUserId": "",
            "friendDisplayName": "",
            "daysAhead": 7,
        }
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


def _all_data_paths_in_layout(ui_layout: dict[str, Any]) -> set[str]:
    blocks = ui_layout.get("blocks") if isinstance(ui_layout.get("blocks"), builtins.list) else []
    return set(data_paths_from_blocks(blocks))


def _unique_data_path_in_layout(
    prefix: str, ui_layout: dict[str, Any], data: dict[str, Any]
) -> str:
    used = _all_data_paths_in_layout(ui_layout)
    for k in data:
        used.add(k)
    for _ in range(80):
        p = f"{prefix}_{uuid.uuid4().hex[:6]}"
        if p not in used:
            return p
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _remove_block_from_layout(ui_layout: dict[str, Any], block_id: str) -> bool:
    bid = block_id.strip()
    blocks = ui_layout.get("blocks")
    if not isinstance(blocks, builtins.list):
        return False
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if str(b.get("type") or "").strip().lower() == "section":
            props = b.get("props") if isinstance(b.get("props"), dict) else {}
            nested = props.get("nested") if isinstance(props.get("nested"), dict) else {}
            nested_blocks = nested.get("blocks")
            if isinstance(nested_blocks, builtins.list):
                before = len(nested_blocks)
                nested_blocks[:] = [
                    x
                    for x in nested_blocks
                    if not (isinstance(x, dict) and str(x.get("id") or "").strip() == bid)
                ]
                if len(nested_blocks) < before:
                    return True
    before_root = len(blocks)
    blocks[:] = [
        b for b in blocks if not (isinstance(b, dict) and str(b.get("id") or "").strip() == bid)
    ]
    return len(blocks) < before_root


def _find_block_in_layout(ui_layout: dict[str, Any], block_id: str) -> dict[str, Any] | None:
    bid = block_id.strip()
    blocks = ui_layout.get("blocks")
    if not isinstance(blocks, builtins.list):
        return None
    for b in blocks:
        if isinstance(b, dict) and str(b.get("id") or "").strip() == bid:
            return b
        if isinstance(b, dict) and str(b.get("type") or "").strip().lower() == "section":
            props = b.get("props") if isinstance(b.get("props"), dict) else {}
            nested = props.get("nested") if isinstance(props.get("nested"), dict) else {}
            for nb in nested.get("blocks") or []:
                if isinstance(nb, dict) and str(nb.get("id") or "").strip() == bid:
                    return nb
    return None


def _sync_layout_version(ui_layout: dict[str, Any]) -> None:
    blocks = ui_layout.get("blocks") if isinstance(ui_layout.get("blocks"), builtins.list) else []
    for b in blocks:
        if isinstance(b, dict) and str(b.get("type") or "").strip().lower() == "section":
            ui_layout["version"] = 2
            return
    if int(ui_layout.get("version") or 1) == 2:
        ui_layout["version"] = 2
    else:
        ui_layout["version"] = 1


def _apply_layout_ops(
    ui_layout: dict[str, Any],
    data: dict[str, Any],
    ops: list[dict[str, Any]],
    *,
    allowed_block_ids: frozenset[str] | None,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    ul = deepcopy(ui_layout) if isinstance(ui_layout, dict) else {"version": 1, "blocks": []}
    dt = deepcopy(data) if isinstance(data, dict) else {}
    if not isinstance(ul.get("blocks"), builtins.list):
        ul["blocks"] = []

    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            return ul, dt, f"ops[{i}] must be an object"
        kind = str(op.get("op") or "").strip().lower()
        parent_raw = str(op.get("parent_block_id") or "").strip()
        parent_block_id = parent_raw or None

        if kind == "add_block":
            btype = str(op.get("type") or "").strip().lower()
            if btype not in _BLOCK_TYPES:
                return ul, dt, f"ops[{i}]: invalid type {btype!r}"
            if btype == "section" and parent_block_id:
                return ul, dt, f"ops[{i}]: cannot nest section inside section"
            if count_layout_blocks(ul) >= _MAX_BLOCKS:
                return ul, dt, f"ops[{i}]: max {_MAX_BLOCKS} blocks (including nested)"
            target_blocks, terr = resolve_blocks_target(ul, parent_block_id)
            if terr:
                return ul, dt, f"ops[{i}]: {terr}"
            assert target_blocks is not None
            prefix = _BLOCK_PREFIX.get(btype, "block")
            dp = str(op.get("data_path") or "").strip()
            if btype in ("section", "schedules", "dashboard_ref", "share_widget"):
                dp = ""
            elif not dp:
                dp = _unique_data_path_in_layout(prefix, ul, dt)
            y = (
                max(
                    (
                        int(b.get("grid", {}).get("y", 0) or 0)
                        + int(b.get("grid", {}).get("h", 0) or 0)
                    )
                    for b in target_blocks
                    if isinstance(b, dict)
                )
                if target_blocks
                else 0
            )
            nb = _make_block(
                btype,
                dp,
                y,
                grid=op.get("grid") if isinstance(op.get("grid"), dict) else None,
                props=op.get("props") if isinstance(op.get("props"), dict) else None,
            )
            target_blocks.append(nb)
            for k, v in _default_data_for_block(btype, dp or prefix).items():
                if k not in dt:
                    dt[k] = v
        elif kind == "remove_block":
            bid = str(op.get("block_id") or "").strip()
            if not bid:
                return ul, dt, f"ops[{i}]: block_id required"
            if allowed_block_ids is not None and bid not in allowed_block_ids:
                return ul, dt, f"ops[{i}]: block_id not in allowed blocks"
            if not _remove_block_from_layout(ul, bid):
                return ul, dt, f"ops[{i}]: unknown block_id {bid!r}"
        elif kind == "set_grid":
            bid = str(op.get("block_id") or "").strip()
            grid = op.get("grid")
            if not bid or not isinstance(grid, dict):
                return ul, dt, f"ops[{i}]: block_id and grid object required"
            if allowed_block_ids is not None and bid not in allowed_block_ids:
                return ul, dt, f"ops[{i}]: block_id not in allowed blocks"
            found = _find_block_in_layout(ul, bid)
            if not found:
                return ul, dt, f"ops[{i}]: unknown block_id {bid!r}"
            found["grid"] = _clamp_grid(grid)
        elif kind == "set_props":
            bid = str(op.get("block_id") or "").strip()
            props = op.get("props")
            if not bid or not isinstance(props, dict):
                return ul, dt, f"ops[{i}]: block_id and props object required"
            if allowed_block_ids is not None and bid not in allowed_block_ids:
                return ul, dt, f"ops[{i}]: block_id not in allowed blocks"
            found = _find_block_in_layout(ul, bid)
            if not found:
                return ul, dt, f"ops[{i}]: unknown block_id {bid!r}"
            cur = found.get("props") if isinstance(found.get("props"), dict) else {}
            merged = dict(cur)
            for k, v in props.items():
                if k == "dataPath":
                    continue
                merged[k] = v
            found["props"] = merged
        else:
            return ul, dt, f"ops[{i}]: unknown op {kind!r} (use add_block, remove_block, set_grid, set_props)"
    _sync_layout_version(ul)
    return ul, dt, None


def _kinds_hint() -> str:
    return ", ".join(sorted(bundles_by_kind().keys()))


def create_dashboard(arguments: dict[str, Any]) -> str:
    """Create or reuse a dashboard for any catalog kind; returns onboarding when available."""
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident

    kind = str(arguments.get("kind") or "").strip().lower()
    kerr = validate_create_kind(kind)
    if kerr:
        return _err(kerr)

    payload = create_dashboard_payload(
        uid,
        tid,
        kind=kind,
        default_title=default_title_for_kind(kind),
        arguments=arguments,
    )
    if payload is None:
        return _err(
            f"Multiple {kind} dashboards exist — pass dashboard_id or set only_if_none=false with an explicit title."
        )
    return json.dumps(payload, ensure_ascii=False)


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
    if (ws.get("kind") or "").strip().lower() == "projects":
        dp = projects_data_path(ws)
        if patches_touch_projects_list(patches, dp):
            new_data = sync_projects_kpis_in_data(new_data, dp)
    updated = dashboard_db.dashboard_update(uid, tid, wid, data=new_data)
    if updated is None:
        return _err("could not update dashboard (viewer or conflict)")
    from apps.backend.infrastructure.notifications_service import notify_dashboard_agent_update

    notify_dashboard_agent_update(
        tenant_id=tid,
        user_id=uid,
        dashboard_id=wid,
        dashboard_title=str(ws.get("title") or ""),
        patches=patches,
        ui_layout=ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None,
    )
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


def create_public_share(arguments: dict[str, Any]) -> str:
    """Create a public read-only link (optional block scope, expiry, password). Owner/co-owner only."""
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    wid, res_err = resolve_dashboard_id(uid, tid, arguments.get("dashboard_id"))
    if wid is None:
        return _err(res_err or "dashboard_id required")

    block_ids_raw = arguments.get("block_ids")
    block_ids: list[str] = []
    if isinstance(block_ids_raw, builtins.list):
        block_ids = [str(x).strip() for x in block_ids_raw if str(x).strip()]

    label = str(arguments.get("label") or "").strip()[:200]
    password_raw = arguments.get("password")
    pw = str(password_raw).strip() if password_raw is not None else ""

    expires_at = None
    raw_exp = arguments.get("expires_at")
    if raw_exp is not None and str(raw_exp).strip():
        try:
            expires_at = datetime.fromisoformat(str(raw_exp).strip().replace("Z", "+00:00"))
        except ValueError:
            return _err("expires_at must be ISO-8601 datetime")

    created = public_share.public_share_create(
        uid,
        tid,
        wid,
        block_ids=block_ids,
        label=label,
        expires_at=expires_at,
        password=pw or None,
    )
    if created is None:
        return _err(
            "could not create public share (need owner/co-owner, valid block_ids, password min 4 chars if set)"
        )
    raw_token, meta = created
    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "share": meta,
            "token": raw_token,
            "url_path": f"/app/dashboard/shared?t={raw_token}",
            "hint": "Give the user url_path once; the token is not stored and cannot be retrieved later.",
        },
        ensure_ascii=False,
    )


def export_template(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    wid, res_err = resolve_dashboard_id(uid, tid, arguments)
    if wid is None:
        return _err(res_err or "dashboard_id required")
    row = dashboard_db.dashboard_get(uid, tid, wid)
    if not row:
        return _err("dashboard not found")
    payload = export_template_payload(
        kind=str(row.get("kind") or "custom"),
        title=str(row.get("title") or ""),
        ui_layout=row.get("ui_layout") if isinstance(row.get("ui_layout"), dict) else {},
        data=row.get("data") if isinstance(row.get("data"), dict) else {},
    )
    return json.dumps({"ok": True, "template": payload, "dashboard_id": str(wid)}, ensure_ascii=False)


def import_layout(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    kind = str(arguments.get("kind") or "custom").strip().lower()
    title = str(arguments.get("title") or "Dashboard").strip()[:500]
    ul = arguments.get("ui_layout")
    if not isinstance(ul, dict):
        return _err("ui_layout object is required")
    initial = arguments.get("initial_data")
    if initial is None:
        initial = arguments.get("data")
    ul_clean, dt_clean, err = validate_template_import(kind=kind, ui_layout=ul, data=initial)
    if err:
        return _err(err)
    row = dashboard_db.dashboard_create(
        uid, tid, kind=kind, title=title, ui_layout=ul_clean, data=dt_clean
    )
    return json.dumps({"ok": True, "dashboard": row}, ensure_ascii=False, default=str)


def pin_block(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — dashboard tools need an authenticated chat user.")
    tid, uid = ident
    target_raw = arguments.get("target_dashboard_id") or arguments.get("dashboard_id")
    source_raw = arguments.get("source_dashboard_id")
    block_id = str(arguments.get("source_block_id") or "").strip()
    if not target_raw or not source_raw or not block_id:
        return _err("target_dashboard_id, source_dashboard_id, and source_block_id are required")
    try:
        target_id = uuid.UUID(str(target_raw).strip())
        source_id = uuid.UUID(str(source_raw).strip())
    except ValueError:
        return _err("invalid dashboard uuid")
    parent = str(arguments.get("parent_block_id") or "").strip() or None
    title = str(arguments.get("title") or "").strip() or None
    result = pin_block_to_dashboard(
        uid,
        tid,
        target_id,
        source_dashboard_id=source_id,
        source_block_id=block_id,
        parent_block_id=parent,
        title=title,
    )
    if not result:
        return _err("could not pin block (edit access on target, read access on source)")
    return json.dumps(result, ensure_ascii=False, default=str)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "create_dashboard": create_dashboard,
    "list": list,
    "read": read,
    "patch_data": patch_data,
    "patch_layout": patch_layout,
    "create_public_share": create_public_share,
    "export_template": export_template,
    "import_layout": import_layout,
    "pin_block": pin_block,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_dashboard",
            "TOOL_DESCRIPTION": (
                "Create or reuse a dashboard for any catalog kind — the only create tool (no pets_create_dashboard etc.). "
                "Pass kind (required). When only_if_none=true (default), reuse the sole existing board of that kind. "
                "Response may include onboarding (greeting, agent_prompt, steps, suggested_tools) and setup_hint — "
                "when present, run the setup conversation from that payload: greet, offer steps one at a time, "
                "use the suggested kind-specific tools for data, do not install schema (install-templates is operator UI only). "
                f"Catalog kinds: {_kinds_hint()}, custom."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Dashboard kind (required), e.g. pets, projects, ideas, shopping_list, "
                            "todo, feeds, friends, photo_album, personal_dashboard, custom"
                        ),
                    },
                    "title": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Dashboard title; default is the catalog label for the kind",
                    },
                    "only_if_none": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Reuse existing board when user has exactly one of that kind (default true)",
                    },
                },
                "required": ["kind"],
            },
        },
    },
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
                "sparkline, kanban, embed, section, schedules, card_grid, dashboard_ref, share_widget. Optional parent_block_id on add_block "
                "to place inside a section (not section-in-section). Initializes empty data for new blocks. "
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
                            "add_block: {op,type,data_path?,parent_block_id?,grid?,props?} — "
                            "parent_block_id = section block id for nested blocks; "
                            "remove_block: {op,block_id}; set_grid: {op,block_id,grid}; "
                            "set_props: {op,block_id,props}. "
                            "card_grid: use data_path matching list in data (e.g. projects). "
                            "section: props.nested.blocks holds inner layout after adds."
                        ),
                        "items": {"type": "object"},
                    },
                },
                "required": ["ops"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_public_share",
            "TOOL_DESCRIPTION": (
                "Create a public read-only share link for a dashboard (no login required). "
                "Empty block_ids = entire board; otherwise only listed layout block ids (e.g. gallery blocks). "
                "Optional ISO expires_at and password (min 4 chars). Returns token and url_path once — owner/co-owner only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "UUID; omit if unambiguous (single dashboard).",
                    },
                    "block_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "TOOL_DESCRIPTION": "Layout block ids to expose; empty = full dashboard",
                    },
                    "label": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional label for the owner (e.g. dog album for friends)",
                    },
                    "expires_at": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional ISO-8601 expiry datetime",
                    },
                    "password": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional link password (min 4 characters)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_template",
            "TOOL_DESCRIPTION": (
                "Export a dashboard layout + data snapshot (kind, ui_layout, initial_data) for copying to another board."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string", "TOOL_DESCRIPTION": "Source dashboard UUID"},
                },
                "required": ["dashboard_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_layout",
            "TOOL_DESCRIPTION": (
                "Create a new dashboard from a layout snapshot (copy, not live sync). "
                "Pass kind, title, ui_layout, and optional initial_data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "TOOL_DESCRIPTION": "Usually custom or a catalog kind"},
                    "title": {"type": "string"},
                    "ui_layout": {"type": "object"},
                    "initial_data": {"type": "object"},
                },
                "required": ["ui_layout"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pin_block",
            "TOOL_DESCRIPTION": (
                "Pin a block from another dashboard onto a target board as a live dashboard_ref. "
                "Requires edit on target and read on source block."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_dashboard_id": {"type": "string"},
                    "source_dashboard_id": {"type": "string"},
                    "source_block_id": {"type": "string"},
                    "parent_block_id": {"type": "string", "TOOL_DESCRIPTION": "Optional section id on target"},
                    "title": {"type": "string"},
                },
                "required": ["target_dashboard_id", "source_dashboard_id", "source_block_id"],
            },
        },
    },
]
