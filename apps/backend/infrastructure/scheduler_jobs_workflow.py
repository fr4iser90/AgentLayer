"""Parse ``ide_workflow`` on ``scheduler_jobs`` (metadata; server-side PIDEA execution removed)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_PREAMBLE = 12_000
_MAX_JSON_BYTES = 24_000
_MAX_PHASES = 12
_ALLOWED_KEYS = frozenset(
    {
        "new_chat",
        "prompt_preamble",
        "git_repo_path",
        "git_branch_template",
        "git_source_branch",
        "project_path",
        "phase_prompt_paths",
        "use_pidea_task_management_phases",
        "pidea_workflow_name",
        "use_pidea_scheduler_pipeline",
        "scheduler_pipeline_include_review",
        "attach_task_plans_to_execute",
        "task_plan_glob",
        "task_plan_max_files",
        "task_plan_max_chars",
        "use_cdp_project_path",
    }
)


def ide_workflow_from_row(row: dict[str, Any]) -> dict[str, Any]:
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


def normalize_ide_workflow(raw: Any) -> dict[str, Any]:
    """Validate and normalize payload for DB (schedule_job_create)."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            raw = json.loads(s)
        except json.JSONDecodeError as e:
            raise ValueError("ide_workflow: invalid JSON") from e
    if not isinstance(raw, dict):
        raise ValueError("ide_workflow must be a JSON object")
    extra = set(raw.keys()) - _ALLOWED_KEYS
    if extra:
        raise ValueError(f"ide_workflow unknown keys: {sorted(extra)}")
    blob = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    if len(blob.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError("ide_workflow too large")
    out: dict[str, Any] = {}
    if "new_chat" in raw:
        out["new_chat"] = bool(raw["new_chat"])
    if raw.get("prompt_preamble") is not None:
        p = str(raw["prompt_preamble"])
        if len(p) > _MAX_PREAMBLE:
            raise ValueError("prompt_preamble too long")
        out["prompt_preamble"] = p
    if raw.get("git_repo_path"):
        out["git_repo_path"] = str(raw["git_repo_path"]).strip()
    if raw.get("git_branch_template"):
        out["git_branch_template"] = str(raw["git_branch_template"]).strip()
    if raw.get("git_source_branch"):
        out["git_source_branch"] = str(raw["git_source_branch"]).strip()
    if raw.get("project_path"):
        out["project_path"] = str(raw["project_path"]).strip()

    wf_name_in = raw.get("pidea_workflow_name")
    if wf_name_in is not None and str(wf_name_in).strip():
        raise ValueError(
            "pidea_workflow_name is not supported (server-side PIDEA removed; external IDE connector TBD)"
        )

    paths_in = raw.get("phase_prompt_paths")
    use_default = bool(raw.get("use_pidea_task_management_phases"))
    if paths_in is not None:
        if not isinstance(paths_in, list):
            raise ValueError("phase_prompt_paths must be a list of strings")
        if len(paths_in) > _MAX_PHASES:
            raise ValueError(f"phase_prompt_paths: at most {_MAX_PHASES} entries")
        cleaned: list[str] = []
        for p in paths_in:
            s = str(p).strip().replace("\\", "/").lstrip("/")
            if not s or ".." in s:
                raise ValueError("phase_prompt_paths: invalid path")
            if not s.endswith(".md"):
                raise ValueError("phase_prompt_paths: expected .md paths under content-library/prompts/")
            cleaned.append(s)
        out["phase_prompt_paths"] = cleaned
    elif use_default:
        raise ValueError(
            "use_pidea_task_management_phases is not supported (server-side PIDEA removed)"
        )

    if "use_pidea_scheduler_pipeline" in raw and bool(raw.get("use_pidea_scheduler_pipeline")):
        raise ValueError(
            "use_pidea_scheduler_pipeline is not supported (server-side PIDEA removed)"
        )

    if "attach_task_plans_to_execute" in raw:
        out["attach_task_plans_to_execute"] = bool(raw.get("attach_task_plans_to_execute"))
    if raw.get("task_plan_glob") is not None:
        tg = str(raw["task_plan_glob"]).strip().replace("\\", "/").lstrip("/")
        if len(tg) > 500:
            raise ValueError("task_plan_glob too long")
        if ".." in tg:
            raise ValueError("task_plan_glob must not contain ..")
        out["task_plan_glob"] = tg
    if "use_cdp_project_path" in raw:
        out["use_cdp_project_path"] = bool(raw.get("use_cdp_project_path"))

    for key, lo, hi in (
        ("task_plan_max_files", 1, 50),
        ("task_plan_max_chars", 2_000, 200_000),
    ):
        if raw.get(key) is not None:
            try:
                v = int(raw[key])
            except (TypeError, ValueError) as e:
                raise ValueError(f"ide_workflow {key} must be an integer") from e
            if v < lo or v > hi:
                raise ValueError(f"ide_workflow {key} must be between {lo} and {hi}")
            out[key] = v

    return out


def job_context_footer(row: dict[str, Any]) -> str:
    """Block with job metadata and extra instructions (for scheduler / IDE workflow context)."""
    lines: list[str] = ["---", "[Scheduler job context]"]
    t = (str(row.get("title") or "").strip()) or None
    if t:
        lines.append(f"Title: {t}")
    ws = row.get("dashboard_id")
    if ws is not None:
        lines.append(f"Dashboard id: {ws}")
    instr = str(row.get("instructions") or "").strip()
    if instr:
        lines.append("Additional instructions:")
        lines.append(instr[:31000])
    lines.append("---")
    return "\n".join(lines)


def compose_pidea_message(
    row: dict[str, Any],
    wf: dict[str, Any],
) -> str:
    """Build composer text: optional preamble + standard job block."""
    title = (str(row.get("title") or "").strip()) or None
    instr = str(row.get("instructions") or "").strip()
    parts: list[str] = []
    pre = (wf.get("prompt_preamble") or "").strip()
    if pre:
        parts.append(pre)
        parts.append("")
    parts.append("[Scheduled job — scheduler_jobs / ide_agent]")
    if title:
        parts.append(f"Title: {title}")
    ws = row.get("dashboard_id")
    if ws is not None:
        parts.append(f"Dashboard id: {ws}")
    parts.append("Instructions:")
    parts.append(instr[:31000])
    return "\n".join(parts).strip()


def run_optional_git_branch(
    row: dict[str, Any],
    wf: dict[str, Any],
    *,
    job_id_str: str,
) -> tuple[bool, str | None]:
    """
    Legacy hook for creating a git branch from ``ide_workflow``.

    Server-side automation no longer runs git here; callers treat skip as success so rows are not wedged.
    """
    _ = row, job_id_str
    tmpl = (wf.get("git_branch_template") or "").strip()
    repo_s = (wf.get("git_repo_path") or wf.get("project_path") or "").strip()
    if not tmpl and not repo_s:
        return True, None
    logger.warning(
        "ide_workflow: git branch step skipped (server-side IDE/git automation disabled; remove git_* fields if unused)"
    )
    return True, None
