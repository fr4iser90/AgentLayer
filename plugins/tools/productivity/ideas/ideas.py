"""Agent tools for ``kind: ideas`` dashboards — list, read, add/patch idea rows, scratchpad."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.tool_dashboard_resolve import (
    resolve_dashboard_id_for_kind,
    dashboard_rows_for_kind,
)

__version__ = "1.0.0"
TOOL_ID = "ideas"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "ideas"
TOOL_LABEL = "Ideas & memos"
TOOL_DESCRIPTION = (
    "Read and update ideas dashboards (kind ideas): idea table (title, tags, status, snippet, pinned) "
    "and markdown scratchpad. dashboard_id is optional when the user has exactly one ideas board; "
    "if several exist, call ideas_dashboards or pass dashboard_id. Prefer [Dashboard context] when present. "
    "Stored JSON only — no web search unless you use other tools."
)
TOOL_TRIGGERS = (
    "idea",
    "ideas",
    "idee",
    "ideen",
    "memo",
    "memos",
    "notiz",
    "brainstorm",
    "scratchpad",
)
TOOL_CAPABILITIES = ("dashboard.ideas.read", "dashboard.ideas.write")

_MAX_IDEAS = 500
_MAX_BATCH = 30
_MAX_TITLE = 500
_MAX_TAGS = 500
_MAX_SNIPPET = 4000
_MAX_SCRATCHPAD = 120_000

_STATUS_OPTIONS = frozenset({"Neu", "Später", "In Arbeit", "Erledigt / Archiv"})


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (tid, uid)


def _ensure_ideas(ws: dict[str, Any]) -> str | None:
    if (ws.get("kind") or "").strip() != "ideas":
        return "dashboard is not an ideas kind"
    return None


def _clip(s: str, max_len: int) -> str:
    t = (s or "").strip()
    if len(t) > max_len:
        return t[:max_len]
    return t


def _normalize_status(raw: Any) -> str:
    s = str(raw or "").strip()
    if s in _STATUS_OPTIONS:
        return s
    return "Neu"


def _normalize_idea_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    title = _clip(str(entry.get("title") or ""), _MAX_TITLE)
    if not title:
        return None
    return {
        "id": f"r_{uuid.uuid4().hex[:12]}",
        "pinned": bool(entry.get("pinned", False)),
        "title": title,
        "tags": _clip(str(entry.get("tags") or ""), _MAX_TAGS),
        "status": _normalize_status(entry.get("status")),
        "snippet": _clip(str(entry.get("snippet") or ""), _MAX_SNIPPET),
    }


def ideas_dashboards(arguments: dict[str, Any]) -> str:
    """List ideas dashboards for the current user."""
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — ideas tools need an authenticated chat user.")
    tid, uid = ident
    rows = dashboard_rows_for_kind(uid, tid, "ideas")
    out = [{"id": str(r.get("id", "")), "title": (r.get("title") or "").strip()} for r in rows]
    return json.dumps({"ok": True, "dashboards": out}, ensure_ascii=False)


def ideas_read(arguments: dict[str, Any]) -> str:
    """Return ideas rows and scratchpad for one ideas dashboard."""
    ident = _identity()
    if ident is None:
        return _err("No user identity — ideas tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="ideas", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_ideas(ws)
    if bad:
        return _err(bad)

    data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
    ideas = data.get("ideas")
    if not isinstance(ideas, list):
        ideas = []
    scratch = data.get("scratchpad")
    if not isinstance(scratch, str):
        scratch = ""

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "title": ws.get("title") or "",
            "ideas": ideas,
            "scratchpad": scratch,
        },
        ensure_ascii=False,
    )


def ideas_add_rows(arguments: dict[str, Any]) -> str:
    """Append one or more idea rows (title required per row; optional tags, status, snippet, pinned)."""
    raw = arguments.get("rows")
    if not isinstance(raw, list) or not raw:
        return _err("rows must be a non-empty array of objects with title")

    ident = _identity()
    if ident is None:
        return _err("No user identity — ideas tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="ideas", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_ideas(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    cur_raw = data.get("ideas")
    cur: list[dict[str, Any]] = [dict(x) for x in cur_raw] if isinstance(cur_raw, list) else []
    if len(cur) >= _MAX_IDEAS:
        return _err(f"max {_MAX_IDEAS} ideas — archive or delete rows in the UI first")

    new_rows: list[dict[str, Any]] = []
    for entry in raw[:_MAX_BATCH]:
        if not isinstance(entry, dict):
            continue
        row = _normalize_idea_entry(entry)
        if row:
            new_rows.append(row)
    if not new_rows:
        return _err("no valid rows — each needs a non-empty title")

    if len(cur) + len(new_rows) > _MAX_IDEAS:
        return _err(f"would exceed {_MAX_IDEAS} ideas — add fewer rows")

    merged = cur + new_rows
    data["ideas"] = merged
    if "scratchpad" not in data or not isinstance(data.get("scratchpad"), str):
        data["scratchpad"] = ""

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "added": len(new_rows),
            "ideas_count": len(merged),
        },
        ensure_ascii=False,
    )


_IDEA_PATCH_FIELDS = ("title", "tags", "status", "snippet", "pinned")


def ideas_patch_idea(arguments: dict[str, Any]) -> str:
    """Merge fields into one idea row (by idea id or zero-based index)."""
    patch = arguments.get("patch")
    if not isinstance(patch, dict) or not patch:
        return _err("patch must be a non-empty object")

    idea_id = arguments.get("idea_id")
    idea_index = arguments.get("idea_index")

    ident = _identity()
    if ident is None:
        return _err("No user identity — ideas tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="ideas", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_ideas(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    ideas_raw = data.get("ideas")
    ideas: list[dict[str, Any]] = [dict(x) for x in ideas_raw] if isinstance(ideas_raw, list) else []

    idx: int | None = None
    if idea_id is not None and str(idea_id).strip():
        iid = str(idea_id).strip()
        for i, row in enumerate(ideas):
            if str(row.get("id", "")).strip() == iid:
                idx = i
                break
        if idx is None:
            return _err("idea_id not found")
    elif idea_index is not None:
        try:
            ix = int(idea_index)
        except (TypeError, ValueError):
            return _err("idea_index must be an integer")
        if ix < 0 or ix >= len(ideas):
            return _err("idea_index out of range")
        idx = ix
    else:
        return _err("provide idea_id or idea_index")

    row = dict(ideas[idx])
    allowed = {k: patch[k] for k in _IDEA_PATCH_FIELDS if k in patch}
    if not allowed:
        return _err(f"patch must include at least one of: {', '.join(_IDEA_PATCH_FIELDS)}")

    for k, v in allowed.items():
        if k == "pinned":
            row["pinned"] = bool(v)
        elif k == "status":
            row["status"] = _normalize_status(v)
        elif k == "title":
            t = _clip(str(v or ""), _MAX_TITLE)
            if not t:
                return _err("title cannot be empty")
            row["title"] = t
        elif k == "tags":
            row["tags"] = _clip(str(v or ""), _MAX_TAGS)
        elif k == "snippet":
            row["snippet"] = _clip(str(v or ""), _MAX_SNIPPET)

    ideas[idx] = row
    data["ideas"] = ideas

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {"ok": True, "dashboard_id": str(wid), "idea_index": idx, "idea_id": str(row.get("id", ""))},
        ensure_ascii=False,
    )


def ideas_patch_scratchpad(arguments: dict[str, Any]) -> str:
    """Replace or append the markdown scratchpad (data.scratchpad)."""
    mode = str(arguments.get("mode") or "replace").strip().lower()
    if mode not in ("replace", "append"):
        return _err("mode must be replace or append")

    text = str(arguments.get("text") or "")
    if mode == "replace" and not text.strip():
        return _err("text must be non-empty for mode=replace")

    ident = _identity()
    if ident is None:
        return _err("No user identity — ideas tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="ideas", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_ideas(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    cur = data.get("scratchpad")
    if not isinstance(cur, str):
        cur = ""
    chunk = _clip(text, _MAX_SCRATCHPAD)
    if mode == "append":
        combined = _clip((cur + ("\n\n" if cur and chunk else "") + chunk).strip(), _MAX_SCRATCHPAD)
        data["scratchpad"] = combined
    else:
        data["scratchpad"] = chunk

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {"ok": True, "dashboard_id": str(wid), "scratchpad_chars": len(data["scratchpad"])},
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "ideas_dashboards": ideas_dashboards,
    "ideas_read": ideas_read,
    "ideas_add_rows": ideas_add_rows,
    "ideas_patch_idea": ideas_patch_idea,
    "ideas_patch_scratchpad": ideas_patch_scratchpad,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "ideas_dashboards",
            "TOOL_DESCRIPTION": (
                "List ideas dashboards (kind ideas). Call when which board is unclear or there is no "
                "[Dashboard context] dashboard_id."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ideas_read",
            "TOOL_DESCRIPTION": (
                "Read idea rows and scratchpad markdown for one ideas dashboard. "
                "Omit dashboard_id when the user has exactly one ideas board; else pass UUID or call ideas_dashboards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single ideas dashboard).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ideas_add_rows",
            "TOOL_DESCRIPTION": (
                "Add one or more ideas / memos (ideas dashboard — not the task-list dashboard). "
                "Each row needs title; optional tags, status "
                "(Neu | Später | In Arbeit | Erledigt / Archiv), snippet, pinned. "
                "Omit dashboard_id when the user has exactly one ideas dashboard. "
                "For checkbox tasks / due dates use todo_* tools (kind todo), not this. "
                "You MUST call this function with tool_calls — do not paste JSON or {\"rows\":[...]} as plain assistant text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single ideas dashboard).",
                    },
                    "rows": {
                        "type": "array",
                        "TOOL_DESCRIPTION": "Objects with title (required); optional tags, status, snippet, pinned",
                        "items": {"type": "object"},
                    },
                },
                "required": ["rows"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ideas_patch_idea",
            "TOOL_DESCRIPTION": (
                "Update one idea: title, tags, status, snippet, and/or pinned. "
                "Identify by idea_id (row id) or idea_index (0-based). "
                "Omit dashboard_id when the user has exactly one ideas dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single ideas dashboard).",
                    },
                    "idea_id": {"type": "string", "TOOL_DESCRIPTION": "Row id from ideas[].id"},
                    "idea_index": {"type": "integer", "TOOL_DESCRIPTION": "Zero-based index if id unknown"},
                    "patch": {"type": "object", "TOOL_DESCRIPTION": "Subset of title, tags, status, snippet, pinned"},
                },
                "required": ["patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ideas_patch_scratchpad",
            "TOOL_DESCRIPTION": (
                "Set (replace) or append the markdown scratchpad. "
                "Omit dashboard_id when the user has exactly one ideas dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single ideas dashboard).",
                    },
                    "mode": {"type": "string", "TOOL_DESCRIPTION": "replace or append"},
                    "text": {"type": "string", "TOOL_DESCRIPTION": "Markdown text"},
                },
                "required": ["mode", "text"],
            },
        },
    },
]
