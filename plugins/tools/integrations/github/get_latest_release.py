"""Get the latest published GitHub release for a repository."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.github._client import (
    MAX_ISSUE_BODY_CHARS,
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)
from plugins.tools.integrations.github._release import release_summary

__version__ = "1.0.0"
TOOL_ID = "github_get_latest_release"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: Get latest release"
TOOL_DESCRIPTION = (
    "Fetch the latest GitHub release (tag, title, body, URL). "
    "Use before create_release to compare changes since the last tag."
)
# Router phrases: co-located get_latest_release.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
def get_latest_release(arguments: dict[str, Any]) -> str:
    owner = (arguments.get("owner") or "").strip()
    repo = (arguments.get("repo") or "").strip()
    if not owner or not repo:
        return json.dumps({"ok": False, "error": "owner and repo are required"})
    status, data = github_request("GET", f"/repos/{owner}/{repo}/releases/latest")
    if status == 404:
        return json.dumps(
            {
                "ok": True,
                "found": False,
                "message": "No published releases yet for this repository.",
            },
            ensure_ascii=False,
        )
    if is_error_payload(status, data):
        return json.dumps(data, ensure_ascii=False)
    if not isinstance(data, dict):
        return json.dumps({"ok": False, "error": "unexpected response"})
    body = str(data.get("body") or "")
    if len(body) > MAX_ISSUE_BODY_CHARS:
        body = body[:MAX_ISSUE_BODY_CHARS] + "\n… (truncated)"
    out = release_summary(data)
    out["ok"] = True
    out["found"] = True
    out["body"] = body
    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "get_latest_release": get_latest_release,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_latest_release",
            "TOOL_DESCRIPTION": (
                "Get the latest published GitHub release (tag_name, name, body, URL). "
                "Returns found=false when the repo has no releases yet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "TOOL_DESCRIPTION": "Repository owner (user or org)"},
                    "repo": {"type": "string", "TOOL_DESCRIPTION": "Repository name without .git"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
]
