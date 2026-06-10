"""List, create, and bind project workspaces for the signed-in user."""

from __future__ import annotations

import builtins
import uuid
from typing import Any, Callable

from apps.backend.domain.workspace.workspace_common import (
    bind_workspace_in_context,
    dump,
    find_workspace_by_name,
    list_workspaces_for_user,
    normalize_git_url,
    persist_conversation_workspace,
    user_from_context,
)

__version__ = "1.0.0"
TOOL_ID = "workspaces"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "workspace"
TOOL_LABEL = "Workspaces"
TOOL_DESCRIPTION = (
    "List, create, and bind coding workspaces (project_workspaces). "
    "Use workspace_bind before coding_* tools when the user asked to work in another repo."
)
# Router phrases: co-located workspaces.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("workspace.read", "workspace.write")
TOOL_MIN_ROLE = "user"


def list(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    user = user_from_context(context)
    if user is None:
        return dump({"ok": False, "error": "not authenticated"})
    name_filter = str(arguments.get("name") or "").strip().lower()
    workspaces = list_workspaces_for_user(user)
    if name_filter:
        workspaces = [
            w
            for w in workspaces
            if name_filter in (w.get("name") or "").lower()
            or name_filter in (w.get("git_url") or "").lower()
        ]
    slim = [
        {
            "id": w.get("id"),
            "name": w.get("name"),
            "source": w.get("source"),
            "git_url": w.get("git_url"),
            "git_branch": w.get("git_branch"),
            "path": w.get("path"),
        }
        for w in workspaces
    ]
    bound = None
    if context and isinstance(context.get("workspace"), dict):
        bound = context["workspace"].get("id")
    return dump(
        {
            "ok": True,
            "workspaces": slim,
            "count": len(slim),
            "bound_workspace_id": bound,
        }
    )


def create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    user = user_from_context(context)
    if user is None:
        return dump({"ok": False, "error": "not authenticated"})

    name = str(arguments.get("name") or "").strip()
    if not name:
        return dump({"ok": False, "error": "name is required"})

    source = str(arguments.get("source") or "git").strip().lower()
    if source not in ("manual", "git"):
        return dump({"ok": False, "error": "source must be manual or git"})

    git_url_raw = str(arguments.get("git_url") or arguments.get("url") or "").strip()
    git_branch = str(arguments.get("git_branch") or arguments.get("branch") or "main").strip() or "main"
    git_url: str | None = None
    if source == "git":
        git_url = normalize_git_url(git_url_raw)
        if not git_url:
            return dump(
                {
                    "ok": False,
                    "error": (
                        "git_url is required for source=git "
                        '(HTTPS URL or "owner/repo", e.g. fr4iser90/PIDEA)'
                    ),
                }
            )

    bind_after = arguments.get("bind")
    if bind_after is None:
        bind_after = True
    elif isinstance(bind_after, str):
        bind_after = bind_after.strip().lower() in ("1", "true", "yes", "on")
    else:
        bind_after = bool(bind_after)

    from apps.backend.infrastructure.workspace_service import (
        WorkspaceCreateError,
        create_project_workspace_for_user,
        ensure_workspace,
    )

    try:
        created = create_project_workspace_for_user(
            user,
            name=name,
            source=source,
            git_url=git_url,
            git_branch=git_branch,
        )
    except WorkspaceCreateError as e:
        return dump({"ok": False, "error": e.message})

    wid = str(created["id"])
    materialized = ensure_workspace(wid, user)
    if not materialized:
        return dump(
            {
                "ok": False,
                "error": "workspace row created but materialization failed (clone/path)",
                "workspace": created,
            }
        )

    bound = False
    conversation_updated = False
    if bind_after:
        bind_workspace_in_context(context, materialized)
        bound = True
        if user.id:
            conversation_updated = persist_conversation_workspace(context, wid, user.id)

    return dump(
        {
            "ok": True,
            "workspace": {
                "id": materialized.get("id"),
                "name": materialized.get("name"),
                "source": materialized.get("source"),
                "git_url": materialized.get("git_url"),
                "git_branch": materialized.get("git_branch"),
                "path": materialized.get("path"),
            },
            "bound": bound,
            "conversation_workspace_updated": conversation_updated,
            "agent_guidance": (
                "Workspace is active for further coding_* tools in this run. "
                "If the user asked to analyze a different repo than earlier messages, "
                "prefer fresh reads in this workspace; older tool output may refer to the previous tree."
            ),
        }
    )


def bind(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    user = user_from_context(context)
    if user is None:
        return dump({"ok": False, "error": "not authenticated"})

    wid_raw = arguments.get("workspace_id") or arguments.get("id")
    name_arg = str(arguments.get("name") or "").strip()

    from apps.backend.infrastructure.workspace_service import ensure_workspace

    wid: str | None = None
    if wid_raw is not None and str(wid_raw).strip():
        wid = str(wid_raw).strip()
    elif name_arg:
        hit = find_workspace_by_name(list_workspaces_for_user(user), name_arg)
        if hit:
            wid = str(hit.get("id") or "")
    if not wid:
        return dump(
            {
                "ok": False,
                "error": "workspace_id or name is required (use workspace_list first)",
            }
        )

    workspace = ensure_workspace(wid, user)
    if not workspace:
        return dump({"ok": False, "error": f"workspace not found or not accessible: {wid}"})

    previous: str | None = None
    if context:
        old = context.get("workspace")
        if isinstance(old, dict) and old.get("id"):
            previous = str(old["id"])

    bind_workspace_in_context(context, workspace)
    conversation_updated = False
    has_conversation_id = bool(
        context and str(context.get("conversation_id") or "").strip()
    )
    if user.id:
        conversation_updated = persist_conversation_workspace(context, str(workspace["id"]), user.id)

    return dump(
        {
            "ok": True,
            "workspace": {
                "id": workspace.get("id"),
                "name": workspace.get("name"),
                "source": workspace.get("source"),
                "git_url": workspace.get("git_url"),
                "git_branch": workspace.get("git_branch"),
                "path": workspace.get("path"),
            },
            "previous_workspace_id": previous,
            "conversation_workspace_updated": conversation_updated,
            "conversation_id_in_context": has_conversation_id,
            "ui_sync": True,
            "agent_guidance": (
                f"Bound to workspace **{workspace.get('name')}**. "
                "Use coding_* tools against this tree only. "
                "Earlier transcript tool results may reference another workspace — re-read files here."
            ),
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "list": list,
    "create": create,
    "bind": bind,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list",
            "TOOL_DESCRIPTION": "List project workspaces for the signed-in user (id, name, git_url).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional filter substring for name or git_url",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create",
            "TOOL_DESCRIPTION": (
                "Create a workspace (manual dir or git clone). "
                "Defaults bind=true so this run uses the new workspace."
            ),
            "parameters": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Unique workspace name (folder under your user path)",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["manual", "git"],
                        "TOOL_DESCRIPTION": "manual = empty dir; git = clone",
                    },
                    "git_url": {
                        "type": "string",
                        "TOOL_DESCRIPTION": 'HTTPS clone URL or "owner/repo" (GitHub)',
                    },
                    "git_branch": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Branch for git clone (default main)",
                    },
                    "bind": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Bind this workspace for the rest of the agent run (default true)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bind",
            "TOOL_DESCRIPTION": (
                "Switch the active coding workspace for this chat/run by workspace_id or name. "
                "Persists to the conversation when conversation_id is available."
            ),
            "parameters": {
                "type": "object",
                "minProperties": 1,
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Workspace UUID from workspace_list",
                    },
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Workspace name (alternative to workspace_id)",
                    },
                },
            },
        },
    },
]
