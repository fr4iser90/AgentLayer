"""List pull requests for a GitHub repository."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.github._client import (
    MAX_SEARCH_ITEMS,
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)

__version__ = "1.0.0"
TOOL_ID = "github_list_pull_requests"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: List pull requests"
TOOL_DESCRIPTION = "List pull requests (open, closed, or all)."
TOOL_TRIGGERS = ("list prs", "list pull requests", "github prs")


def list_pull_requests(arguments: dict[str, Any]) -> str:
    owner = (arguments.get("owner") or "").strip()
    repo = (arguments.get("repo") or "").strip()
    if not owner or not repo:
        return json.dumps({"ok": False, "error": "owner and repo are required"})
    state = (arguments.get("state") or "open").strip().lower()
    if state not in ("open", "closed", "all"):
        state = "open"
    per_page = min(max(int(arguments.get("per_page") or 10), 1), MAX_SEARCH_ITEMS)
    status, data = github_request(
        "GET",
        f"/repos/{owner}/{repo}/pulls",
        params={"state": state, "per_page": per_page},
    )
    if is_error_payload(status, data):
        return json.dumps(data, ensure_ascii=False)
    items_out: list[dict[str, Any]] = []
    if isinstance(data, list):
        for it in data[:per_page]:
            if not isinstance(it, dict):
                continue
            items_out.append(
                {
                    "number": it.get("number"),
                    "title": it.get("title"),
                    "state": it.get("state"),
                    "html_url": it.get("html_url"),
                    "draft": it.get("draft"),
                    "user": (it.get("user") or {}).get("login"),
                }
            )
    if not isinstance(data, list):
        return json.dumps(
            {"ok": False, "error": "unexpected response"},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, "items": items_out}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "list_pull_requests": list_pull_requests,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_pull_requests",
            "TOOL_DESCRIPTION": "List pull requests for a repository (open, closed, or all).",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "TOOL_DESCRIPTION": "Default open",
                    },
                    "per_page": {"type": "integer", "TOOL_DESCRIPTION": "1–20, default 10"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
]
