"""Shared helpers for workspace management tools."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api
from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

_GITHUB_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


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


def list_workspaces_for_user(user) -> list[dict[str, Any]]:
    from apps.backend.infrastructure.workspace_service import ensure_workspace

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + WORKSPACE_SELECT_SQL + """
                FROM project_workspaces
                WHERE owner_user_id = %s
                ORDER BY name ASC
                """,
                (user.id,),
            )
            rows = cur.fetchall()

    out = [workspace_row_to_api(r) for r in rows]
    if not self_editing_allowed(user):
        out = [w for w in out if (w.get("name") or "").strip() != AGENTLAYER_SELF_NAME]

    if self_editing_allowed(user):
        self_ws = ensure_workspace("__agentlayer_self__", user)
        if self_ws and self_ws.get("id"):
            sid = str(self_ws["id"])
            if not any(str(w.get("id")) == sid for w in out):
                out.insert(
                    0,
                    {
                        "id": sid,
                        "name": self_ws.get("name") or AGENTLAYER_SELF_NAME,
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
    from apps.backend.infrastructure.conversations_db import conversation_replace

    updated = conversation_replace(
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
