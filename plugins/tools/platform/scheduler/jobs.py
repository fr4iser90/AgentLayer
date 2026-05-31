"""Create and list persisted scheduler jobs (coding agent / server targets). Server-side RBAC."""

from __future__ import annotations

import builtins
import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db
from apps.backend.domain.scheduler_targets import (
    agent_requires_workspace_for_target,
    execution_target_error,
    is_valid_execution_target,
    normalize_execution_target,
    schedule_permission_error,
)
from apps.backend.infrastructure import scheduler_jobs_store
from apps.backend.dashboard.db import dashboard_access_ex

__version__ = "1.0.0"
TOOL_ID = "scheduler_jobs"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "scheduler"
TOOL_LABEL = "Scheduler jobs"
TOOL_DESCRIPTION = (
    "Create, list, or enable/disable persisted scheduler jobs (separate from the single operator "
    "tick in Admin → Interfaces). Use schedule_job_create to queue work for the coding agent or server; "
    "schedule_job_list to inspect; schedule_job_set_enabled to pause/resume. "
    "execution_target is a registry agent_id (see schedule_job_list / execution-targets catalog); "
    "workspace agents need workspace_id; admin-only agents need admin role."
)
TOOL_TRIGGERS = (
    "schedule",
    "scheduler",
    "cron",
    "job",
    "ide agent",
    "recurring",
    "scheduler_jobs",
)
TOOL_CAPABILITIES = ("scheduler.job.read", "scheduler.job.write")
TOOL_MIN_ROLE = "user"
AGENT_TOOL_META_BY_NAME = {
    "create": {"min_role": "user", "capabilities": ("scheduler.job.write",)},
    "list": {"min_role": "user", "capabilities": ("scheduler.job.read",)},
    "set_enabled": {"min_role": "user", "capabilities": ("scheduler.job.write",)},
}

_MAX_INSTRUCTIONS = 32_000
_MAX_TITLE = 500


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    d = {"ok": True, **payload}
    return json.dumps(d, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (int(tid), uid)


def _dashboard_allows_schedule(tenant_id: int, user_id: uuid.UUID, dashboard_id: uuid.UUID) -> bool:
    d = dashboard_access_ex(user_id, tenant_id, dashboard_id)
    if d.role is None:
        return False
    if d.allowed_block_ids is None:
        return d.role in ("owner", "co_owner", "editor")
    return bool(d.granular_can_write)


def _parse_uuid(s: Any, *, field: str) -> uuid.UUID | None:
    if s is None or (isinstance(s, str) and not str(s).strip()):
        return None
    try:
        return uuid.UUID(str(s).strip())
    except (ValueError, TypeError):
        return None


def create(arguments: dict[str, Any]) -> str:
    """Insert a scheduler_jobs row; workspace agents need workspace_id; optional dashboard_id."""
    idt = _identity()
    if not idt:
        return _err("missing identity — not authenticated")
    tenant_id, caller_uid = idt
    role = db.user_role(caller_uid)
    is_admin = role == "admin"

    raw_target = normalize_execution_target(arguments.get("execution_target"))
    if not raw_target or not is_valid_execution_target(raw_target):
        return _err(execution_target_error(arguments.get("execution_target")))

    perm_err = schedule_permission_error(user_role=role or "user", execution_target=raw_target or "")
    if perm_err:
        return _err(perm_err)

    instructions = str(arguments.get("instructions") or "").strip()
    if not instructions:
        return _err("instructions is required")
    if len(instructions) > _MAX_INSTRUCTIONS:
        return _err("instructions too long")

    title_raw = arguments.get("title")
    title = str(title_raw).strip()[:_MAX_TITLE] if title_raw is not None else None
    if title == "":
        title = None

    interval = arguments.get("interval_minutes")
    try:
        interval_m = int(interval) if interval is not None else 60
    except (TypeError, ValueError):
        return _err("interval_minutes must be an integer")
    if interval_m < 5 or interval_m > 10080:
        return _err("interval_minutes must be between 5 and 10080")

    exec_uid = _parse_uuid(arguments.get("execution_user_id"), field="execution_user_id")
    if exec_uid is None:
        exec_uid = caller_uid
    elif not scheduler_jobs_store.user_belongs_to_tenant(exec_uid, tenant_id):
        return _err("execution_user_id must be a user in your tenant")

    ws_raw = arguments.get("dashboard_id")
    dashboard_id: uuid.UUID | None = _parse_uuid(ws_raw, field="dashboard_id")
    if ws_raw is not None and str(ws_raw).strip() and dashboard_id is None:
        return _err("invalid dashboard_id UUID")
    if dashboard_id is not None:
        if not _dashboard_allows_schedule(tenant_id, caller_uid, dashboard_id):
            return _err("no permission to attach a schedule to this dashboard")

    from apps.backend.infrastructure.coding_workflow import normalize_coding_workflow

    wf_raw: dict[str, Any] = {}
    if arguments.get("coding_workflow") is not None:
        if not isinstance(arguments.get("coding_workflow"), dict):
            return _err("coding_workflow must be an object")
        wf_raw = dict(arguments["coding_workflow"])
    ws_arg = arguments.get("workspace_id")
    if ws_arg is not None and str(ws_arg).strip():
        wf_raw.setdefault("workspace_id", str(ws_arg).strip())
    try:
        coding_wf = normalize_coding_workflow(
            wf_raw, require_workspace=agent_requires_workspace_for_target(raw_target)
        )
    except (ValueError, TypeError) as e:
        return _err(str(e))

    row = scheduler_jobs_store.insert_job(
        tenant_id=tenant_id,
        created_by_user_id=caller_uid,
        execution_user_id=exec_uid,
        dashboard_id=dashboard_id,
        execution_target=raw_target,
        title=title,
        instructions=instructions,
        interval_minutes=interval_m,
        enabled=bool(arguments.get("enabled", True)),
        coding_workflow=coding_wf,
    )
    if not row:
        return _err("failed to create job")
    return _ok({"job": scheduler_jobs_store.row_to_public(row)})


def list(arguments: dict[str, Any]) -> str:
    idt = _identity()
    if not idt:
        return _err("missing identity — not authenticated")
    tenant_id, caller_uid = idt
    is_admin = db.user_role(caller_uid) == "admin"

    ws = _parse_uuid(arguments.get("dashboard_id"), field="dashboard_id")
    if arguments.get("dashboard_id") is not None and str(arguments.get("dashboard_id")).strip() and ws is None:
        return _err("invalid dashboard_id UUID")

    try:
        lim = int(arguments.get("limit", 50))
    except (TypeError, ValueError):
        lim = 50

    rows = scheduler_jobs_store.list_jobs_for_user(
        tenant_id=tenant_id,
        current_user_id=caller_uid,
        is_admin=is_admin,
        dashboard_id=ws,
        limit=lim,
    )
    return _ok(
        {
            "jobs": [scheduler_jobs_store.row_to_public(r) for r in rows],
            "count": len(rows),
        }
    )


def set_enabled(arguments: dict[str, Any]) -> str:
    idt = _identity()
    if not idt:
        return _err("missing identity — not authenticated")
    tenant_id, caller_uid = idt
    is_admin = db.user_role(caller_uid) == "admin"

    jid = _parse_uuid(arguments.get("job_id"), field="job_id")
    if jid is None:
        return _err("job_id is required (UUID)")

    if "enabled" not in arguments:
        return _err("enabled is required (boolean)")

    en = bool(arguments.get("enabled"))
    row = scheduler_jobs_store.set_enabled(
        job_id=jid,
        tenant_id=tenant_id,
        enabled=en,
        actor_user_id=caller_uid,
        actor_is_admin=is_admin,
    )
    if not row:
        return _err("job not found or not allowed to change")
    return _ok({"job": scheduler_jobs_store.row_to_public(row)})


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "create": create,
    "list": list,
    "set_enabled": set_enabled,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create",
            "TOOL_DESCRIPTION": (
                "Create a persisted scheduler job. execution_target: registry agent_id "
                "(e.g. general, coding, coding_plan, security_auditor — see GET /v1/user/scheduler-jobs/execution-targets). "
                "Workspace agents need workspace_id or coding_workflow.workspace_id. "
                "Optional coding_workflow: agent_id, prompt_preamble. "
                "instructions: what to do. Optional dashboard_id (UUID). interval_minutes: 5–10080 (default 60)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Task description for the executing agent.",
                    },
                    "execution_target": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Registry agent_id (general, coding, coding_plan, security_auditor, …).",
                    },
                    "title": {"type": "string", "TOOL_DESCRIPTION": "Short label (optional)."},
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID of user_dashboards row; requires edit access.",
                    },
                    "execution_user_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID — user context for execution; default is caller.",
                    },
                    "interval_minutes": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "5–10080; default 60.",
                    },
                    "enabled": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Default true.",
                    },
                    "workspace_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Workspace UUID (required for workspace agents).",
                    },
                    "coding_workflow": {
                        "type": "object",
                        "TOOL_DESCRIPTION": (
                            "Optional overrides: workspace_id, agent_id (coding|coding_plan), prompt_preamble."
                        ),
                    },
                },
                "required": ["instructions", "execution_target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list",
            "TOOL_DESCRIPTION": (
                "List scheduler jobs in your tenant. Non-admins see jobs they created or that target them "
                "as execution user. Optional dashboard_id filter."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string", "TOOL_DESCRIPTION": "Optional filter UUID."},
                    "limit": {"type": "integer", "TOOL_DESCRIPTION": "Max rows (default 50, max 200)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_enabled",
            "TOOL_DESCRIPTION": "Enable or disable a job by id. Creator or admin only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "TOOL_DESCRIPTION": "Job UUID."},
                    "enabled": {"type": "boolean"},
                },
                "required": ["job_id", "enabled"],
            },
        },
    },
]
