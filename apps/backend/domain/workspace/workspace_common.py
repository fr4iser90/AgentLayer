"""Shared helpers for workspace management tools."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Protocol

from apps.backend.domain.identity import get_identity

_GITHUB_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
AGENTLAYER_SELF_NAME = "agentlayer-self"


class WorkspaceCommonDependencies(Protocol):
    workspace_select_sql: str
    agentlayer_self_name: str

    def pool(self) -> Any: ...

    def user_role(self, user_id: uuid.UUID) -> str | None: ...

    def workspace_row_to_api(self, row: Any) -> dict[str, Any]: ...

    def self_editing_allowed(self, user: Any) -> bool: ...

    def ensure_workspace(self, workspace_id: str, user: Any) -> dict[str, Any] | None: ...

    def conversation_replace(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        title: str | None,
        mode: str | None,
        model: str | None,
        messages: list[dict[str, Any]] | None,
        agent_log: list[dict[str, Any]] | None,
        composer_prefs: dict[str, Any] | None,
    ) -> dict[str, Any] | None: ...


_deps: WorkspaceCommonDependencies | None = None


def register_workspace_common_dependencies(deps: WorkspaceCommonDependencies) -> None:
    global _deps
    _deps = deps


class _DbPort:
    def pool(self) -> Any:
        if _deps is None:
            raise RuntimeError("workspace common dependencies not registered")
        return _deps.pool()

    def user_role(self, user_id: uuid.UUID) -> str | None:
        if _deps is None:
            raise RuntimeError("workspace common dependencies not registered")
        return _deps.user_role(user_id)


db = _DbPort()


def _workspace_select_sql() -> str:
    if _deps is None:
        return "*"
    return _deps.workspace_select_sql


def _agentlayer_self_name() -> str:
    return _deps.agentlayer_self_name if _deps is not None else AGENTLAYER_SELF_NAME


def _workspace_row_to_api(row: Any) -> dict[str, Any]:
    if _deps is None:
        if isinstance(row, tuple):
            return {
                "id": row[0] if len(row) > 0 else None,
                "owner_user_id": row[1] if len(row) > 1 else None,
                "name": row[2] if len(row) > 2 else None,
                "path": row[3] if len(row) > 3 else None,
                "source": row[4] if len(row) > 4 else None,
                "git_url": row[5] if len(row) > 5 else None,
                "git_branch": row[6] if len(row) > 6 else None,
                "access_role": row[7] if len(row) > 7 else None,
            }
        return dict(row) if isinstance(row, dict) else {}
    return _deps.workspace_row_to_api(row)


def _self_editing_allowed(user: Any) -> bool:
    return bool(_deps and _deps.self_editing_allowed(user))


def _ensure_workspace(workspace_id: str, user: Any) -> dict[str, Any] | None:
    return _deps.ensure_workspace(workspace_id, user) if _deps is not None else None


def dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def user_from_context(context: dict[str, Any] | None) -> Any | None:
    if context:
        u = context.get("user")
        if u is not None and getattr(u, "id", None) is not None:
            return u
    _tid, uid = get_identity()
    if uid is None:
        return None

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


def normalize_git_url(raw: str) -> str | None:
    """Accept HTTPS URL or ``owner/repo`` (GitHub)."""
    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("https://") or s.startswith("http://"):
        return s.rstrip("/")
    if s.startswith("git@"):
        if ":" in s and "@" in s:
            host_path = s.split("@", 1)[1]
            host, path_part = host_path.split(":", 1)
            return f"https://{host}/{path_part.rstrip('/')}"
        return None
    slug = s.strip("/")
    if _GITHUB_SLUG_RE.match(slug):
        owner, repo = slug.split("/", 1)
        repo = repo.removesuffix(".git")
        return f"https://github.com/{owner}/{repo}.git"
    return None


def git_url_equivalence_key(url: str) -> str:
    """Canonical key for matching git remotes (https/http, with or without ``.git``)."""
    s = (url or "").strip().rstrip("/").lower()
    if s.endswith(".git"):
        s = s[:-4]
    return s


def find_owned_git_workspace(user, *, git_url: str) -> dict[str, Any] | None:
    """
    Existing git workspace for this owner and remote URL, or None.

    Never matches another user's row — query is scoped to ``owner_user_id``.
    """
    target = git_url_equivalence_key(git_url)
    if not target or user is None or getattr(user, "id", None) is None:
        return None
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + _workspace_select_sql() + """
                FROM project_workspaces
                WHERE owner_user_id = %s AND source = 'git' AND git_url IS NOT NULL
                ORDER BY updated_at DESC
                """,
                (user.id,),
            )
            rows = cur.fetchall()
    for row in rows:
        ws = _workspace_row_to_api(row)
        if git_url_equivalence_key(str(ws.get("git_url") or "")) == target:
            return ws
    return None


def list_workspaces_for_user(user) -> list[dict[str, Any]]:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + _workspace_select_sql() + """
                FROM project_workspaces
                WHERE owner_user_id = %s
                ORDER BY name ASC
                """,
                (user.id,),
            )
            rows = cur.fetchall()

    out = [_workspace_row_to_api(r) for r in rows]
    if not _self_editing_allowed(user):
        out = [w for w in out if (w.get("name") or "").strip() != _agentlayer_self_name()]

    if _self_editing_allowed(user):
        self_ws = _ensure_workspace("__agentlayer_self__", user)
        if self_ws and self_ws.get("id"):
            sid = str(self_ws["id"])
            if not any(str(w.get("id")) == sid for w in out):
                out.insert(
                    0,
                    {
                        "id": sid,
                        "name": self_ws.get("name") or _agentlayer_self_name(),
                        "path": self_ws.get("path"),
                        "source": self_ws.get("source") or "manual",
                        "git_url": self_ws.get("git_url"),
                        "git_branch": self_ws.get("git_branch") or "main",
                        "access_role": "owner",
                    },
                )
    return out


def find_workspace_by_name(workspaces: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    nm = (name or "").strip().lower()
    if not nm:
        return None
    for w in workspaces:
        if (w.get("name") or "").strip().lower() == nm:
            return w
    return None


def bind_workspace_in_context(
    context: dict[str, Any] | None,
    workspace: dict[str, Any],
) -> None:
    if not context or not isinstance(workspace, dict):
        return
    p = workspace.get("path")
    if isinstance(p, str) and p.strip():
        context["workspace"] = workspace
    wid = workspace.get("id")
    if wid:
        context["workspace_id"] = str(wid)


def persist_conversation_workspace(
    context: dict[str, Any] | None,
    workspace_id: str,
    user_id: uuid.UUID,
) -> bool:
    if not context:
        return False
    raw_cid = context.get("conversation_id")
    if not raw_cid:
        return False
    try:
        cid = raw_cid if isinstance(raw_cid, uuid.UUID) else uuid.UUID(str(raw_cid).strip())
        wid = uuid.UUID(str(workspace_id).strip())
    except (ValueError, TypeError):
        return False
    if _deps is None:
        return False
    updated = _deps.conversation_replace(
        user_id,
        cid,
        title=None,
        mode=None,
        model=None,
        messages=None,
        agent_log=None,
        composer_prefs={"workspace_id": str(wid)},
    )
    return updated is not None
