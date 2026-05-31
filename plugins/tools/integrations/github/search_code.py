"""Search code on GitHub."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.github._client import (
    MAX_SEARCH_ITEMS,
    TOOL_USER_SECRET_FORMS,
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)

__version__ = "1.0.0"
TOOL_ID = "github_search_code"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_USER_SECRET_FORMS = TOOL_USER_SECRET_FORMS
TOOL_LABEL = "GitHub: Search code"
TOOL_DESCRIPTION = "Search code on GitHub (github.com query syntax)."
TOOL_TRIGGERS = ("github code search", "search repository code")


def search_code(arguments: dict[str, Any]) -> str:
    q = (arguments.get("query") or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "query is required"})
    per_page = min(max(int(arguments.get("per_page") or 10), 1), MAX_SEARCH_ITEMS)
    status, data = github_request(
        "GET",
        "/search/code",
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
                    "name": it.get("name"),
                    "path": it.get("path"),
                    "html_url": it.get("html_url"),
                    "repository": (it.get("repository") or {}).get("full_name"),
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


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {"search_code": search_code}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "TOOL_DESCRIPTION": (
                "Search code on GitHub (same query syntax as github.com search). "
                "Needs GITHUB_TOKEN (env) or user secret github_pat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "GitHub code search query, e.g. org:myorg filename:flake.nix",
                    },
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
