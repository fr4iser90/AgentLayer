"""Reusable HTTP connector profiles — save API definitions and run named endpoints."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.http.lib.extract import apply_template
from plugins.tools.integrations.http.lib.profiles_db import (
    connector_profile_delete,
    connector_profile_get,
    connector_profile_list,
    connector_profile_upsert,
    normalize_profile_id,
)
from plugins.tools.integrations.http.lib.request import execute_http
from apps.backend.domain.identity import get_identity

__version__ = "1.0.0"
TOOL_ID = "connector"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "connector"
TOOL_RISK_LEVEL = 3
TOOL_LABEL = "API connector"
TOOL_DESCRIPTION = (
    "Save reusable HTTP API profiles (base_url, auth, endpoints) and run named endpoints. "
    "Pair with save_user_secret for tokens. Results can be written to dashboards via dashboard.patch_data."
)
# Router phrases: co-located connector.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("connector.read", "connector.write")
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "save_profile": {"min_role": "user", "capabilities": ("connector.write",)},
    "list_profiles": {"min_role": "user", "capabilities": ("connector.read",)},
    "run": {"min_role": "user", "capabilities": ("connector.write",)},
    "delete_profile": {"min_role": "user", "capabilities": ("connector.write",)},
}


def _err(msg: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False)


def _identity_uid() -> Any:
    ident = get_identity()
    if ident[1] is None:
        return None
    return ident[1]


def save_profile(arguments: dict[str, Any]) -> str:
    uid = _identity_uid()
    if uid is None:
        return _err("No user identity — connector.save_profile needs an authenticated user.")

    pid_raw = str(arguments.get("profile_id") or "").strip()
    if normalize_profile_id(pid_raw) is None:
        return _err("profile_id must match ^[a-z][a-z0-9_-]{0,63}$")

    base_url = str(arguments.get("base_url") or "").strip()
    if not base_url:
        return _err("base_url required")

    auth = arguments.get("auth") if isinstance(arguments.get("auth"), dict) else {}
    default_headers = (
        arguments.get("default_headers")
        if isinstance(arguments.get("default_headers"), dict)
        else {}
    )
    endpoints = arguments.get("endpoints") if isinstance(arguments.get("endpoints"), dict) else {}
    if not endpoints:
        return _err("endpoints required — object mapping endpoint name to {method, path, ...}")

    row = connector_profile_upsert(
        uid,
        pid_raw,
        label=str(arguments.get("label") or "").strip() or None,
        base_url=base_url,
        auth=auth,
        default_headers=default_headers,
        endpoints=endpoints,
    )
    if row is None:
        return _err("invalid profile — check profile_id and base_url (must be public HTTPS/HTTP)")
    return json.dumps({"ok": True, "profile": row}, ensure_ascii=False, default=str)


def list_profiles(arguments: dict[str, Any]) -> str:
    uid = _identity_uid()
    if uid is None:
        return _err("No user identity — connector.list_profiles needs an authenticated user.")
    try:
        limit = int(arguments.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    rows = connector_profile_list(uid, limit=limit)
    return json.dumps({"ok": True, "profiles": rows, "count": len(rows)}, ensure_ascii=False)


def delete_profile(arguments: dict[str, Any]) -> str:
    uid = _identity_uid()
    if uid is None:
        return _err("No user identity — connector.delete_profile needs an authenticated user.")
    pid = str(arguments.get("profile_id") or "").strip()
    if not connector_profile_delete(uid, pid):
        return _err("profile not found or invalid profile_id")
    return json.dumps({"ok": True, "deleted": pid}, ensure_ascii=False)


def run(arguments: dict[str, Any]) -> str:
    uid = _identity_uid()
    if uid is None:
        return _err("No user identity — connector.run needs an authenticated user.")

    pid = str(arguments.get("profile_id") or "").strip()
    endpoint = str(arguments.get("endpoint") or "").strip()
    if not pid or not endpoint:
        return _err("profile_id and endpoint required")

    prof = connector_profile_get(uid, pid)
    if prof is None:
        return _err("profile not found")

    eps = prof.get("endpoints") if isinstance(prof.get("endpoints"), dict) else {}
    spec = eps.get(endpoint)
    if not isinstance(spec, dict):
        known = sorted(eps.keys())
        return _err(f"unknown endpoint {endpoint!r}", known_endpoints=known)

    params = arguments.get("params") if isinstance(arguments.get("params"), dict) else {}
    method = str(spec.get("method") or "GET").strip().upper()
    path_tpl = str(spec.get("path") or "/").strip() or "/"
    path = apply_template(path_tpl, params)

    query: dict[str, str] = {}
    for key in spec.get("query_params") or []:
        if isinstance(key, str) and key in params:
            query[key] = str(params[key])
    extra_q = spec.get("query") if isinstance(spec.get("query"), dict) else {}
    for k, v in extra_q.items():
        query[str(k)] = apply_template(str(v), params)

    body = arguments.get("body")
    if body is None and spec.get("body_template") is not None:
        body = apply_template(spec.get("body_template"), params)

    extract = str(spec.get("extract") or arguments.get("extract") or "").strip() or None
    headers = dict(prof.get("default_headers") or {})
    extra_h = spec.get("headers") if isinstance(spec.get("headers"), dict) else {}
    headers.update({str(k): str(v) for k, v in extra_h.items()})

    result = execute_http(
        user_id=uid,
        method=method,
        base_url=str(prof.get("base_url") or ""),
        path=path,
        query=query or None,
        headers=headers,
        body=body,
        auth=prof.get("auth") if isinstance(prof.get("auth"), dict) else None,
        extract=extract,
    )
    result["profile_id"] = pid
    result["endpoint"] = endpoint
    return json.dumps(result, ensure_ascii=False, default=str)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "save_profile": save_profile,
    "list_profiles": list_profiles,
    "run": run,
    "delete_profile": delete_profile,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_profile",
            "description": "Create or update a reusable API connector profile for this user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile_id": {
                        "type": "string",
                        "description": "Slug id (lowercase, e.g. todoist, weather_api)",
                    },
                    "label": {"type": "string", "description": "Human label"},
                    "base_url": {"type": "string", "description": "API root URL"},
                    "auth": {
                        "type": "object",
                        "description": "Same shape as http.call auth",
                        "additionalProperties": True,
                    },
                    "default_headers": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                    "endpoints": {
                        "type": "object",
                        "description": (
                            "Map of endpoint name → {method, path, query_params?, body_template?, extract?}. "
                            "Use {{param}} in path/body."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["profile_id", "base_url", "endpoints"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_profiles",
            "description": "List saved connector profiles (ids, labels, endpoint names).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max rows (default 50)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run",
            "description": "Execute a named endpoint from a saved profile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "string"},
                    "endpoint": {"type": "string"},
                    "params": {
                        "type": "object",
                        "description": "Template variables for path/body/query",
                        "additionalProperties": True,
                    },
                    "body": {"description": "Optional body override"},
                    "extract": {"type": "string", "description": "Override endpoint extract path"},
                },
                "required": ["profile_id", "endpoint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_profile",
            "description": "Delete a saved connector profile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "string"},
                },
                "required": ["profile_id"],
            },
        },
    },
]
