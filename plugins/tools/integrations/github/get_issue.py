"""Get one issue or pull request via the issues API."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.github._client import (
    MAX_ISSUE_BODY_CHARS,
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)

__version__ = "1.0.0"
TOOL_ID = "github_get_issue"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: Get issue"
TOOL_DESCRIPTION = "Get one issue or PR by number (issues endpoint)."
TOOL_TRIGGERS = ("github issue", "get issue")


def get_issue(arguments: dict[str, Any]) -> str:
    owner = (arguments.get("owner") or "").strip()
    repo = (arguments.get("repo") or "").strip()
    try:
        num = int(arguments.get("issue_number"))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "issue_number must be an integer"})
    if not owner or not repo:
        return json.dumps({"ok": False, "error": "owner and repo are required"})
    status, data = github_request("GET", f"/repos/{owner}/{repo}/issues/{num}")
    if is_error_payload(status, data):
        return json.dumps(data, ensure_ascii=False)
    if not isinstance(data, dict):
        return json.dumps({"ok": False, "error": "unexpected response"})
    body = str(data.get("body") or "")
    if len(body) > MAX_ISSUE_BODY_CHARS:
        body = body[:MAX_ISSUE_BODY_CHARS] + "\n… (truncated)"
    labels = [
        x.get("name")
        for x in (data.get("labels") or [])
        if isinstance(x, dict)
    ]
    return json.dumps(
        {
            "ok": True,
            "number": data.get("number"),
            "title": data.get("title"),
            "state": data.get("state"),
            "html_url": data.get("html_url"),
            "user": (data.get("user") or {}).get("login"),
            "labels": labels,
            "pull_request": bool(data.get("pull_request")),
            "body": body,
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {"get_issue": get_issue}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_issue",
            "TOOL_DESCRIPTION": (
                "Get one issue or pull request by number (body may be truncated). "
                "PRs are returned via the issues API when pull_request is present."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                },
                "required": ["owner", "repo", "issue_number"],
            },
        },
    },
]
