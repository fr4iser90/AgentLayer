"""Create a GitHub release (tag + release notes)."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.github._client import (
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)
from plugins.tools.integrations.github._release import release_summary

__version__ = "1.0.0"
TOOL_ID = "github_create_release"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: Create release"
TOOL_DESCRIPTION = (
    "Publish a GitHub release (POST /releases). Use get_latest_release and git_read log "
    "with since_ref to draft changelog first; do not use bash or gh."
)
# Router phrases: co-located create_release.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
def create_release(arguments: dict[str, Any]) -> str:
    owner = (arguments.get("owner") or "").strip()
    repo = (arguments.get("repo") or "").strip()
    tag_name = (arguments.get("tag_name") or "").strip()
    name = (arguments.get("name") or "").strip()
    body = (arguments.get("body") or "").strip()
    target_commitish = (arguments.get("target_commitish") or "").strip()
    if not owner or not repo:
        return json.dumps({"ok": False, "error": "owner and repo are required"})
    if not tag_name:
        return json.dumps({"ok": False, "error": "tag_name is required (e.g. v1.2.0)"})

    payload: dict[str, Any] = {"tag_name": tag_name}
    if name:
        payload["name"] = name
    elif tag_name:
        payload["name"] = tag_name
    if body:
        payload["body"] = body
    if target_commitish:
        payload["target_commitish"] = target_commitish
    if arguments.get("draft") is True:
        payload["draft"] = True
    if arguments.get("prerelease") is True:
        payload["prerelease"] = True
    if arguments.get("generate_release_notes") is True:
        payload["generate_release_notes"] = True

    status, data = github_request(
        "POST",
        f"/repos/{owner}/{repo}/releases",
        json_body=payload,
    )
    if is_error_payload(status, data):
        hint = None
        if status == 422:
            hint = (
                "Tag may already exist or target_commitish is invalid. "
                "Use get_latest_release to pick the next tag; ensure the commit/branch exists on GitHub "
                "(git_push first if needed)."
            )
        err = data if isinstance(data, dict) else {"ok": False, "error": "request failed"}
        if hint and isinstance(err, dict):
            err = {**err, "hint": hint}
        return json.dumps(err, ensure_ascii=False)
    if not isinstance(data, dict):
        return json.dumps({"ok": False, "error": "unexpected response"})
    out = release_summary(data)
    out["ok"] = True
    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "create_release": create_release,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_release",
            "TOOL_DESCRIPTION": (
                "Create a GitHub release (POST /releases). Requires github_pat with repo / "
                "contents write scope. Draft changelog with get_latest_release + git_read log "
                "(since_ref=last tag); prefer draft=true until the user confirms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "TOOL_DESCRIPTION": "Repository owner (user or org)"},
                    "repo": {"type": "string", "TOOL_DESCRIPTION": "Repository name without .git"},
                    "tag_name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Git tag for this release (e.g. v1.2.0)",
                    },
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Release title (defaults to tag_name)",
                    },
                    "body": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Release notes / changelog (markdown)",
                    },
                    "target_commitish": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Branch or commit SHA for the tag when it does not exist yet "
                            "(default: repository default branch)"
                        ),
                    },
                    "draft": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Create as draft release (recommended until user confirms)",
                    },
                    "prerelease": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Mark as pre-release",
                    },
                    "generate_release_notes": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Let GitHub auto-generate release notes from merged PRs",
                    },
                },
                "required": ["owner", "repo", "tag_name"],
            },
        },
    },
]
