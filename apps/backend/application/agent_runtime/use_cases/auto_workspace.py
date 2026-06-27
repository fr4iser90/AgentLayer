"""Auto-bind or create workspaces for Git URLs in agent chat prompts."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from apps.backend.application.agent_runtime.dependencies import (
    WorkspaceCreateError,
    create_project_workspace_for_user,
    db,
    ensure_workspace,
    slug_from_git_url,
)
from apps.backend.application.agent_runtime.runtime.prompts import _AGENTS_AUTO_WORKSPACE_FROM_GIT_URL

logger = logging.getLogger(__name__)

_REPO_GIT_INTENT_RE = re.compile(
    r"\b(?:git\s+)?clone\b|\brep(?:ository|os?)\b|\bcodebase\b|\b(?:pull\s+request|pr)\b|"
    r"\bgit\s+init\b|\bgit\s+pull\b|\bgit\s+push\b|\bcommit(?:s)?\b|\bbranch\b|\bmerge\b|"
    r"\b(?:fork|star)\s+(?:this\s+)?(?:repo|repository)\b|\bgithub\.com/",
    re.IGNORECASE,
)


def user_defers_git_workspace_to_tool(text: str) -> bool:
    """Prompt assigns clone/create to workspace.create, so chat should not auto-clone/reuse."""
    low = (text or "").lower()
    return "workspace.create" in low and ("git_url" in low or "source=git" in low)


def extract_https_git_url(text: str) -> str | None:
    if not (text or "").strip():
        return None
    for m in re.finditer(r"https://[^\s\)\]\"'<>]+", text):
        u = m.group(0).rstrip(").,;]")
        low = u.lower()
        if low.endswith(".git"):
            return u
        for marker in (
            "github.com/",
            "gitlab.com/",
            "bitbucket.org/",
            "codeberg.org/",
        ):
            if marker in low:
                return u
        if "/git/" in low or ".git" in low:
            return u
    return None


def coding_repo_intent(text: str) -> bool:
    if extract_https_git_url(text):
        return True
    return bool(text and _REPO_GIT_INTENT_RE.search(text))


def is_elevated_admin(
    user_obj: Any,
    bearer_user_role: str | None,
    user_id: Any,
) -> bool:
    if (bearer_user_role or "").strip().lower() == "admin":
        return True
    if user_obj is not None and getattr(user_obj, "role", None) == "admin":
        return True
    if user_id:
        try:
            if db.user_role(user_id) == "admin":
                return True
        except Exception:
            pass
    return False


def try_auto_create_workspace_from_git_url(
    *,
    agent_id: str | None,
    user_id: Any,
    user_obj: Any,
    last_user_text: str,
    embedded_subagent: bool,
) -> dict[str, Any] | None:
    """
    Admin users: clone/bind a project workspace when the last user message contains a Git HTTPS URL.
    Used for ``coding`` and ``general`` chat (not embedded sub-agents).
    """
    aid = (agent_id or "general").strip() or "general"
    if aid not in _AGENTS_AUTO_WORKSPACE_FROM_GIT_URL:
        return None
    if embedded_subagent or not user_id:
        return None
    gu = extract_https_git_url(last_user_text)
    if not gu:
        return None
    if user_defers_git_workspace_to_tool(last_user_text):
        return None
    u = user_obj
    if u is None:

        class UserLike:
            def __init__(self, uid: Any):
                self.id = uid
                self.role = "user"

        u = UserLike(user_id)
        try:
            u.role = db.user_role(user_id) or "user"
        except Exception:
            pass
    if u is None or not is_elevated_admin(u, None, user_id):
        return None
    try:
        from apps.backend.domain.workspace.workspace_common import find_owned_git_workspace

        existing = find_owned_git_workspace(u, git_url=gu)
        if existing:
            wid = str(existing.get("id") or "").strip()
            if wid:
                workspace = ensure_workspace(wid, u)
                if workspace:
                    logger.info(
                        "chat_completion: reusing owned workspace %s for Git URL (agent=%s)",
                        wid,
                        aid,
                    )
                    return workspace

        nm = f"{slug_from_git_url(gu)}-{uuid.uuid4().hex[:8]}"
        created = create_project_workspace_for_user(
            u,
            name=nm,
            source="git",
            git_url=gu,
            git_branch="main",
        )
        wid = str(created["id"])
        workspace = ensure_workspace(wid, u)
        if workspace:
            logger.info(
                "chat_completion: auto-created workspace %s from Git URL (agent=%s)",
                wid,
                aid,
            )
            return workspace
    except WorkspaceCreateError as e:
        logger.warning("auto-create workspace failed: %s", e.message)
    except Exception as e:
        logger.warning("auto-create workspace failed: %s", e)
    return None
