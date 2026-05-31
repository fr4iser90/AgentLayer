"""Fetch a single file from a GitHub repository."""

from __future__ import annotations

import base64
import json
from typing import Any, Callable
from urllib.parse import quote

from plugins.tools.integrations.github._client import (
    MAX_FILE_CHARS,
    USER_SECRET_KEY,
    github_request,
    is_error_payload,
)

__version__ = "1.0.0"
TOOL_ID = "github_get_file"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "github"
TOOL_CAPABILITIES = ("code.repository",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "GitHub: Get file"
TOOL_DESCRIPTION = "Fetch one UTF-8 text file from a repository via the contents API."
TOOL_TRIGGERS = ("github file", "read github file", "repository file")


def get_file(arguments: dict[str, Any]) -> str:
    owner = (arguments.get("owner") or "").strip()
    repo = (arguments.get("repo") or "").strip()
    path = (arguments.get("path") or "").strip().lstrip("/")
    ref = (arguments.get("ref") or "").strip() or None
    if not owner or not repo or not path:
        return json.dumps(
            {"ok": False, "error": "owner, repo, and path are required"},
        )
    enc_path = quote(path, safe="")
    p = f"/repos/{owner}/{repo}/contents/{enc_path}"
    params: dict[str, Any] = {}
    if ref:
        params["ref"] = ref
    status, data = github_request("GET", p, params=params or None)
    if is_error_payload(status, data):
        return json.dumps(data, ensure_ascii=False)
    if not isinstance(data, dict):
        return json.dumps({"ok": False, "error": "unexpected response"})
    if data.get("type") != "file":
        return json.dumps(
            {
                "ok": False,
                "error": "not a file (directory or submodule); use search_code",
                "type": data.get("type"),
            },
        )
    b64 = data.get("encoding") == "base64" and data.get("content")
    if not b64:
        return json.dumps(
            {
                "ok": False,
                "error": "no file content (too large or empty)",
                "sha": data.get("sha"),
            },
        )
    try:
        raw = base64.b64decode(
            "".join(str(b64).splitlines()),
            validate=False,
        ).decode("utf-8", errors="replace")
    except Exception as e:
        return json.dumps({"ok": False, "error": f"decode failed: {e}"})
    if len(raw) > MAX_FILE_CHARS:
        raw = raw[:MAX_FILE_CHARS] + "\n… (truncated)"
    return json.dumps(
        {
            "ok": True,
            "path": data.get("path"),
            "sha": data.get("sha"),
            "size": data.get("size"),
            "html_url": data.get("html_url"),
            "content": raw,
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {"get_file": get_file}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_file",
            "TOOL_DESCRIPTION": (
                "Fetch a single file from a repository (decoded UTF-8 text). "
                "Large files are truncated. Not for directories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "File path in repo, e.g. README.md",
                    },
                    "ref": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional branch, tag, or commit SHA",
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        },
    },
]
