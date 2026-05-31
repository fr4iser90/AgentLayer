"""Generic delegate-mode enforcement (artifact handoff, branch scope — no domain hardcoding)."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from apps.backend.domain.agent_task_prompt import parse_delegate_mode

_EDIT_TOOLS = frozenset(
    {
        "coding_write_file",
        "coding_edit",
        "coding_replace",
        "coding_apply_patch",
    }
)

_GENERAL_HANDOFF_BLOCK_TOOLS = frozenset(
    {
        "coding_search",
        "coding_semantic_search",
        "coding_list_dir",
        "coding_glob",
        "retrieve_context",
        "coding_symbols",
    }
)

_PATCH_PATH_RE = re.compile(r"^[+-]{3}\s+(?:a/|b/)?(.+)$")


def parse_requirement_value(requirements: Any, key: str) -> str | None:
    """Read ``branch: foo`` / ``mode: bar`` style entries from a requirements list."""
    if requirements is None:
        return None
    if isinstance(requirements, str):
        requirements = [requirements]
    if not isinstance(requirements, list):
        return None
    prefix = f"{key.lower().strip()}:"
    for ln in requirements:
        low = str(ln).lower().strip()
        if low.startswith(prefix):
            val = str(ln).split(":", 1)[1].strip()
            return val or None
    return None


def normalize_repo_path(path: str) -> str:
    p = str(path or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def paths_from_artifact_content(content: Any) -> list[str]:
    """Collect file paths from any artifact JSON (findings, path lists, etc.)."""
    if not isinstance(content, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        if not raw:
            return
        norm = normalize_repo_path(str(raw))
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)

    for key in ("paths", "high_paths", "target_paths", "files"):
        raw_list = content.get(key)
        if isinstance(raw_list, list):
            for item in raw_list:
                _add(item)

    findings = content.get("findings")
    if isinstance(findings, list):
        for row in findings:
            if isinstance(row, dict):
                _add(row.get("path"))

    return out


def load_delegate_allowed_paths(
    *,
    tenant_id: int,
    artifact_refs: Any,
    max_artifacts: int = 8,
) -> list[str]:
    from apps.backend.infrastructure import agent_artifacts_store

    ids: list[uuid.UUID] = []
    if isinstance(artifact_refs, str):
        artifact_refs = [artifact_refs]
    if isinstance(artifact_refs, list):
        for item in artifact_refs[:max_artifacts]:
            try:
                ids.append(uuid.UUID(str(item).strip()))
            except (ValueError, TypeError):
                continue

    paths: list[str] = []
    seen: set[str] = set()
    for aid in ids:
        row = agent_artifacts_store.get_artifact(artifact_id=aid, tenant_id=tenant_id)
        if not row:
            continue
        for p in paths_from_artifact_content(row.get("content") or {}):
            if p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def _delegate_mode(tool_context: dict[str, Any] | None) -> str:
    ctx = tool_context or {}
    mode = str(ctx.get("agent_delegate_mode") or ctx.get("agent_plan_delegate_mode") or "").strip().lower()
    return mode


def _path_allowed(path: str, allowed: list[str]) -> bool:
    norm = normalize_repo_path(path)
    if not norm or not allowed:
        return False
    return norm in {normalize_repo_path(ap) for ap in allowed}


def _edit_target_path(tool_name: str, args: dict[str, Any]) -> str | None:
    if tool_name == "coding_apply_patch":
        patch = str(args.get("patch_text") or args.get("patch") or "")
        for line in patch.splitlines():
            m = _PATCH_PATH_RE.match(line.strip())
            if m:
                return normalize_repo_path(m.group(1))
        return None
    for key in ("path", "file", "file_path"):
        raw = args.get(key)
        if raw:
            return normalize_repo_path(str(raw))
    return None


def _paths_in_patch_args(args: dict[str, Any]) -> list[str]:
    patch = str(args.get("patch_text") or args.get("patch") or "")
    paths: list[str] = []
    seen: set[str] = set()
    for line in patch.splitlines():
        m = _PATCH_PATH_RE.match(line.strip())
        if not m:
            continue
        p = normalize_repo_path(m.group(1))
        if p and p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


def _required_branch(tool_context: dict[str, Any] | None) -> str | None:
    ctx = tool_context or {}
    raw = ctx.get("agent_delegate_required_branch")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _git_branch_from_args(tool_name: str, args: dict[str, Any]) -> str | None:
    if tool_name == "coding_git_push":
        b = str(args.get("branch") or "").strip()
        return b or None
    if tool_name == "coding_bash":
        cmd = str(args.get("command") or "").strip()
        for pat in (
            r"\bgit\s+push(?:\s+-u)?(?:\s+\S+)?\s+(\S+)\s*$",
            r"\bgit\s+push(?:\s+-u)?\s+(?:origin|upstream)\s+(\S+)",
            r"\bgit\s+checkout\s+(?:-b\s+)?(\S+)",
        ):
            m = re.search(pat, cmd)
            if m:
                return m.group(1).strip()
    return None


def coding_delegate_tool_blocked(
    tool_name: str,
    args: dict[str, Any],
    tool_context: dict[str, Any] | None = None,
) -> str | None:
    """Enforce fix_from_artifact scope on the coding sub-agent."""
    if _delegate_mode(tool_context) != "fix_from_artifact":
        return None
    name = (tool_name or "").strip()
    ctx = tool_context or {}
    allowed = ctx.get("agent_delegate_allowed_paths")
    if not isinstance(allowed, list):
        allowed = []
    allowed_norm = [normalize_repo_path(str(p)) for p in allowed if str(p).strip()]

    if not allowed_norm:
        return (
            "fix_from_artifact: no paths in referenced artifacts. "
            "Pass artifact_refs from the prior specialist run, or list paths in the artifact content."
        )

    if name in _EDIT_TOOLS:
        if name == "coding_apply_patch":
            patch_paths = _paths_in_patch_args(args)
            if not patch_paths:
                return "fix_from_artifact: patch must touch paths listed in referenced artifacts only."
            bad = [p for p in patch_paths if not _path_allowed(p, allowed_norm)]
            if bad:
                return (
                    f"fix_from_artifact: patch touches {bad!r} which is not in artifact scope {allowed_norm!r}."
                )
        else:
            target = _edit_target_path(name, args)
            if target and not _path_allowed(target, allowed_norm):
                return (
                    f"fix_from_artifact: edit path {target!r} is not in artifact scope {allowed_norm!r}. "
                    "Fix only paths from [Referenced artifacts]."
                )

    req_branch = _required_branch(tool_context)
    if req_branch and name in ("coding_git_push", "coding_bash"):
        used = _git_branch_from_args(name, args)
        if used and used != req_branch:
            return (
                f"fix_from_artifact: required branch is {req_branch!r} but tool targets {used!r}. "
                f"Checkout {req_branch!r}, commit there, and push that branch."
            )

    return None


def general_orchestrator_tool_blocked(
    tool_name: str,
    args: dict[str, Any],
    tool_context: dict[str, Any] | None = None,
) -> str | None:
    """When a prior step left artifact handoff pending, block General read exploration."""
    ctx = tool_context or {}
    pending = ctx.get("orchestrator_pending_artifact_refs")
    if not isinstance(pending, list) or not pending:
        return None
    name = (tool_name or "").strip()
    if name not in _GENERAL_HANDOFF_BLOCK_TOOLS:
        return None
    ids = ", ".join(str(x) for x in pending[:5])
    return (
        f"A prior specialist step produced artifact_id(s) for implementation ({ids}). "
        "Call agent_delegate with agent_id=coding, artifact_refs, and requirements "
        "(mode: fix_from_artifact, branch: <name>) — do not explore the repo with read/search tools."
    )


def extract_handoff_artifact_ids(result: str) -> list[str]:
    """Artifact ids intended for the next delegate step (from tool JSON or delegate payload)."""
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict) or data.get("ok") is False:
        return []
    handoff = data.get("handoff_artifact_ids")
    if isinstance(handoff, list):
        out = [str(x).strip() for x in handoff if str(x).strip()]
        if out:
            return out
    return extract_artifact_ids_from_tool_result(result)


def extract_artifact_ids_from_tool_result(result: str) -> list[str]:
    """Pull artifact_id from specialist tool JSON (any integration)."""
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict) or data.get("ok") is False:
        return []
    out: list[str] = []
    aid = data.get("artifact_id")
    if aid:
        out.append(str(aid).strip())
    arts = data.get("artifact_ids")
    if isinstance(arts, list):
        for item in arts:
            s = str(item).strip()
            if s:
                out.append(s)
    return [x for x in out if x]


def subagent_reject_reason(
    *,
    agent_id: str,
    requirements: Any,
) -> str | None:
    """Reject invalid specialist + mode combinations before spawning a sub-run."""
    mode = parse_delegate_mode(requirements)
    if mode == "fix_from_artifact" and agent_id == "coding_plan":
        return (
            "coding_plan is read-only. For fix_from_artifact use agent_delegate with agent_id=coding, "
            "artifact_refs from the prior run, and requirements including mode: fix_from_artifact and branch: <name>."
        )
    return None
