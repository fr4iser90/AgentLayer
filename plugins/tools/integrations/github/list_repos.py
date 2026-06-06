"""List GitHub repositories for the signed-in user (github_pat)."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.domain.github.repos import list_user_repos
from apps.backend.domain.identity import get_identity
from plugins.tools.integrations.github._client import USER_SECRET_KEY

__version__ = "1.0.0"
TOOL_ID = "github_list_repos"
TOOL_BUCKET = "integrations"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("github.read",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: List repositories"
TOOL_DESCRIPTION = (
    "List repositories visible to the user via github_pat. "
    "Returns repo metadata only — use dashboard.list_append to add rows to a board."
)
TOOL_TRIGGERS = ("list repos", "github repos", "repositories", "repos importieren")


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def list_repos(arguments: dict[str, Any]) -> str:
    tid_uid = get_identity()
    if tid_uid[1] is None:
        return _err("No user identity — github.list_repos needs an authenticated user.")
    _tid, uid = tid_uid

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
            "html_url": r.get("html_url"),
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


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "list_repos": list_repos,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_repos",
            "TOOL_DESCRIPTION": (
                "List GitHub repos (github_pat). Does not write dashboards — "
                "map rows and call dashboard.list_append separately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "TOOL_DESCRIPTION": "Page number (default 1)"},
                    "per_page": {"type": "integer", "TOOL_DESCRIPTION": "1–100 (default 100)"},
                },
                "required": [],
            },
        },
    },
]
