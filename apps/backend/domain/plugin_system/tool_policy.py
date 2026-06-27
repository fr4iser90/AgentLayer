"""Merge manifest defaults with operator DB policy for tool exposure."""

from __future__ import annotations

from typing import Any, Protocol

from apps.backend.domain.plugin_system.tool_manifest_dimensions import (
    normalize_execution_context,
    normalize_min_role,
    parse_allowed_tenant_ids,
)
from apps.backend.domain.plugin_system.registry import ToolRegistry


class ToolPolicyDependencies(Protocol):
    def resolved_agent_mode(self) -> str: ...


_deps: ToolPolicyDependencies | None = None


def register_tool_policy_dependencies(deps: ToolPolicyDependencies) -> None:
    global _deps
    _deps = deps


def resolved_agent_mode() -> str:
    return _deps.resolved_agent_mode() if _deps is not None else ""


def manifest_execution_context(meta_entry: dict[str, Any], tool_fn_name: str) -> str:
    """Package manifest, overridden by ``AGENT_TOOL_META_BY_NAME`` for this function when set."""
    base = meta_entry.get("execution_context")
    per = meta_entry.get("per_tool")
    if isinstance(per, dict):
        pt = per.get(tool_fn_name)
        if isinstance(pt, dict) and isinstance(pt.get("execution_context"), str):
            base = pt["execution_context"]
    return normalize_execution_context(base if isinstance(base, str) else None)


def manifest_min_role(meta_entry: dict[str, Any], tool_fn_name: str) -> str:
    base = meta_entry.get("min_role")
    if not isinstance(base, str):
        base = None
    per = meta_entry.get("per_tool")
    if isinstance(per, dict):
        pt = per.get(tool_fn_name)
        if isinstance(pt, dict) and isinstance(pt.get("min_role"), str):
            base = pt["min_role"]
    return normalize_min_role(base)


def manifest_allowed_tenant_ids(meta_entry: dict[str, Any], tool_fn_name: str) -> list[int] | None:
    base = meta_entry.get("allowed_tenant_ids")
    per = meta_entry.get("per_tool")
    if isinstance(per, dict):
        pt = per.get(tool_fn_name)
        if isinstance(pt, dict) and "allowed_tenant_ids" in pt:
            return parse_allowed_tenant_ids(pt.get("allowed_tenant_ids"))
    return parse_allowed_tenant_ids(base)


def _pick_execution_context_policy(
    pmap: dict[tuple[str, str], dict[str, Any]],
    package_id: str,
    tool_fn_name: str,
) -> str | None:
    """Non-None when operator row sets an override."""
    rx = pmap.get((package_id, tool_fn_name))
    rs = pmap.get((package_id, "*"))
    if rx is not None:
        v = rx.get("execution_context")
        if isinstance(v, str) and v.strip():
            return normalize_execution_context(v.strip())
    if rs is not None:
        v = rs.get("execution_context")
        if isinstance(v, str) and v.strip():
            return normalize_execution_context(v.strip())
    return None


def effective_execution_context(
    meta_entry: dict[str, Any],
    tool_fn_name: str,
    pmap: dict[tuple[str, str], dict[str, Any]],
) -> str:
    pid = str(meta_entry.get("id") or "").strip()
    ov = _pick_execution_context_policy(pmap, pid, tool_fn_name) if pid else None
    if ov is not None:
        ctx = ov
    else:
        ctx = manifest_execution_context(meta_entry, tool_fn_name)
    try:
        if resolved_agent_mode() == "sandbox":
            return "container"
    except Exception:
        pass
    return ctx


def _pick_policy_str(
    pmap: dict[tuple[str, str], dict[str, Any]],
    pid: str,
    tool_fn_name: str,
    key: str,
    manifest_val: str,
    normalize: Any,
) -> str:
    rx = pmap.get((pid, tool_fn_name))
    rs = pmap.get((pid, "*"))
    if rx is not None:
        v = rx.get(key)
        if isinstance(v, str) and v.strip():
            return normalize(v)
    if rs is not None:
        v = rs.get(key)
        if isinstance(v, str) and v.strip():
            return normalize(v)
    return manifest_val


def _pick_allowed_tenants(
    pmap: dict[tuple[str, str], dict[str, Any]],
    pid: str,
    tool_fn_name: str,
    manifest_val: list[int] | None,
) -> list[int] | None:
    """Operator non-NULL allowed_tenant_ids overrides manifest; NULL/absent inherits manifest."""
    rx = pmap.get((pid, tool_fn_name))
    rs = pmap.get((pid, "*"))
    if rx is not None and "allowed_tenant_ids" in rx:
        return parse_allowed_tenant_ids(rx.get("allowed_tenant_ids"))
    if rs is not None and "allowed_tenant_ids" in rs:
        return parse_allowed_tenant_ids(rs.get("allowed_tenant_ids"))
    return manifest_val


def effective_flags(
    meta_entry: dict[str, Any],
    tool_fn_name: str,
    pmap: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Resolved enabled, min_role, allowed_tenant_ids, execution_context for one tool name."""
    pid = str(meta_entry.get("id") or "").strip()
    m_mr = manifest_min_role(meta_entry, tool_fn_name)
    m_tids = manifest_allowed_tenant_ids(meta_entry, tool_fn_name)
    rs = pmap.get((pid, "*"))
    rx = pmap.get((pid, tool_fn_name))
    enabled = True
    if rx is not None:
        enabled = bool(rx.get("enabled", True))
    elif rs is not None:
        enabled = bool(rs.get("enabled", True))

    min_role = _pick_policy_str(pmap, pid, tool_fn_name, "min_role", m_mr, normalize_min_role)
    allowed_tenant_ids = _pick_allowed_tenants(pmap, pid, tool_fn_name, m_tids)

    return {
        "enabled": enabled,
        "min_role": min_role,
        "allowed_tenant_ids": allowed_tenant_ids,
        "execution_context": effective_execution_context(meta_entry, tool_fn_name, pmap),
    }


def caller_fulfills_effective_policy(
    user_role: str | None,
    tenant_id: int,
    eff: dict[str, Any],
) -> bool:
    """Whether the current caller may list/invoke a tool with this effective policy."""
    mr = str(eff.get("min_role") or "user")
    ur = normalize_min_role(user_role)
    if normalize_min_role(mr) == "admin" and ur != "admin":
        return False
    allowed = eff.get("allowed_tenant_ids")
    if allowed is None:
        return True
    if not isinstance(allowed, list) or not allowed:
        return True
    return int(tenant_id) in allowed


def filter_chat_tool_specs(
    specs: list[dict[str, Any]],
    reg: ToolRegistry,
    pmap: dict[tuple[str, str], dict[str, Any]],
    user_role: str | None,
    tenant_id: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        fn = spec.get("function") if isinstance(spec, dict) else None
        n = fn.get("name") if isinstance(fn, dict) else None
        if not n:
            out.append(spec)
            continue
        name = str(n)
        meta = reg.meta_entry_for_tool_name(name)
        if not meta:
            out.append(spec)
            continue
        eff = effective_flags(meta, name, pmap)
        if eff["enabled"] and caller_fulfills_effective_policy(user_role, tenant_id, eff):
            out.append(spec)
    return out


def filter_tools_meta(
    entries: list[dict[str, Any]],
    pmap: dict[tuple[str, str], dict[str, Any]],
    user_role: str | None,
    tenant_id: int,
) -> list[dict[str, Any]]:
    """Drop packages whose every tool is disabled or not allowed for this caller."""
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        names = entry.get("tools")
        if not isinstance(names, list):
            continue
        for tn in names:
            if not isinstance(tn, str):
                continue
            eff = effective_flags(entry, tn, pmap)
            if eff["enabled"] and caller_fulfills_effective_policy(user_role, tenant_id, eff):
                out.append(entry)
                break
    return out


def attach_execution_context_by_tool(
    entries: list[dict[str, Any]],
    pmap: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Mutate copies or entries: add ``execution_context_by_tool`` for API consumers."""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        names = entry.get("tools")
        if not isinstance(names, list):
            continue
        m: dict[str, str] = {}
        for tn in names:
            if isinstance(tn, str):
                m[tn] = effective_flags(entry, tn, pmap)["execution_context"]
        if m:
            entry["execution_context_by_tool"] = m


def enrich_meta_for_admin(
    entries: list[dict[str, Any]],
    pmap: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach effective{} and tool_effective map for admin UI."""
    rich: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        names = row.get("tools")
        te: dict[str, Any] = {}
        if isinstance(names, list):
            for tn in names:
                if not isinstance(tn, str):
                    continue
                te[tn] = effective_flags(row, tn, pmap)
        row["tool_effective"] = te
        rs = pmap.get((str(row.get("id") or "").strip(), "*"))
        if rs:
            row["policy_row"] = {
                "enabled": rs.get("enabled"),
                "min_role": rs.get("min_role"),
                "allowed_tenant_ids": rs.get("allowed_tenant_ids"),
                "execution_context": rs.get("execution_context"),
            }
        rich.append(row)
    return rich
