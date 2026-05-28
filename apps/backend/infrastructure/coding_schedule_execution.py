"""Run scheduled / queued work via the coding agent (``chat_completion`` + workspace)."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from apps.backend.domain.agent import WorkspaceAccessDenied, chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.domain.schedule_run_context import (
    begin_schedule_run_collection,
    get_schedule_abort_reason,
    get_schedule_tool_events,
    reset_schedule_run_collection,
)
from apps.backend.infrastructure.coding_workflow import workflow_from_row
from apps.backend.infrastructure.doc_maintenance import (
    DOC_PROFILE_PATH,
    REPORT_PATH,
    build_doc_maintenance_instructions,
    mode_summary_line,
    parse_doc_maintenance_mode,
)
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_MAX_INSTRUCTIONS = 31_000
_SCHEDULE_MODEL_PROFILE = "coding"
_SCHEDULE_PROVIDER_ORDER = ("llama_cpp", "ollama")

# Fixed tool set for background schedules (avoids ranking dropping git/write tools).
CODING_SCHEDULE_TOOL_ALLOWLIST: tuple[str, ...] = (
    "coding_git_read",
    "coding_git_sync",
    "coding_read_file",
    "coding_write_file",
    "coding_replace",
    "coding_edit",
    "coding_apply_patch",
    "coding_list_dir",
    "coding_glob",
    "coding_bash",
    "coding_workspace_verify",
    "get_tool_help",
)

SECURITY_SCAN_TOOL_NAMES: tuple[str, ...] = (
    "security_scan_finding_policy_schema",
    "security_scan_resolve",
    "security_scan_status",
    "security_scan_get",
    "security_scan_findings",
    "security_scan_agent_callback",
    "security_scan_targets_list",
    "security_scan_list",
    "security_scan_start",
)

_WRITE_TOOLS = frozenset(
    {
        "coding_write_file",
        "coding_replace",
        "coding_edit",
        "coding_apply_patch",
    }
)


def _provider_configured(provider_id: str) -> bool:
    from apps.backend.infrastructure.model_catalog_providers import get_provider_spec

    spec = get_provider_spec(provider_id)
    return spec is not None and bool(spec.base_url.strip())


def _pick_schedule_catalog_provider() -> str | None:
    """
    Prefer a reachable coding stack for background jobs (llama.cpp before Ollama).

    Falls back to the first configured provider when health probes fail.
    Override with env ``AGENT_SCHEDULE_LLM_PROVIDER`` (e.g. ``ollama`` when only Ollama is up).
    """
    import os

    from apps.backend.infrastructure.model_catalog_providers import fetch_full_model_catalog
    from apps.backend.infrastructure.operator_settings import normalize_model_catalog_owned_by

    raw = (os.environ.get("AGENT_SCHEDULE_LLM_PROVIDER") or "").strip()
    if raw:
        forced = normalize_model_catalog_owned_by(raw)
        if forced and _provider_configured(forced):
            return forced

    _, agentlayer = fetch_full_model_catalog()
    for pid in _SCHEDULE_PROVIDER_ORDER:
        if not _provider_configured(pid):
            continue
        meta = agentlayer.get(pid)
        if isinstance(meta, dict) and meta.get("reachable") is True:
            return pid

    for pid in _SCHEDULE_PROVIDER_ORDER:
        if _provider_configured(pid):
            return pid
    return None


def _schedule_llm_body_fields(workflow: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """``chat_completion`` body fields + ``model_profile_header`` (no bare OLLAMA_DEFAULT_MODEL override)."""
    from apps.backend.infrastructure.operator_settings import normalize_model_catalog_owned_by

    extras: dict[str, Any] = {}

    explicit_owned = workflow.get("model_catalog_owned_by")
    if explicit_owned is not None and str(explicit_owned).strip():
        ob = normalize_model_catalog_owned_by(explicit_owned)
        if ob:
            extras["agent_model_catalog_owned_by"] = ob

    explicit_model = workflow.get("model")
    if explicit_model is not None and str(explicit_model).strip():
        extras["model"] = str(explicit_model).strip()[:256]
    else:
        extras["model"] = _SCHEDULE_MODEL_PROFILE

    if "agent_model_catalog_owned_by" not in extras:
        owned = _pick_schedule_catalog_provider()
        if owned:
            extras["agent_model_catalog_owned_by"] = owned
            logger.info("schedule LLM: using catalog provider %r", owned)

    return extras, _SCHEDULE_MODEL_PROFILE


def _parse_uuid(v: Any) -> uuid.UUID | None:
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v).strip())
    except (ValueError, TypeError):
        return None


def _extract_assistant_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return ""
    c = msg.get("content")
    return c.strip() if isinstance(c, str) else ""


def _resolve_doc_maintenance_instructions(
    *,
    workflow: dict[str, Any],
    title: str | None,
    stored_instructions: str,
) -> tuple[str, str | None]:
    """
    Return (instructions, mode) for doc maintenance jobs.

    When ``coding_workflow.doc_maintenance_mode`` is set, use canonical template.
    Otherwise for detected doc jobs, prepend mode preamble to stored instructions.
    """
    mode = parse_doc_maintenance_mode(workflow)
    explicit = workflow.get("doc_maintenance_mode") is not None
    if explicit:
        return build_doc_maintenance_instructions(mode), mode
    if _is_doc_maintenance_job(title, stored_instructions):
        preamble = mode_summary_line(mode) + f"\nRead/update `{DOC_PROFILE_PATH}` when present.\n\n"
        return preamble + stored_instructions, mode
    return stored_instructions, None


def _schedule_user_message(*, title: str | None, doc_mode: str | None = None) -> str:
    lines = [
        "Run this scheduled coding task now.",
        f"Execute the system instructions in order: git pull (ff-only), update `{REPORT_PATH}`, "
        f"update `{DOC_PROFILE_PATH}` after inventory, then apply limited doc/README edits.",
        "For every tool call, pass a JSON object with all required fields from the tool schema "
        '(e.g. coding_write_file: {"path": "docs/MAINTENANCE_REPORT.md", "content": "..."}).',
    ]
    if doc_mode:
        lines.append(f"Doc maintenance mode: {doc_mode}")
    if title:
        lines.append(f"Job title: {title}")
    return "\n".join(lines)


class _WsUser:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid


def _workspace_disk_path(ws_id: uuid.UUID, user_id: uuid.UUID) -> Path | None:
    from apps.backend.domain.workspace_resolver import resolve_workspace

    ws = resolve_workspace(str(ws_id), _WsUser(user_id))
    if not ws:
        return None
    raw = ws.get("repo_path") or ws.get("path")
    if not raw:
        return None
    p = Path(str(raw))
    return p if p.is_dir() else None


def _is_doc_maintenance_job(title: str | None, instructions: str) -> bool:
    blob = f"{title or ''}\n{instructions}".lower()
    return "doc maintenance" in blob or "docs/maintenance_report" in blob


def _is_security_remediation_job(
    title: str | None, instructions: str, workflow: dict[str, Any]
) -> bool:
    if workflow.get("security_scan"):
        return True
    blob = f"{title or ''}\n{instructions}".lower()
    return (
        "security remediation" in blob
        or "security_remediation" in blob
        or "simplesec" in blob
        or "security_scan_start" in blob
        or "docs/security_report" in blob
    )


def _schedule_tool_allowlist(
    workflow: dict[str, Any], title: str | None, instructions: str
) -> list[str]:
    names = list(CODING_SCHEDULE_TOOL_ALLOWLIST)
    if _is_security_remediation_job(title, instructions, workflow):
        for t in SECURITY_SCAN_TOOL_NAMES:
            if t not in names:
                names.append(t)
    return names


def _evaluate_run_status(
    *,
    tools: list[dict[str, Any]],
    git_summary: dict[str, Any] | None,
    is_doc_job: bool,
    abort_reason: str | None = None,
) -> tuple[str, str]:
    """
    Return (status, outcome_key).

    status: succeeded | partial | failed (failed only set by caller on exception)
    """
    if abort_reason:
        return "failed", abort_reason

    pull_repeats = sum(
        1
        for t in tools
        if t.get("name") == "coding_bash"
        and isinstance(t.get("args"), dict)
        and "git pull" in str(t["args"].get("command") or "").lower()
    )
    if pull_repeats >= 3:
        return "failed", "repeated_git_pull"

    files_changed = []
    if git_summary and git_summary.get("ok"):
        files_changed = list(git_summary.get("files") or [])

    doc_paths = {
        str(f.get("path") or "")
        for f in files_changed
        if isinstance(f, dict) and f.get("path")
    }
    doc_write_ok = any(
        t.get("name") in _WRITE_TOOLS
        and t.get("ok")
        and isinstance(t.get("args"), dict)
        and (
            str(t["args"].get("path") or "").startswith("docs/")
            or str(t["args"].get("path") or "") in ("README.md", "README")
        )
        for t in tools
    )
    has_git_changes = bool(git_summary and git_summary.get("has_changes"))
    report_touched = REPORT_PATH in doc_paths or any(
        p.endswith("MAINTENANCE_REPORT.md") for p in doc_paths
    )
    profile_touched = DOC_PROFILE_PATH in doc_paths or any(
        p.endswith("DOC_PROFILE.md") for p in doc_paths
    )

    if is_doc_job:
        if has_git_changes or report_touched or profile_touched or doc_write_ok:
            return "succeeded", "docs_touched"
        return "partial", "no_doc_changes"

    if has_git_changes or any(t.get("name") in _WRITE_TOOLS and t.get("ok") for t in tools):
        return "succeeded", "workspace_changed"
    if tools:
        return "partial", "no_workspace_changes"
    return "partial", "no_tools_run"


def _build_summary(
    *,
    tools: list[dict[str, Any]],
    git_summary: dict[str, Any] | None,
    final_reply: str,
    outcome: str,
    agent_run_id: str | None,
    duration_ms: int,
) -> dict[str, Any]:
    files_changed: list[dict[str, str]] = []
    git_block: dict[str, Any] | None = None
    if git_summary and git_summary.get("is_git_repo"):
        git_block = {
            "branch": git_summary.get("branch"),
            "has_changes": git_summary.get("has_changes"),
        }
        files_changed = list(git_summary.get("files") or [])

    return {
        "tools": tools,
        "tool_count": len(tools),
        "files_changed": files_changed,
        "git": git_block,
        "outcome": outcome,
        "final_reply_excerpt": (final_reply or "")[:2000],
        "agent_run_id": agent_run_id,
        "duration_ms": duration_ms,
    }


async def run_coding_schedule_row(
    row: dict[str, Any],
    *,
    row_kind: str = "scheduler_job",
) -> tuple[bool, str | None]:
    """
    Execute instructions with agent_id + workspace_id from ``coding_workflow`` / legacy column.

    Returns (success, error_message). ``success`` is True for succeeded and partial runs
    (agent finished without exception); partial means no detectable doc/workspace edits.
    """
    from apps.backend.infrastructure import scheduler_job_runs_store

    tenant_id = int(row.get("tenant_id") or 0)
    user_id = _parse_uuid(row.get("execution_user_id"))
    if user_id is None:
        return False, "missing execution_user_id"

    job_id = _parse_uuid(row.get("id"))
    wf = workflow_from_row(row)
    ws_id = _parse_uuid(wf.get("workspace_id"))
    if ws_id is None:
        return False, "coding_workflow.workspace_id is required"

    from apps.backend.domain.scheduler_targets import is_agent_schedulable, normalize_execution_target

    exec_agent = normalize_execution_target(str(row.get("execution_target") or "")) or ""
    wf_agent = str(wf.get("agent_id") or "").strip().lower()
    agent_id = exec_agent or wf_agent or "coding"
    if wf_agent and exec_agent and wf_agent != exec_agent:
        logger.info(
            "schedule: using execution_target agent_id=%r (workflow had agent_id=%r)",
            exec_agent,
            wf_agent,
        )
    if not is_agent_schedulable(agent_id):
        return False, f"non-schedulable agent_id: {agent_id}"

    title = (str(row.get("title") or "").strip()) or None
    stored_instr = str(row.get("instructions") or "").strip()
    if not stored_instr:
        return False, "empty instructions"

    instr, doc_mode = _resolve_doc_maintenance_instructions(
        workflow=wf,
        title=title,
        stored_instructions=stored_instr,
    )
    is_doc_job = _is_doc_maintenance_job(title, instr) or doc_mode is not None
    run_row: dict[str, Any] | None = None
    run_id: uuid.UUID | None = None
    if job_id is not None and row_kind == "scheduler_job":
        run_row = scheduler_job_runs_store.insert_run_start(
            scheduler_job_id=job_id,
            tenant_id=tenant_id,
            execution_user_id=user_id,
            workspace_id=ws_id,
            agent_id=agent_id,
        )
        run_id = _parse_uuid(run_row.get("id") if run_row else None)

    preamble = str(wf.get("prompt_preamble") or "").strip()
    dash = row.get("dashboard_id")
    parts: list[str] = [
        f"You are executing a persisted {row_kind} (coding agent on workspace {ws_id}).",
        "Follow the instructions. Apply changes in the workspace when appropriate.",
    ]
    if title:
        parts.append(f"Title: {title}")
    if dash is not None:
        parts.append(f"Dashboard scope (id): {dash}")
    if preamble:
        parts.append(f"Additional context:\n{preamble[:12000]}")
    parts.append(f"Instructions:\n{instr[:_MAX_INSTRUCTIONS]}")
    sys_prompt = "\n\n".join(parts)

    llm_fields, model_profile = _schedule_llm_body_fields(wf)
    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": _schedule_user_message(title=title, doc_mode=doc_mode)},
        ],
        "stream": False,
        "agent_id": agent_id,
        "workspace_id": str(ws_id),
        "TOOL_DOMAIN": "coding",
        # Background schedules have no WebSocket control_queue — never gate on permission UI.
        "agent_permission_ask": False,
        "agent_unattended": True,
        "agent_tools_full_schema": True,
        "agent_tool_name_allowlist": _schedule_tool_allowlist(wf, title, instr),
        "agent_tools_ranking_enabled": False,
        **llm_fields,
    }

    role = db.user_role(user_id)
    id_tok = set_identity(tenant_id, user_id)
    collect_tokens: tuple | None = None
    t0 = time.monotonic()
    data: dict[str, Any] = {}
    err_msg: str | None = None
    agent_run_id: str | None = None
    tools: list[dict[str, Any]] = []
    abort_reason: str | None = None

    if run_id is not None:
        collect_tokens = begin_schedule_run_collection(run_id)

    try:
        data = await chat_completion(
            body,
            bearer_user_role=role if role in ("user", "admin") else None,
            model_profile_header=model_profile,
        )
        if isinstance(data, dict):
            agent_run_id = str(data.get("agent_run_id") or "") or None
    except WorkspaceAccessDenied as e:
        err_msg = str(e) or "workspace access denied"
    except Exception as e:
        logger.exception("coding schedule failed row_kind=%s user=%s", row_kind, user_id)
        err_msg = str(e)[:2000] if str(e) else "coding agent run failed"
    finally:
        if run_id is not None:
            tools = get_schedule_tool_events()
        abort_reason = get_schedule_abort_reason()
        reset_identity(id_tok)
        if collect_tokens is not None:
            reset_schedule_run_collection(collect_tokens[0], collect_tokens[1])

    duration_ms = int((time.monotonic() - t0) * 1000)

    git_summary: dict[str, Any] | None = None
    root = _workspace_disk_path(ws_id, user_id)
    if root is not None:
        try:
            from apps.backend.infrastructure.workspace_git import workspace_git_changes_summary

            git_summary = workspace_git_changes_summary(root)
        except Exception:
            logger.warning("schedule run: git summary failed", exc_info=True)

    final_reply = _extract_assistant_text(data if isinstance(data, dict) else {})

    if run_id is not None and job_id is not None:
        if err_msg:
            status = "failed"
            outcome = "error"
            summary = _build_summary(
                tools=tools,
                git_summary=git_summary,
                final_reply=final_reply,
                outcome=outcome,
                agent_run_id=agent_run_id,
                duration_ms=duration_ms,
            )
            scheduler_job_runs_store.finish_run(
                run_id=run_id,
                tenant_id=tenant_id,
                status=status,
                error=err_msg,
                summary=summary,
            )
            return False, err_msg

        status, outcome = _evaluate_run_status(
            tools=tools,
            git_summary=git_summary,
            is_doc_job=is_doc_job,
            abort_reason=abort_reason,
        )
        summary = _build_summary(
            tools=tools,
            git_summary=git_summary,
            final_reply=final_reply,
            outcome=outcome,
            agent_run_id=agent_run_id,
            duration_ms=duration_ms,
        )
        scheduler_job_runs_store.finish_run(
            run_id=run_id,
            tenant_id=tenant_id,
            status=status,
            error=None,
            summary=summary,
        )
        if status == "failed":
            return False, err_msg or outcome or "schedule run failed"
        return True, None

    if err_msg:
        return False, err_msg
    return True, None
