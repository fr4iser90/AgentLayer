"""List / update workspace env→user_secret bindings (names only, Postgres)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from apps.backend.domain.shared.identity import get_identity
from plugins.tools.workspace.lib.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)
from plugins.tools.workspace.lib.env_secret_bridge import (
    bindings_status_payload,
    load_env_bindings,
    save_env_bindings,
)

__version__ = "1.1.0"
TOOL_ID = "env_bindings"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "repository"
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("coding.execute", "coding.read")
TOOL_LABEL = "Coding: Env secret bindings"
TOOL_DESCRIPTION = (
    "Map process environment variable names to user_secrets service_keys for this "
    "bound workspace (stored in Postgres — names only, not a repo file). "
    "Usually unnecessary: save_user_secret auto-creates bindings (FOO_BAR ← foo_bar). "
    "bash injects secret values at runtime: workspace-scoped secret first, then global. "
    "Actions: list (default), set (merge bindings map), clear (remove keys)."
)


def env_bindings(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    wid = ws.get("id")
    _tid, uid = get_identity()
    if uid is None:
        return json.dumps(
            {"ok": False, "error": "not authenticated — cannot store workspace bindings"},
            ensure_ascii=False,
        )
    action = str(arguments.get("action") or "list").strip().lower()

    if action in ("list", "status", ""):
        return json.dumps(
            bindings_status_payload(root, user_id=uid, workspace_id=wid),
            ensure_ascii=False,
        )

    if action == "set":
        raw = arguments.get("bindings")
        if not isinstance(raw, dict) or not raw:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        'action=set requires bindings object, e.g. '
                        '{"FOO_BAR":"foo_bar","API_TOKEN":"api_token"} '
                        "(env name → service_key; usually lowercased env name)"
                    ),
                },
                ensure_ascii=False,
            )
        merged = load_env_bindings(root, user_id=uid, workspace_id=wid)
        for k, v in raw.items():
            merged[str(k)] = str(v)
        try:
            saved = save_env_bindings(
                root, merged, user_id=uid, workspace_id=wid
            )
        except ValueError as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        status = bindings_status_payload(root, user_id=uid, workspace_id=wid)
        status["updated"] = True
        status["bindings_count"] = len(saved)
        status["for_assistant_must_say_de"] = (
            "Bindings in der DB gespeichert (nur Namen). Fehlende Secrets mit "
            "save_user_secret (scope=workspace) / request_user_secret anlegen, dann bash erneut."
        )
        return json.dumps(status, ensure_ascii=False)

    if action == "clear":
        keys = arguments.get("keys")
        current = load_env_bindings(root, user_id=uid, workspace_id=wid)
        if keys is None:
            saved = save_env_bindings(root, {}, user_id=uid, workspace_id=wid)
        elif isinstance(keys, list):
            remove = {str(k).strip() for k in keys if str(k).strip()}
            saved = save_env_bindings(
                root,
                {en: sk for en, sk in current.items() if en not in remove},
                user_id=uid,
                workspace_id=wid,
            )
        else:
            return json.dumps(
                {"ok": False, "error": "keys must be a list of env names, or omit to clear all"},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "ok": True,
                "cleared": True,
                "bindings_count": len(saved),
                "storage": "database",
                "workspace_id": str(wid) if wid else None,
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {"ok": False, "error": "action must be list, set, or clear"},
        ensure_ascii=False,
    )


def tool_step_detail(arguments: dict[str, Any]) -> str:
    action = str(arguments.get("action") or "list").strip().lower()
    return action or "list"


HANDLERS: dict[str, Callable[..., str]] = {
    "env_bindings": env_bindings,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "env_bindings",
            "TOOL_DESCRIPTION": (
                "List/set/clear workspace env→secret bindings in Postgres (names only). "
                "Example set: bindings={FOO_BAR: foo_bar} (env name → lowercased service_key)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "list (default) | set | clear",
                    },
                    "bindings": {
                        "type": "object",
                        "TOOL_DESCRIPTION": (
                            "For set: map ENV_NAME → service_key "
                            '(usually lowercased env name, e.g. {"FOO_BAR":"foo_bar"}).'
                        ),
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "TOOL_DESCRIPTION": "For clear: env names to remove (omit = clear all).",
                    },
                },
            },
        },
    },
]
