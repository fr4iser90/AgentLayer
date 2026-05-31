"""Search issues and pull requests on GitHub."""

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
TOOL_ID = "github_search_issues"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: Search issues"
TOOL_DESCRIPTION = "Search issues and pull requests across GitHub."
TOOL_TRIGGERS = ("github issues", "search issues", "search pull requests")


def search_issues(arguments: dict[str, Any]) -> str:
    q = (arguments.get("query") or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "query is required"})
    per_page = min(max(int(arguments.get("per_page") or 10), 1), MAX_SEARCH_ITEMS)
    status, data = github_request(
        "GET",
        "/search/issues",
        params={"q": q, "per_page": per_page},
    )
    if is_error_payload(status, data):
        return json.dumps(data, ensure_ascii=False)
    items_out: list[dict[str, Any]] = []
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        for it in data["items"][:per_page]:
            if not isinstance(it, dict):
                continue
            items_out.append(
                {
                    "number": it.get("number"),
                    "title": it.get("title"),
                    "state": it.get("state"),
                    "html_url": it.get("html_url"),
                    "repository_url": it.get("repository_url"),
                    "pull_request": bool(it.get("pull_request")),
                }
            )
    return json.dumps(
        {
            "ok": True,
            "total_count": data.get("total_count") if isinstance(data, dict) else None,
            "items": items_out,
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {"search_issues": search_issues}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_issues",
            "TOOL_DESCRIPTION": (
                "Search issues and pull requests across GitHub. "
                "Query examples: repo:owner/name is:open label:bug"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "per_page": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Max results 1–20 (default 10).",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
