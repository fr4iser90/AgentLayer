"""Generic delegate-mode enforcement (artifact handoff, branch scope — no domain hardcoding)."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from apps.backend.domain.agent_task_prompt import parse_delegate_mode

_CAP_REPO_WRITE = frozenset({"coding.write"})
_CAP_REPO_EXECUTE = frozenset({"coding.execute"})

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


def _tool_capability_set(tool_name: str) -> frozenset[str]:
    from apps.backend.domain.plugin_system.capability_index import effective_capabilities_for_tool
    from apps.backend.domain.plugin_system.registry import get_registry

    meta = get_registry().meta_entry_for_tool_name((tool_name or "").strip())
    if not meta:
        return frozenset()
    return frozenset(c.lower() for c in effective_capabilities_for_tool(meta, tool_name) if c)


def _path_from_args(args: dict[str, Any]) -> str | None:
    for key in ("path", "file", "file_path"):
        raw = args.get(key)
        if raw:
            return normalize_repo_path(str(raw))
    return None


def _repo_paths_from_args(args: dict[str, Any]) -> list[str]:
    patch_paths = _paths_in_patch_args(args)
    if patch_paths:
        return patch_paths
    single = _path_from_args(args)
    return [single] if single else []


def _looks_like_git_publish_args(args: dict[str, Any]) -> bool:
    if str(args.get("branch") or "").strip():
        return True
    if str(args.get("remote") or "").strip():
        return True
    cmd = str(args.get("command") or "").strip()
    return bool(re.search(r"\bgit\s+push", cmd))


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


def _git_branch_from_args(args: dict[str, Any]) -> str | None:
    b = str(args.get("branch") or "").strip()
    if b:
        return b
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
    """Enforce fix_from_artifact scope on the coding sub-agent (capabilities + args, no tool lists)."""
    if _delegate_mode(tool_context) != "fix_from_artifact":
        return None
    ctx = tool_context or {}
    allowed = ctx.get("agent_delegate_allowed_paths")
    if not isinstance(allowed, list):
        allowed = []
    allowed_norm = [normalize_repo_path(str(p)) for p in allowed if str(p).strip()]
    caps = _tool_capability_set(tool_name)

    if not allowed_norm:
        if caps & _CAP_REPO_WRITE:
            return (
                "fix_from_artifact: no paths in referenced artifacts. "
                "Pass artifact_refs from the prior specialist run, or list paths in the artifact content."
            )
        if caps & _CAP_REPO_EXECUTE and _looks_like_git_publish_args(args):
            return (
                "fix_from_artifact: no paths in referenced artifacts. "
                "Pass artifact_refs from the prior specialist run, or list paths in the artifact content."
            )
        return None

    if caps & _CAP_REPO_WRITE:
        paths = _repo_paths_from_args(args)
        if not paths:
            return "fix_from_artifact: write must touch paths listed in referenced artifacts only."
        bad = [p for p in paths if not _path_allowed(p, allowed_norm)]
        if bad:
            return (
                f"fix_from_artifact: write touches {bad!r} which is not in artifact scope {allowed_norm!r}."
            )

    req_branch = _required_branch(tool_context)
    if req_branch and caps & _CAP_REPO_EXECUTE:
        used = _git_branch_from_args(args)
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
    """When artifact handoff is pending, only allow the next delegate step."""
    del args
    ctx = tool_context or {}
    pending = ctx.get("orchestrator_pending_artifact_refs")
    if not isinstance(pending, list) or not pending:
        return None
    if (tool_name or "").strip() == "delegate":
        return None
    ids = ", ".join(str(x) for x in pending[:5])
    return (
        f"A prior specialist step produced artifact_id(s) for implementation ({ids}). "
        "Call delegate with agent_id=coding, artifact_refs, and requirements "
        "(mode: fix_from_artifact, branch: <name>)."
    )


def delegate_fingerprint(agent_id: str, prompt: str) -> str:
    """Stable key for duplicate-delegate detection (no domain or tool-name lists)."""
    aid = (agent_id or "").strip().lower()
    p = " ".join((prompt or "").split()).strip().lower()
    if not aid or not p:
        return ""
    return f"{aid}:{p}"


def _truthy_flag(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def record_orchestrator_delegate_success(
    tool_context: dict[str, Any],
    args: dict[str, Any],
    result: str,
) -> None:
    """Track successful delegate handoffs for loop prevention (general agent only)."""
    if str(tool_context.get("agent_id") or "") != "general":
        return
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict) or data.get("ok") is not True:
        return
    excerpt = data.get("assistant_excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        return
    tool_context["orchestrator_last_delegate_excerpt"] = excerpt.strip()
    sub_agent = str(args.get("agent_id") or "").strip()
    if sub_agent:
        tool_context["orchestrator_last_delegate_agent_id"] = sub_agent
    fp = delegate_fingerprint(
        str(args.get("agent_id") or ""),
        str(args.get("prompt") or ""),
    )
    if not fp:
        return
    seen = tool_context.get("orchestrator_delegate_success_fps")
    if not isinstance(seen, set):
        seen = set()
        tool_context["orchestrator_delegate_success_fps"] = seen
    seen.add(fp)


def orchestrator_pre_tool_blocked(
    tool_name: str,
    args: dict[str, Any],
    tool_context: dict[str, Any] | None = None,
) -> str | None:
    """State-based pre-flight checks for general orchestrator — no tool-name blocklists."""
    ctx = tool_context or {}
    if str(ctx.get("agent_id") or "") != "general":
        return None

    msg = general_orchestrator_tool_blocked(tool_name, args, ctx)
    if msg:
        return msg

    if (tool_name or "").strip() != "delegate":
        return None

    if _truthy_flag(args.get("list_agents")):
        last_excerpt = ctx.get("orchestrator_last_delegate_excerpt")
        if isinstance(last_excerpt, str) and last_excerpt.strip():
            return (
                "A delegate already returned assistant_excerpt. "
                "Answer the user from that result — do not list agents again."
            )
        return None

    sub_aid = str(args.get("agent_id") or "").strip()
    last_excerpt = ctx.get("orchestrator_last_delegate_excerpt")
    last_agent = str(ctx.get("orchestrator_last_delegate_agent_id") or "").strip()
    if (
        sub_aid
        and last_agent
        and sub_aid == last_agent
        and isinstance(last_excerpt, str)
        and last_excerpt.strip()
    ):
        return (
            "You already delegated to this specialist successfully. "
            "Use the prior delegate tool result (assistant_excerpt) in your reply — "
            "do not delegate to the same agent_id again."
        )

    fp = delegate_fingerprint(
        str(args.get("agent_id") or ""),
        str(args.get("prompt") or ""),
    )
    if not fp:
        return None
    seen = ctx.get("orchestrator_delegate_success_fps")
    if isinstance(seen, set) and fp in seen:
        return (
            "You already delegated this task successfully. "
            "Use the prior delegate tool result (assistant_excerpt) in your reply — "
            "do not call delegate again with the same agent_id and prompt."
        )

    return None


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


def _artifact_ref_ids(artifact_refs: Any) -> list[str]:
    if artifact_refs is None:
        return []
    if isinstance(artifact_refs, str):
        artifact_refs = [artifact_refs]
    if not isinstance(artifact_refs, list):
        return []
    out: list[str] = []
    for item in artifact_refs:
        s = str(item).strip()
        if not s:
            continue
        try:
            uuid.UUID(s)
            out.append(s)
        except (ValueError, TypeError):
            continue
    return out


def subagent_reject_reason(
    *,
    agent_id: str,
    requirements: Any,
    artifact_refs: Any = None,
) -> str | None:
    """Reject invalid specialist + mode combinations before spawning a sub-run."""
    mode = parse_delegate_mode(requirements)
    if mode == "fix_from_artifact" and agent_id == "coding_plan":
        return (
            "coding_plan is read-only. For fix_from_artifact use agent_delegate with agent_id=coding, "
            "artifact_refs from the prior run, and requirements including mode: fix_from_artifact and branch: <name>."
        )
    if mode == "fix_from_artifact" and agent_id == "coding":
        refs = _artifact_ref_ids(artifact_refs)
        if not refs:
            return (
                "fix_from_artifact requires artifact_refs from a prior specialist run (e.g. security_auditor "
                "ssc_scan artifact_id). For open-ended repo fixes, delegate to coding without mode: fix_from_artifact."
            )
    return None
