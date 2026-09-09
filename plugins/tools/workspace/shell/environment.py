"""Report which coding CLIs are available in the AgentLayer server container."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from plugins.tools.workspace.lib.bash_policy import subprocess_env_for_coding
from plugins.tools.workspace.lib.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)
from plugins.tools.workspace.lib.host_toolchain import probe_coding_environment

__version__ = "1.0.0"
TOOL_ID = "environment"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "repository"
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("coding.execute", "coding.read")
TOOL_LABEL = "Coding: Environment"
TOOL_DESCRIPTION = (
    "List which CLIs (node, npm, python, git, docker, …) are available in the "
    "AgentLayer **server container** PATH used by bash. Call this when a tool "
    "fails with missing_executable, or before assuming npx/node/docker exist. "
    "Does not inspect the user's laptop unless the workspace is client-mode."
)


def environment(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = arguments
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    env = subprocess_env_for_coding(home=str(root.resolve()), cwd=str(root.resolve()))
    payload = probe_coding_environment(env=env)
    payload["workspace_id"] = ws.get("id")
    payload["workspace_path"] = str(root)
    return json.dumps(payload, ensure_ascii=False)


def tool_step_detail(arguments: dict[str, Any]) -> str:
    _ = arguments
    return "probe host toolchain"


HANDLERS: dict[str, Callable[..., str]] = {
    "environment": environment,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "environment",
            "TOOL_DESCRIPTION": (
                "Probe which coding CLIs exist in the AgentLayer server container "
                "(node/npm/python/git/…). Use when unsure the toolchain is installed."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
