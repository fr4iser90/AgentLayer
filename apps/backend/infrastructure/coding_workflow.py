"""``coding_workflow`` JSON on scheduler_jobs / project_runs (coding agent + workspace)."""

from __future__ import annotations

import json
from typing import Any

_MAX_PREAMBLE = 12_000
_MAX_JSON_BYTES = 24_000
_ALLOWED_KEYS = frozenset(
    {
        "workspace_id",
        "agent_id",
        "prompt_preamble",
    }
)
_VALID_AGENT_IDS = frozenset({"coding", "coding_plan"})


def workflow_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("coding_workflow")
    if raw is None:
        raw = row.get("ide_workflow")
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return d if isinstance(d, dict) else {}
    return {}


def normalize_coding_workflow(raw: Any, *, require_workspace: bool = False) -> dict[str, Any]:
    if raw is None:
        if require_workspace:
            raise ValueError("coding_workflow.workspace_id is required for coding_agent schedules")
        return {}
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            if require_workspace:
                raise ValueError("coding_workflow.workspace_id is required for coding_agent schedules")
            return {}
        try:
            raw = json.loads(s)
        except json.JSONDecodeError as e:
            raise ValueError("coding_workflow: invalid JSON") from e
    if not isinstance(raw, dict):
        raise ValueError("coding_workflow must be a JSON object")

    legacy_pidea = {
        "use_pidea_scheduler_pipeline",
        "use_pidea_task_management_phases",
        "pidea_workflow_name",
        "phase_prompt_paths",
        "scheduler_pipeline_include_review",
        "attach_task_plans_to_execute",
        "task_plan_glob",
        "task_plan_max_files",
        "task_plan_max_chars",
        "use_cdp_project_path",
        "new_chat",
        "git_repo_path",
        "git_branch_template",
        "git_source_branch",
        "project_path",
    }
    found_legacy = legacy_pidea & set(raw.keys())
    if found_legacy:
        raise ValueError(
            f"legacy IDE/PIDEA workflow keys are not supported: {sorted(found_legacy)}"
        )

    extra = set(raw.keys()) - _ALLOWED_KEYS
    if extra:
        raise ValueError(f"coding_workflow unknown keys: {sorted(extra)}")

    blob = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    if len(blob.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError("coding_workflow too large")

    out: dict[str, Any] = {}
    ws = raw.get("workspace_id")
    if ws is not None and str(ws).strip():
        try:
            import uuid

            out["workspace_id"] = str(uuid.UUID(str(ws).strip()))
        except (ValueError, TypeError) as e:
            raise ValueError("coding_workflow.workspace_id must be a UUID") from e
    elif require_workspace:
        raise ValueError("coding_workflow.workspace_id is required for coding_agent schedules")

    aid = raw.get("agent_id")
    if aid is not None and str(aid).strip():
        a = str(aid).strip().lower()
        if a not in _VALID_AGENT_IDS:
            raise ValueError("coding_workflow.agent_id must be coding or coding_plan")
        out["agent_id"] = a
    elif require_workspace:
        out["agent_id"] = "coding"

    if raw.get("prompt_preamble") is not None:
        p = str(raw["prompt_preamble"])
        if len(p) > _MAX_PREAMBLE:
            raise ValueError("prompt_preamble too long")
        out["prompt_preamble"] = p

    return out


def default_coding_workflow_for_create(workspace_id: str | None = None) -> dict[str, Any]:
    if not workspace_id or not str(workspace_id).strip():
        raise ValueError("workspace_id is required for coding_agent schedules")
    return normalize_coding_workflow(
        {"workspace_id": str(workspace_id).strip(), "agent_id": "coding"},
        require_workspace=True,
    )
