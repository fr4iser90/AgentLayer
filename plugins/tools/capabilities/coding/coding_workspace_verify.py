"""Run the workspace verify command from DB policy (bounded shell); persists each run."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, cast

from apps.backend.core.config import config

from plugins.tools.capabilities.coding.coding_bash import _is_blocked, _tail
from plugins.tools.capabilities.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

__version__ = "1.1.0"
TOOL_ID = "coding_workspace_verify"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("verify workspace", "run verify", "lint test workspace", "agentlayer verify")
TOOL_CAPABILITIES = ("coding.execute",)
TOOL_LABEL = "Coding: Workspace verify"
TOOL_DESCRIPTION = (
    "Run **only** the shell command stored on the workspace (``verify_command`` in the database). "
    "Does not accept arbitrary commands from the model (unlike ``coding_bash``). "
    "Same dangerous-pattern blocklist as ``coding_bash``. Timeout from ``AGENT_WORKSPACE_VERIFY_TIMEOUT_SEC``. "
    "Each run is recorded in ``workspace_verify_runs``."
)

MAX_OUTPUT_BYTES = 80_000


def _verify_command_from_workspace(ws: dict[str, Any]) -> tuple[str | None, str | None]:
    vc = ws.get("verify_command")
    if isinstance(vc, str) and vc.strip():
        return vc.strip(), None
    return None, "verify_command is not set for this workspace (configure it via PATCH /v1/workspaces/{id})"


def _persist_run(
    *,
    workspace_id: str,
    user: Any,
    agent_run_id: str | None,
    command: str,
    exit_code: int,
    ok: bool,
    output_preview: str | None,
    error_message: str | None = None,
) -> None:
    try:
        from apps.backend.infrastructure.workspace_verify_store import insert_verify_run

        insert_verify_run(
            workspace_id=uuid.UUID(str(workspace_id)),
            user_id=uuid.UUID(str(getattr(user, "id"))),
            agent_run_id=agent_run_id,
            command=command,
            exit_code=exit_code,
            ok=ok,
            output_preview=output_preview,
            error_message=error_message,
        )
    except Exception:
        pass


def coding_workspace_verify(arguments: dict[str, Any], context: dict | None = None) -> str:
    ctx = context or {}
    ws = workspace_binding_from_context(ctx)
    if ws is None:
        return json_workspace_missing_error()
    wid = str(ws.get("id") or "").strip()
    user = ctx.get("user")
    agent_run_id = ctx.get("agent_run_id")
    if isinstance(agent_run_id, str):
        agent_run_id = agent_run_id.strip() or None
    else:
        agent_run_id = None

    root = Path(ws["path"]).resolve()

    cmd, err = _verify_command_from_workspace(ws)
    if err or not cmd:
        out = json.dumps({"ok": False, "error": err or "no verify_command"}, ensure_ascii=False)
        if wid and user is not None and getattr(user, "id", None) is not None:
            _persist_run(
                workspace_id=wid,
                user=user,
                agent_run_id=agent_run_id,
                command="",
                exit_code=-2,
                ok=False,
                output_preview=None,
                error_message=err or "no verify_command",
            )
        return out

    blocked = _is_blocked(cmd)
    if blocked:
        payload = {"ok": False, "error": blocked, "verify_command": cmd[:500]}
        if wid and user is not None and getattr(user, "id", None) is not None:
            _persist_run(
                workspace_id=wid,
                user=user,
                agent_run_id=agent_run_id,
                command=cmd,
                exit_code=-3,
                ok=False,
                output_preview=None,
                error_message=str(blocked)[:4000],
            )
        return json.dumps(payload, ensure_ascii=False)

    timeout_s = int(config.AGENT_WORKSPACE_VERIFY_TIMEOUT_SEC)
    try:
        raw_to = arguments.get("timeout")
        if raw_to is not None:
            timeout_s = max(30, min(int(raw_to), 3600))
    except (TypeError, ValueError):
        pass

    env = {**os.environ, "HOME": str(root), "PWD": str(root)}
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        out_text = ""
        if e.stdout:
            out_text += str(e.stdout)
        if e.stderr:
            out_text += "\n" + str(e.stderr)
        preview, cut = _tail(out_text, MAX_OUTPUT_BYTES)
        err_msg = f"verify_command timed out after {timeout_s}s"
        if wid and user is not None and getattr(user, "id", None) is not None:
            _persist_run(
                workspace_id=wid,
                user=user,
                agent_run_id=agent_run_id,
                command=cmd,
                exit_code=-1,
                ok=False,
                output_preview=preview,
                error_message=err_msg,
            )
        return json.dumps(
            {
                "ok": False,
                "error": err_msg,
                "exit_code": -1,
                "truncated": cut,
                "output": preview,
                "verify_command": cmd[:500],
            },
            ensure_ascii=False,
        )
    except OSError as e:
        if wid and user is not None and getattr(user, "id", None) is not None:
            _persist_run(
                workspace_id=wid,
                user=user,
                agent_run_id=agent_run_id,
                command=cmd,
                exit_code=-4,
                ok=False,
                output_preview=None,
                error_message=str(e)[:4000],
            )
        return json.dumps({"ok": False, "error": str(e), "verify_command": cmd[:500]}, ensure_ascii=False)

    combined = ""
    if result.stdout:
        combined += result.stdout
    if result.stderr:
        if combined:
            combined += "\n--- stderr ---\n"
        combined += result.stderr
    if not combined:
        combined = "(no output)"
    preview, cut = _tail(combined, MAX_OUTPUT_BYTES)
    ok = result.returncode == 0
    if wid and user is not None and getattr(user, "id", None) is not None:
        _persist_run(
            workspace_id=wid,
            user=user,
            agent_run_id=agent_run_id,
            command=cmd,
            exit_code=int(result.returncode),
            ok=ok,
            output_preview=preview,
            error_message=None if ok else "non-zero exit",
        )
    return json.dumps(
        {
            "ok": ok,
            "exit_code": result.returncode,
            "truncated": cut,
            "output": preview,
            "verify_command": cmd[:500],
            "detail": "verify_command succeeded" if ok else "verify_command exited non-zero",
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "coding_workspace_verify": cast(Callable[..., str], coding_workspace_verify),
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_workspace_verify",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout in seconds (30–3600; default from server config)",
                    },
                },
            },
        },
    },
]
