"""Create and list one-shot project runs (coding agent execution queue)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.coding_workflow import normalize_coding_workflow
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure import project_runs_store

__version__ = "0.1.0"
TOOL_ID = "project_runs"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "meta"
TOOL_LABEL = "Project runs"
TOOL_DESCRIPTION = "Create and inspect one-shot coding-agent project runs (decoupled execution queue)."
TOOL_TRIGGERS = ("run", "project run", "execute project", "run now", "one-shot")
TOOL_CAPABILITIES = ("project.run.read", "project.run.write")
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "project_run_create": {"min_role": "user", "capabilities": ("project.run.write",)},
}

_MAX_INSTRUCTIONS = 32_000


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (int(tid), uid)


def project_run_create(arguments: dict[str, Any]) -> str:
    """Insert a project_runs row (one-shot coding agent)."""
    idt = _identity()
    if not idt:
        return _err("missing identity — not authenticated")
    tenant_id, caller_uid = idt

    instructions = str(arguments.get("instructions") or "").strip()
    if not instructions:
        return _err("instructions is required")
    if len(instructions) > _MAX_INSTRUCTIONS:
        return _err("instructions too long")

    exec_uid_raw = arguments.get("execution_user_id")
    exec_uid = caller_uid
    if exec_uid_raw is not None and str(exec_uid_raw).strip():
        try:
            exec_uid = uuid.UUID(str(exec_uid_raw).strip())
        except (ValueError, TypeError):
            return _err("execution_user_id must be a UUID")
        if not db.user_by_id(exec_uid):
            return _err("execution_user_id unknown")

    wf_raw: dict[str, Any] = {}
    if arguments.get("coding_workflow") is not None:
        if not isinstance(arguments.get("coding_workflow"), dict):
            return _err("coding_workflow must be an object when provided")
        wf_raw = dict(arguments["coding_workflow"])
    ws_arg = arguments.get("workspace_id")
    if ws_arg is not None and str(ws_arg).strip():
        wf_raw.setdefault("workspace_id", str(ws_arg).strip())
    try:
        wf = normalize_coding_workflow(wf_raw, require_workspace=True)
    except (ValueError, TypeError) as e:
        return _err(str(e))

    row = project_runs_store.insert_run(
        tenant_id=tenant_id,
        created_by_user_id=caller_uid,
        execution_user_id=exec_uid,
        scheduler_job_id=None,
        dashboard_id=None,
        project_row_id=None,
        project_title=None,
        execution_target="coding",
        instructions=instructions,
        coding_workflow=wf,
    )
    if not row:
        return _err("failed to create run")
    return _ok({"run": project_runs_store.row_to_public(row)})


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "project_run_create": project_run_create,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "project_run_create",
            "TOOL_DESCRIPTION": (
                "Create a one-shot coding-agent execution run (queued in project_runs). "
                "Requires workspace_id. Does not create a recurring schedule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {"type": "string"},
                    "workspace_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Coding workspace UUID (required).",
                    },
                    "execution_user_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; default caller.",
                    },
                    "coding_workflow": {
                        "type": "object",
                        "TOOL_DESCRIPTION": "Optional: agent_id, prompt_preamble.",
                    },
                },
                "required": ["instructions", "workspace_id"],
            },
        },
    }
]
