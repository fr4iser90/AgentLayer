"""Delegate handoff data read from specialist artifacts (paths, artifact ids, requirement values)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

__all__ = [
    "DelegateEnforcementDependencies",
    "agent_artifacts_store",
    "artifact_ref_ids",
    "extract_artifact_ids_from_tool_result",
    "extract_handoff_artifact_ids",
    "load_delegate_allowed_paths",
    "normalize_repo_path",
    "parse_requirement_value",
    "paths_from_artifact_content",
    "register_delegate_enforcement_dependencies",
]


class DelegateEnforcementDependencies(Protocol):
    def get_artifact(self, *, artifact_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None: ...


_deps: DelegateEnforcementDependencies | None = None


def register_delegate_enforcement_dependencies(deps: DelegateEnforcementDependencies) -> None:
    global _deps
    _deps = deps


class _AgentArtifactsStorePort:
    def get_artifact(self, *, artifact_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
        return _deps.get_artifact(artifact_id=artifact_id, tenant_id=tenant_id) if _deps is not None else None


agent_artifacts_store = _AgentArtifactsStorePort()


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


def artifact_ref_ids(artifact_refs: Any) -> list[str]:
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
