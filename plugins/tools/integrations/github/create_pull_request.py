"""Create a pull request on GitHub."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.github._client import (
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)
from plugins.tools.integrations.github._pr import pull_request_summary

__version__ = "1.0.0"
TOOL_ID = "github_create_pull_request"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: Create pull request"
TOOL_DESCRIPTION = (
    "Open a pull request (POST /pulls). Push the head branch with git_push first; "
    "do not use bash or gh."
)
TOOL_TRIGGERS = ("create pr", "open pull request", "github pr create")


def create_pull_request(arguments: dict[str, Any]) -> str:
    owner = (arguments.get("owner") or "").strip()
    repo = (arguments.get("repo") or "").strip()
    title = (arguments.get("title") or "").strip()
    head = (arguments.get("head") or "").strip()
    base = (arguments.get("base") or "main").strip() or "main"
    body = (arguments.get("body") or "").strip()
    if not owner or not repo:
        return json.dumps({"ok": False, "error": "owner and repo are required"})
    if not title:
        return json.dumps({"ok": False, "error": "title is required"})
    if not head:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "head is required (branch name on this repo, or owner:branch for a fork). "
                    "Push the branch with git_push first."
                ),
            },
        )
    payload: dict[str, Any] = {"title": title, "head": head, "base": base}
    if body:
        payload["body"] = body
    if arguments.get("draft") is True:
        payload["draft"] = True
    status, data = github_request(
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        json_body=payload,
    )
    if is_error_payload(status, data):
        hint = None
        if status == 422:
            hint = (
                "Branch missing on remote? Call git_push for head first. "
                "For forks use head=owner:branch. Check base exists."
            )
        err = data if isinstance(data, dict) else {"ok": False, "error": "request failed"}
        if hint and isinstance(err, dict):
            err = {**err, "hint": hint}
        return json.dumps(err, ensure_ascii=False)
    if not isinstance(data, dict):
        return json.dumps({"ok": False, "error": "unexpected response"})
    out = pull_request_summary(data)
    out["ok"] = True
    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "create_pull_request": create_pull_request,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_pull_request",
            "TOOL_DESCRIPTION": (
                "Open a pull request on GitHub (POST /pulls). Requires github_pat with repo / "
                "pull-request write scope. Push head with git_push first; do not use bash or gh."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "TOOL_DESCRIPTION": "Repository owner (user or org)"},
                    "repo": {"type": "string", "TOOL_DESCRIPTION": "Repository name without .git"},
                    "title": {"type": "string"},
                    "head": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Source branch (e.g. security-fixes) or fork owner:branch",
                    },
                    "base": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Target branch (default main)",
                    },
                    "body": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "PR description (markdown)",
                    },
                    "draft": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Create as draft PR",
                    },
                },
                "required": ["owner", "repo", "title", "head"],
            },
        },
    },
]
