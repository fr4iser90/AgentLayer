"""Import GitHub repositories into a projects dashboard."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.domain.workspace.workspace_common import list_workspaces_for_user, normalize_git_url
from apps.backend.infrastructure.workspace_service import (
    WorkspaceCreateError,
    create_project_workspace_for_user,
    slug_from_git_url,
)


def _normalize_remote(url: str) -> str:
    n = normalize_git_url(url)
    return (n or url or "").strip().rstrip("/").lower()


def _find_workspace_for_remote(user, remote: str) -> dict[str, Any] | None:
    target = _normalize_remote(remote)
    if not target:
        return None
    for ws in list_workspaces_for_user(user):
        gu = _normalize_remote(str(ws.get("git_url") or ""))
        if gu and gu == target:
            return ws
    return None


def _projects_data_path(dashboard: dict[str, Any]) -> str:
    ul = dashboard.get("ui_layout") if isinstance(dashboard.get("ui_layout"), dict) else {}
    blocks = ul.get("blocks") if isinstance(ul.get("blocks"), list) else []
    for b in blocks:
        if not isinstance(b, dict) or b.get("type") != "table":
            continue
        props = b.get("props") if isinstance(b.get("props"), dict) else {}
        if props.get("enableRunNow") is True:
            dp = str(props.get("dataPath") or "").strip()
            if dp:
                return dp
    return "projects"


def import_repos_into_projects_dashboard(
    user,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    repos: list[dict[str, Any]],
    create_workspaces: bool = False,
    skip_existing: bool = True,
    data_path: str | None = None,
) -> dict[str, Any]:
    row = dashboard_db.dashboard_get(user.id, tenant_id, dashboard_id)
    if not row:
        return {"ok": False, "error": "dashboard not found"}
    if str(row.get("kind") or "").strip().lower() != "projects":
        return {"ok": False, "error": "dashboard kind must be projects"}

    role = (row.get("access_role") or "owner").strip().lower()
    if role == "viewer":
        return {"ok": False, "error": "read-only access"}
    if row.get("access_scope") == "granular" and not row.get("granular_can_write"):
        return {"ok": False, "error": "granular share is read-only"}

    dp = (data_path or "").strip() or _projects_data_path(row)
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    projects = data.get(dp)
    if not isinstance(projects, list):
        projects = []

    existing_remotes = {
        _normalize_remote(str(p.get("remote_url") or ""))
        for p in projects
        if isinstance(p, dict) and str(p.get("remote_url") or "").strip()
    }

    added: list[dict[str, Any]] = []
    skipped: list[str] = []
    workspace_errors: list[dict[str, str]] = []

    for repo in repos:
        if not isinstance(repo, dict):
            continue
        full_name = str(repo.get("full_name") or "").strip()
        clone_url = str(repo.get("clone_url") or repo.get("remote_url") or "").strip()
        if not clone_url and full_name:
            clone_url = normalize_git_url(full_name) or ""
        if not clone_url:
            continue

        remote_key = _normalize_remote(clone_url)
        if skip_existing and remote_key in existing_remotes:
            skipped.append(full_name or clone_url)
            continue

        title = str(repo.get("name") or "").strip() or (full_name.split("/")[-1] if full_name else "")
        branch = str(repo.get("default_branch") or "main").strip() or "main"
        tags = str(repo.get("description") or "").strip()[:240]

        workspace_id = ""
        project_path = ""

        ws = _find_workspace_for_remote(user, clone_url)
        if ws:
            workspace_id = str(ws.get("id") or "")
            project_path = str(ws.get("path") or "")
        elif create_workspaces:
            base_name = slug_from_git_url(clone_url)
            name = base_name
            attempt = 0
            while attempt < 5:
                try:
                    created = create_project_workspace_for_user(
                        user,
                        name=name,
                        source="git",
                        git_url=clone_url,
                        git_branch=branch,
                    )
                    workspace_id = str(created.get("id") or "")
                    project_path = str(created.get("path") or "")
                    break
                except WorkspaceCreateError as e:
                    if "already exists" in e.message.lower() or "unique" in e.message.lower():
                        attempt += 1
                        name = f"{base_name}-{attempt}"
                        continue
                    if "quota" in e.message.lower():
                        workspace_errors.append(
                            {"repo": full_name or clone_url, "error": e.message}
                        )
                        break
                    workspace_errors.append({"repo": full_name or clone_url, "error": e.message})
                    break

        new_row: dict[str, Any] = {
            "id": f"r_{uuid.uuid4().hex[:12]}",
            "pinned": False,
            "title": title,
            "remote_url": clone_url,
            "project_path": project_path,
            "tags": tags,
            "workspace_id": workspace_id,
        }
        projects.append(new_row)
        added.append(new_row)
        existing_remotes.add(remote_key)

    if not added and not skipped and workspace_errors:
        return {
            "ok": False,
            "error": workspace_errors[0]["error"],
            "workspace_errors": workspace_errors,
        }

    new_data = {**data, dp: projects}
    updated = dashboard_db.dashboard_update(
        user.id,
        tenant_id,
        dashboard_id,
        data=new_data,
    )
    if not updated:
        return {"ok": False, "error": "could not save dashboard"}

    return {
        "ok": True,
        "added_count": len(added),
        "skipped_count": len(skipped),
        "added": added,
        "skipped": skipped,
        "workspace_errors": workspace_errors,
        "data_path": dp,
        "dashboard": updated,
    }


def link_project_row_workspace(
    user,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    project_row_id: str,
    workspace_id: str | None = None,
    workspace_name: str | None = None,
    create_workspace: bool = False,
) -> dict[str, Any]:
    """Set ``workspace_id`` / ``project_path`` on one projects table row."""
    from apps.backend.domain.workspace.workspace_common import find_workspace_by_name, list_workspaces_for_user
    from apps.backend.infrastructure.workspace_service import WorkspaceCreateError, create_project_workspace_for_user

    row = dashboard_db.dashboard_get(user.id, tenant_id, dashboard_id)
    if not row:
        return {"ok": False, "error": "dashboard not found"}
    if str(row.get("kind") or "").strip().lower() != "projects":
        return {"ok": False, "error": "dashboard kind must be projects"}

    role = (row.get("access_role") or "owner").strip().lower()
    if role == "viewer":
        return {"ok": False, "error": "read-only access"}
    if row.get("access_scope") == "granular" and not row.get("granular_can_write"):
        return {"ok": False, "error": "granular share is read-only"}

    pid = (project_row_id or "").strip()
    if not pid:
        return {"ok": False, "error": "project_row_id is required"}

    dp = _projects_data_path(row)
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    projects = data.get(dp)
    if not isinstance(projects, list):
        return {"ok": False, "error": f"no project rows at data.{dp}"}

    idx = next(
        (i for i, p in enumerate(projects) if isinstance(p, dict) and str(p.get("id") or "") == pid),
        -1,
    )
    if idx < 0:
        return {"ok": False, "error": f"project row not found: {pid}"}

    proj = dict(projects[idx])
    ws: dict[str, Any] | None = None

    wid = (workspace_id or "").strip()
    wname = (workspace_name or "").strip()
    if wid:
        for candidate in list_workspaces_for_user(user):
            if str(candidate.get("id") or "") == wid:
                ws = candidate
                break
        if ws is None:
            return {"ok": False, "error": f"workspace not found: {wid}"}
    elif wname:
        ws = find_workspace_by_name(list_workspaces_for_user(user), wname)
        if ws is None:
            return {"ok": False, "error": f"workspace not found by name: {wname}"}
    elif create_workspace:
        remote = str(proj.get("remote_url") or "").strip()
        if not remote:
            return {"ok": False, "error": "project row has no remote_url to clone"}
        branch = "main"
        base_name = slug_from_git_url(remote)
        name = base_name
        last_err = "git clone failed"
        for attempt in range(5):
            try:
                created = create_project_workspace_for_user(
                    user,
                    name=name,
                    source="git",
                    git_url=remote,
                    git_branch=branch,
                )
                ws = created
                break
            except WorkspaceCreateError as e:
                last_err = e.message
                if "already exists" in e.message.lower() or "unique" in e.message.lower():
                    name = f"{base_name}-{attempt + 1}"
                    continue
                return {"ok": False, "error": e.message}
        if ws is None:
            return {"ok": False, "error": last_err}
    else:
        return {
            "ok": False,
            "error": "pass workspace_id, workspace_name, or create_workspace=true",
        }

    proj["workspace_id"] = str(ws.get("id") or "")
    proj["project_path"] = str(ws.get("path") or "")
    projects[idx] = proj

    updated = dashboard_db.dashboard_update(
        user.id,
        tenant_id,
        dashboard_id,
        data={**data, dp: projects},
    )
    if not updated:
        return {"ok": False, "error": "could not save dashboard"}

    return {
        "ok": True,
        "dashboard_id": str(dashboard_id),
        "project_row_id": pid,
        "workspace_id": proj["workspace_id"],
        "project_path": proj["project_path"],
        "project": proj,
    }
