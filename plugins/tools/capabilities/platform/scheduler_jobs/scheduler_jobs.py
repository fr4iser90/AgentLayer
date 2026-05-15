"""Create and list persisted scheduler jobs (IDE / server targets). Server-side RBAC."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure import scheduler_jobs_store
from apps.backend.dashboard.db import dashboard_access_ex

__version__ = "1.0.0"
TOOL_ID = "scheduler_jobs"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "meta"
TOOL_LABEL = "Scheduler jobs"
TOOL_DESCRIPTION = (
    "Create, list, or enable/disable persisted scheduler jobs (separate from the single operator "
    "tick in Admin → Interfaces). Use schedule_job_create to queue work for the IDE agent or server; "
    "schedule_job_list to inspect; schedule_job_set_enabled to pause/resume. "
    "execution_target ide_agent requires admin; dashboard-bound jobs require edit access to that dashboard."
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
    "schedule_job_create": {"min_role": "user", "capabilities": ("scheduler.job.write",)},
    "schedule_job_list": {"min_role": "user", "capabilities": ("scheduler.job.read",)},
    "schedule_job_set_enabled": {"min_role": "user", "capabilities": ("scheduler.job.write",)},
}

_MAX_INSTRUCTIONS = 32_000
_MAX_TITLE = 500
_VALID_TARGETS = frozenset({"server_periodic", "ide_agent"})


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


def schedule_job_create(arguments: dict[str, Any]) -> str:
    """Insert a scheduler_jobs row; ide_agent requires admin; optional dashboard_id."""
    idt = _identity()
    if not idt:
        return _err("missing identity — not authenticated")
    tenant_id, caller_uid = idt
    role = db.user_role(caller_uid)
    is_admin = role == "admin"

    raw_target = (arguments.get("execution_target") or "").strip().lower()
    if raw_target not in _VALID_TARGETS:
        return _err("execution_target must be server_periodic or ide_agent")

    if raw_target == "ide_agent" and not is_admin:
        return _err("execution_target ide_agent requires admin role")

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

    ide_wf: dict[str, Any] = {}
    if arguments.get("ide_workflow") is not None:
        try:
            from apps.backend.infrastructure.scheduler_jobs_workflow import normalize_ide_workflow

            ide_wf = normalize_ide_workflow(arguments.get("ide_workflow"))
        except (ValueError, TypeError) as e:
            return _err(str(e))
    elif raw_target == "ide_agent":
        from apps.backend.infrastructure.scheduler_jobs_workflow import normalize_ide_workflow

        ide_wf = normalize_ide_workflow({"use_pidea_scheduler_pipeline": True})

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
        ide_workflow=ide_wf,
    )
    if not row:
        return _err("failed to create job")
    return _ok({"job": scheduler_jobs_store.row_to_public(row)})


def schedule_job_list(arguments: dict[str, Any]) -> str:
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


def schedule_job_set_enabled(arguments: dict[str, Any]) -> str:
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
    "schedule_job_create": schedule_job_create,
    "schedule_job_list": schedule_job_list,
    "schedule_job_set_enabled": schedule_job_set_enabled,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "schedule_job_create",
            "TOOL_DESCRIPTION": (
                "Create a persisted scheduler job. execution_target: server_periodic (general server) or "
                "ide_agent (runs later in the IDE agent context) — ide_agent requires admin. "
                "instructions: what to do. Optional dashboard_id (UUID) to scope to a dashboard. "
                "Optional execution_user_id (UUID) — defaults to the current user (identity the job runs as). "
                "interval_minutes: 5–10080 (default 60). "
                "Optional ide_workflow (object): new_chat, prompt_preamble; optional git_repo_path, "
                "git_branch_template, git_source_branch; "
                "If ide_workflow is omitted and execution_target is ide_agent, use_pidea_scheduler_pipeline is on by "
                "default: new chat + task-analyze, then task-create in the same chat, then git branch, then new chat + "
                "task-execute (+ optional scheduler_pipeline_include_review). Or set ide_workflow explicitly: use_pidea_task_management_phases, "
                "phase_prompt_paths, pidea_workflow_name (JSON id), use_pidea_scheduler_pipeline, git_repo_path or "
                "project_path, git_branch_template."
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
                        "enum": ["server_periodic", "ide_agent"],
                        "TOOL_DESCRIPTION": "ide_agent requires admin.",
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
                    "ide_workflow": {
                        "type": "object",
                        "TOOL_DESCRIPTION": (
                            "Optional. Default for ide_agent (if omitted): use_pidea_scheduler_pipeline "
                            "(analyze → create → git → execute). Or: pidea_workflow_name (JSON workflow), "
                            "use_pidea_task_management_phases / phase_prompt_paths, "
                            "use_pidea_scheduler_pipeline false for a single message. "
                            "git_repo_path or project_path + git_branch_template for the branch step."
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
            "name": "schedule_job_list",
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
            "name": "schedule_job_set_enabled",
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
