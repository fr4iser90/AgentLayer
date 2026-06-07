"""Generic outbound HTTP tool — SSRF-safe, auth via user secrets."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.domain.http_connector.request import execute_http
from apps.backend.domain.identity import get_identity

__version__ = "1.0.0"
TOOL_ID = "http"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "http"
TOOL_RISK_LEVEL = 3
TOOL_LABEL = "HTTP"
TOOL_DESCRIPTION = (
    "Call any HTTPS/HTTP JSON API. Auth via user secrets (bearer, api_key, basic). "
    "SSRF-protected. Store reusable API definitions with connector.save_profile."
)
TOOL_TRIGGERS = (
    "http",
    "api",
    "rest",
    "fetch",
    "call api",
    "webhook",
    "request",
    "connector",
)
TOOL_CAPABILITIES = ("web.http",)
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "call": {"min_role": "user", "capabilities": ("web.http",)},
}


def _err(msg: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False)


def call(arguments: dict[str, Any]) -> str:
    """Execute one HTTP request. Secrets are read server-side — never pass tokens in arguments."""
    ident = get_identity()
    if ident[1] is None:
        return _err("No user identity — http.call needs an authenticated user.")
    _tid, uid = ident

    method = str(arguments.get("method") or "GET").strip().upper()
    url = str(arguments.get("url") or "").strip() or None
    base_url = str(arguments.get("base_url") or "").strip() or None
    path = str(arguments.get("path") or "").strip() or None
    query = arguments.get("query") if isinstance(arguments.get("query"), dict) else None
    headers = arguments.get("headers") if isinstance(arguments.get("headers"), dict) else None
    body = arguments.get("body")
    if body is None and "json" in arguments:
        body = arguments.get("json")
    auth = arguments.get("auth") if isinstance(arguments.get("auth"), dict) else None
    extract = str(arguments.get("extract") or "").strip() or None

    result = execute_http(
        user_id=uid,
        method=method,
        url=url,
        base_url=base_url,
        path=path,
        query=query,
        headers=headers,
        body=body,
        auth=auth,
        extract=extract,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "call": call,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "call",
            "description": (
                "HTTP request to a public API. Use auth.secret_key referencing a saved user secret. "
                "Optional extract dot-path (e.g. data.items). Blocked: private/loopback URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "GET, POST, PUT, PATCH, DELETE (default GET)",
                    },
                    "url": {"type": "string", "description": "Full URL (or use base_url + path)"},
                    "base_url": {"type": "string", "description": "API base, e.g. https://api.example.com/v1"},
                    "path": {"type": "string", "description": "Path relative to base_url"},
                    "query": {
                        "type": "object",
                        "description": "Query string key-value pairs",
                        "additionalProperties": True,
                    },
                    "headers": {
                        "type": "object",
                        "description": "Extra headers",
                        "additionalProperties": {"type": "string"},
                    },
                    "body": {
                        "description": "JSON object/array or string body (not for GET)",
                    },
                    "auth": {
                        "type": "object",
                        "description": (
                            "Auth spec: {type: bearer|api_key_header|api_key_query|basic|none, "
                            "secret_key, header?, param?}"
                        ),
                        "additionalProperties": True,
                    },
                    "extract": {
                        "type": "string",
                        "description": "Optional dot-path to extract from JSON response",
                    },
                },
                "required": [],
            },
        },
    },
]
