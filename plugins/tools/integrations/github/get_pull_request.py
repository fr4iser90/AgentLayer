"""Get one pull request by number."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.github._client import (
    MAX_ISSUE_BODY_CHARS,
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)
from plugins.tools.integrations.github._pr import pull_request_summary

__version__ = "1.0.0"
TOOL_ID = "github_get_pull_request"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: Get pull request"
TOOL_DESCRIPTION = "Get one pull request (title, branches, body, URL)."
TOOL_TRIGGERS = ("get pr", "pull request details")


def get_pull_request(arguments: dict[str, Any]) -> str:
    owner = (arguments.get("owner") or "").strip()
    repo = (arguments.get("repo") or "").strip()
    try:
        num = int(arguments.get("pull_number"))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "pull_number must be an integer"})
    if not owner or not repo:
        return json.dumps({"ok": False, "error": "owner and repo are required"})
    status, data = github_request("GET", f"/repos/{owner}/{repo}/pulls/{num}")
    if is_error_payload(status, data):
        return json.dumps(data, ensure_ascii=False)
    if not isinstance(data, dict):
        return json.dumps({"ok": False, "error": "unexpected response"})
    body = str(data.get("body") or "")
    if len(body) > MAX_ISSUE_BODY_CHARS:
        body = body[:MAX_ISSUE_BODY_CHARS] + "\n… (truncated)"
    out = pull_request_summary(data)
    out["ok"] = True
    out["body"] = body
    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "get_pull_request": get_pull_request,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_pull_request",
            "TOOL_DESCRIPTION": "Get one pull request by number (title, branches, body, URL).",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "pull_number": {"type": "integer"},
                },
                "required": ["owner", "repo", "pull_number"],
            },
        },
    },
]
