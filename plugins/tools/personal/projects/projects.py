"""Agent tools for ``kind: projects`` dashboards — create, read, GitHub import, workspace link."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.projects_import import (
    import_repos_into_projects_dashboard,
    link_project_row_workspace,
)
from apps.backend.dashboard.tool_dashboard_resolve import (
    dashboard_rows_for_kind,
    resolve_dashboard_id_for_kind,
)
from apps.backend.domain.github.repos import list_user_repos
from apps.backend.domain.identity import get_identity
from apps.backend.domain.workspace.workspace_common import normalize_git_url
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "projects"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "projects"
TOOL_LABEL = "Projects portfolio"
TOOL_DESCRIPTION = (
    "Create and manage projects dashboards (kind projects): portfolio table (title, remote_url, "
    "project_path, tags, workspace_id), GitHub repo import, and link rows to coding workspaces. "
    "dashboard_id is optional when the user has exactly one projects board; call projects_dashboards "
    "when ambiguous. Prefer [Dashboard context] when present. GitHub import uses the user's own "
    "github_pat secret (Settings → Connections)."
)
TOOL_TRIGGERS = (
    "project",
    "projects",
    "projekt",
    "projekte",
    "portfolio",
    "repos",
    "repositories",
    "github import",
    "import repos",
    "project dashboard",
)
TOOL_CAPABILITIES = ("dashboard.projects.read", "dashboard.projects.write")

_MAX_PROJECTS = 500
_MAX_BATCH = 40
_MAX_TITLE = 500
_MAX_REMOTE = 2048
_MAX_TAGS = 500
_MAX_IMPORT_REPOS = 200


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (tid, uid)


def _acting_user(uid: uuid.UUID) -> Any:
    class UserLike:
        def __init__(self, user_id: uuid.UUID) -> None:
            self.id = user_id
            self.role = "user"

    u = UserLike(uid)
    try:
        u.role = db.user_role(uid) or "user"
    except Exception:
        pass
    return u


def _ensure_projects(ws: dict[str, Any]) -> str | None:
    if (ws.get("kind") or "").strip().lower() != "projects":
        return "dashboard is not a projects kind"
    return None


def _can_write(ws: dict[str, Any]) -> bool:
    role = (ws.get("access_role") or "owner").strip().lower()
    if role == "viewer":
        return False
    if ws.get("access_scope") == "granular":
        return ws.get("granular_can_write") is True
    return role in ("owner", "co_owner", "editor")


def _clip(s: str, max_len: int) -> str:
    t = (s or "").strip()
    return t[:max_len] if len(t) > max_len else t


def _projects_list(ws: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
    dp = "projects"
    ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
    for b in ul.get("blocks") or []:
        if not isinstance(b, dict) or b.get("type") != "table":
            continue
        props = b.get("props") if isinstance(b.get("props"), dict) else {}
        if props.get("enableRunNow") is True:
            cand = str(props.get("dataPath") or "").strip()
            if cand:
                dp = cand
                break
    raw = data.get(dp)
    rows = list(raw) if isinstance(raw, list) else []
    out: list[dict[str, Any]] = [dict(x) for x in rows if isinstance(x, dict)]
    return dp, out


def _normalize_row(entry: dict[str, Any]) -> dict[str, Any] | None:
    title = _clip(str(entry.get("title") or ""), _MAX_TITLE)
    remote_raw = _clip(str(entry.get("remote_url") or entry.get("remote") or ""), _MAX_REMOTE)
    remote = normalize_git_url(remote_raw) or remote_raw
    if not title and not remote:
        return None
    if not title and remote:
        title = remote.rstrip("/").split("/")[-1].removesuffix(".git") or "Project"
    return {
        "id": f"r_{uuid.uuid4().hex[:12]}",
        "pinned": bool(entry.get("pinned", False)),
        "title": title,
        "remote_url": remote,
        "project_path": _clip(str(entry.get("project_path") or ""), _MAX_REMOTE),
        "tags": _clip(str(entry.get("tags") or ""), _MAX_TAGS),
        "workspace_id": _clip(str(entry.get("workspace_id") or ""), 64),
    }


def dashboards(arguments: dict[str, Any]) -> str:
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — projects tools need an authenticated chat user.")
    tid, uid = ident
    rows = dashboard_rows_for_kind(uid, tid, "projects")
    out = [{"id": str(r.get("id", "")), "title": (r.get("title") or "").strip()} for r in rows]
    return json.dumps({"ok": True, "dashboards": out}, ensure_ascii=False)


def read(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — projects tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="projects", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_projects(ws)
    if bad:
        return _err(bad)

    dp, projects = _projects_list(ws)
    slim = [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "remote_url": p.get("remote_url"),
            "project_path": p.get("project_path"),
            "tags": p.get("tags"),
            "workspace_id": p.get("workspace_id"),
            "pinned": p.get("pinned"),
        }
        for p in projects
    ]
    notes = ws.get("data", {}).get("notes") if isinstance(ws.get("data"), dict) else ""
    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "data_path": dp,
            "count": len(slim),
            "projects": slim,
            "notes": notes if isinstance(notes, str) else "",
        },
        ensure_ascii=False,
    )


def add_rows(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — projects tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="projects", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    if not _can_write(ws):
        return _err("read-only access")
    bad = _ensure_projects(ws)
    if bad:
        return _err(bad)

    raw_rows = arguments.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        return _err("rows must be a non-empty array")

    dp, projects = _projects_list(ws)
    if len(projects) + len(raw_rows) > _MAX_PROJECTS:
        return _err(f"at most {_MAX_PROJECTS} project rows per dashboard")

    added: list[dict[str, Any]] = []
    for entry in raw_rows[: _MAX_BATCH]:
        if not isinstance(entry, dict):
            continue
        norm = _normalize_row(entry)
        if norm:
            projects.append(norm)
            added.append(norm)

    if not added:
        return _err("no valid rows (need title or remote_url per row)")

    data = dict(ws.get("data") or {})
    data[dp] = projects
    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard")

    return json.dumps(
        {"ok": True, "dashboard_id": str(wid), "added_count": len(added), "added": added},
        ensure_ascii=False,
    )


def list_github_repos(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — projects tools need an authenticated chat user.")
    _tid, uid = ident

    page = int(arguments.get("page") or 1)
    per_page = int(arguments.get("per_page") or 100)
    repos, err = list_user_repos(uid, page=page, per_page=per_page)
    if err and not repos:
        return _err(err)
    slim = [
        {
            "full_name": r.get("full_name"),
            "name": r.get("name"),
            "clone_url": r.get("clone_url"),
            "default_branch": r.get("default_branch"),
            "description": r.get("description"),
            "private": r.get("private"),
        }
        for r in repos
    ]
    return json.dumps(
        {"ok": True, "repos": slim, "count": len(slim), "page": page, "warning": err},
        ensure_ascii=False,
    )


def import_github(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — projects tools need an authenticated chat user.")
    tid, uid = ident
    user = _acting_user(uid)

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="projects", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required — call create_dashboard with kind=projects first")

    create_workspaces = arguments.get("create_workspaces")
    if isinstance(create_workspaces, str):
        create_workspaces = create_workspaces.strip().lower() in ("1", "true", "yes", "on")
    else:
        create_workspaces = bool(create_workspaces)

    skip_existing = arguments.get("skip_existing")
    if skip_existing is None:
        skip_existing = True
    elif isinstance(skip_existing, str):
        skip_existing = skip_existing.strip().lower() in ("1", "true", "yes", "on")
    else:
        skip_existing = bool(skip_existing)

    repo_names_raw = arguments.get("repo_full_names")
    import_all = arguments.get("import_all")
    if isinstance(import_all, str):
        import_all = import_all.strip().lower() in ("1", "true", "yes", "on")
    else:
        import_all = bool(import_all)

    repos_to_import: list[dict[str, Any]] = []

    if isinstance(repo_names_raw, list) and repo_names_raw:
        names = {str(x).strip().lower() for x in repo_names_raw if str(x).strip()}
        if not names:
            return _err("repo_full_names must contain owner/repo strings")
        page = 1
        while page <= 5 and len(repos_to_import) < _MAX_IMPORT_REPOS:
            batch, err = list_user_repos(uid, page=page, per_page=100)
            if err and not batch:
                return _err(err)
            for r in batch:
                fn = str(r.get("full_name") or "").strip().lower()
                if fn in names:
                    repos_to_import.append(r)
            if len(batch) < 100:
                break
            page += 1
        missing = names - {str(r.get("full_name") or "").lower() for r in repos_to_import}
        if missing and not repos_to_import:
            return _err(f"no matching repos found for: {', '.join(sorted(missing))}")
    elif import_all:
        page = 1
        while page <= 5 and len(repos_to_import) < _MAX_IMPORT_REPOS:
            batch, err = list_user_repos(uid, page=page, per_page=100)
            if err and not batch:
                return _err(err)
            repos_to_import.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    else:
        return _err("pass repo_full_names (array) or import_all=true")

    if not repos_to_import:
        return _err("no repositories to import")

    repos_to_import = repos_to_import[:_MAX_IMPORT_REPOS]
    result = import_repos_into_projects_dashboard(
        user,
        tid,
        wid,
        repos=repos_to_import,
        create_workspaces=create_workspaces,
        skip_existing=skip_existing,
    )
    if not result.get("ok"):
        return _err(str(result.get("error") or "import failed"))

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "added_count": result.get("added_count", 0),
            "skipped_count": result.get("skipped_count", 0),
            "workspace_errors": result.get("workspace_errors") or [],
            "added": result.get("added") or [],
            "skipped": result.get("skipped") or [],
        },
        ensure_ascii=False,
    )


def link_workspace(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — projects tools need an authenticated chat user.")
    tid, uid = ident
    user = _acting_user(uid)

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="projects", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    project_row_id = str(arguments.get("project_row_id") or arguments.get("row_id") or "").strip()
    if not project_row_id:
        idx = arguments.get("project_index")
        if idx is not None:
            ws = dashboard_db.dashboard_get(uid, tid, wid)
            if ws is None:
                return _err("dashboard not found")
            _dp, projects = _projects_list(ws)
            try:
                project_row_id = str(projects[int(idx)].get("id") or "")
            except (IndexError, ValueError, TypeError):
                project_row_id = ""
        if not project_row_id:
            return _err("project_row_id or project_index is required")

    create_ws = arguments.get("create_workspace")
    if isinstance(create_ws, str):
        create_ws = create_ws.strip().lower() in ("1", "true", "yes", "on")
    else:
        create_ws = bool(create_ws)

    result = link_project_row_workspace(
        user,
        tid,
        wid,
        project_row_id=project_row_id,
        workspace_id=str(arguments.get("workspace_id") or "").strip() or None,
        workspace_name=str(arguments.get("workspace_name") or arguments.get("name") or "").strip() or None,
        create_workspace=create_ws,
    )
    if not result.get("ok"):
        return _err(str(result.get("error") or "link failed"))
    return json.dumps(result, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "dashboards": dashboards,
    "read": read,
    "add_rows": add_rows,
    "list_github_repos": list_github_repos,
    "import_github": import_github,
    "link_workspace": link_workspace,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "dashboards",
            "TOOL_DESCRIPTION": "List projects dashboards (kind projects).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "TOOL_DESCRIPTION": "Read project rows and notes from a projects dashboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single projects dashboard).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_rows",
            "TOOL_DESCRIPTION": (
                "Append project rows manually (title, remote_url, tags, optional workspace_id). "
                "For bulk GitHub import use import_github instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "rows": {
                        "type": "array",
                        "items": {"type": "object"},
                        "TOOL_DESCRIPTION": "Objects with title and/or remote_url; optional tags, pinned, workspace_id",
                    },
                },
                "required": ["rows"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_github_repos",
            "TOOL_DESCRIPTION": (
                "List GitHub repos visible to the user (requires github_pat in Settings → Connections). "
                "Use before import_github to pick repo_full_names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "TOOL_DESCRIPTION": "Page 1–5 (default 1)"},
                    "per_page": {"type": "integer", "TOOL_DESCRIPTION": "1–100 (default 100)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_github",
            "TOOL_DESCRIPTION": (
                "Import GitHub repos into the projects table. Pass repo_full_names or import_all=true. "
                "Optionally clone as coding workspaces (create_workspaces). Uses per-user github_pat only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "repo_full_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "TOOL_DESCRIPTION": 'e.g. ["owner/repo"]',
                    },
                    "import_all": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Import all visible repos (up to 500, paginated)",
                    },
                    "create_workspaces": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Clone each new repo as a coding workspace and link row",
                    },
                    "skip_existing": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Skip rows with same remote_url (default true)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_workspace",
            "TOOL_DESCRIPTION": (
                "Link a project row to a coding workspace by workspace_id or workspace_name, "
                "or clone remote_url (create_workspace=true)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "project_row_id": {"type": "string", "TOOL_DESCRIPTION": "Row id from projects[].id"},
                    "project_index": {"type": "integer", "TOOL_DESCRIPTION": "Alternative to project_row_id"},
                    "workspace_id": {"type": "string"},
                    "workspace_name": {"type": "string"},
                    "create_workspace": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Clone project row remote_url as new workspace",
                    },
                },
            },
        },
    },
]
