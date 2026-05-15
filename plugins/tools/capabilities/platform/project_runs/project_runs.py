"""Create and list one-shot project runs (execution queue)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure import project_runs_store

__version__ = "0.1.0"
TOOL_ID = "project_runs"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "meta"
TOOL_LABEL = "Project runs"
TOOL_DESCRIPTION = "Create and inspect one-shot project runs (decoupled execution queue)."
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
    """Insert a project_runs row (one-shot)."""
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

    wf = arguments.get("ide_workflow")
    if wf is not None and not isinstance(wf, dict):
        return _err("ide_workflow must be an object when provided")

    row = project_runs_store.insert_run(
        tenant_id=tenant_id,
        created_by_user_id=caller_uid,
        execution_user_id=exec_uid,
        scheduler_job_id=None,
        dashboard_id=None,
        project_row_id=None,
        project_title=None,
        execution_target="ide_agent",
        instructions=instructions,
        ide_workflow=wf if isinstance(wf, dict) else {},
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
                "Create a one-shot IDE execution run (queued in project_runs). "
                "This does not create a schedule; it creates a single run for the execution worker."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {"type": "string"},
                    "execution_user_id": {"type": "string", "TOOL_DESCRIPTION": "Optional UUID; default caller."},
                    "ide_workflow": {"type": "object", "TOOL_DESCRIPTION": "Optional ide_workflow overrides."},
                },
                "required": ["instructions"],
            },
        },
    }
]

