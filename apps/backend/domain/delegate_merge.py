"""Merge global user delegate with workspace overlay for prompts and decisions."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.delegate_config_schema import default_delegate_config, normalize_delegate_config


def _deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], val)
        else:
            out[key] = val
    return out


def merge_delegate_configs(
    user_config: dict[str, Any] | None,
    workspace_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Workspace keys override global for nested objects; workspace ``goals`` replace if non-empty."""
    base = normalize_delegate_config(user_config, scope="user")
    if not workspace_config:
        return base
    ws = normalize_delegate_config(workspace_config, scope="workspace")
    merged = _deep_merge_dict(base, ws)
    ws_goals = ws.get("goals") or []
    if ws_goals:
        merged["goals"] = list(ws_goals)
    ws_priorities = (ws.get("engineering") or {}).get("priorities") or []
    if ws_priorities:
        merged["engineering"] = {**(merged.get("engineering") or {}), "priorities": list(ws_priorities)}
    return merged


def build_delegate_context_block(
    *,
    user_config: dict[str, Any] | None,
    workspace_config: dict[str, Any] | None = None,
    workspace_label: str | None = None,
) -> str:
    """Compact system block for delegate decision / unattended runs (no observations)."""
    cfg = merge_delegate_configs(user_config, workspace_config)
    lines = [
        "## User delegate (Stellvertreter)",
        "You may decide and act on the user's behalf within these explicit bounds — not voice mimicry.",
    ]
    if workspace_label:
        lines.append(f"Workspace context: {workspace_label.strip()}")

    comm = cfg.get("communication") or {}
    eng = cfg.get("engineering") or {}
    aut = cfg.get("autonomy") or {}
    dec = cfg.get("decisioning") or {}
    esc = cfg.get("escalation") or {}
    goals = cfg.get("goals") or []

    lines.append(
        "Communication: "
        f"directness={comm.get('directness')}, "
        f"detail={comm.get('detail_level')}, "
        f"ask_before_major_changes={comm.get('ask_before_major_changes')}"
    )
    lines.append(
        "Engineering: "
        f"security_first={eng.get('security_first')}, "
        f"prefer_tests={eng.get('prefer_tests')}, "
        f"prefer_refactoring={eng.get('prefer_refactoring')}, "
        f"primary_goal={eng.get('primary_goal')}, "
        f"priorities={eng.get('priorities')}"
    )
    lines.append(
        "Autonomy: "
        f"can_fix_minor_issues={aut.get('can_fix_minor_issues')}, "
        f"can_merge_prs={aut.get('can_merge_prs')}, "
        f"can_force_push={aut.get('can_force_push')}"
    )
    lines.append(f"Decisioning: risk_tolerance={dec.get('risk_tolerance')}")
    lines.append(
        "Escalation (stop and ask user when true): "
        f"production_changes={esc.get('ask_on_production_changes')}, "
        f"database_migrations={esc.get('ask_on_database_migrations')}, "
        f"security_findings={esc.get('ask_on_security_findings')}"
    )
    if goals:
        lines.append("Goals:")
        for g in goals[:20]:
            lines.append(f"- {g}")
    else:
        lines.append("Goals: (none configured — use task context and engineering priorities)")

    return "\n".join(lines)


def merged_or_default(
    user_config: dict[str, Any] | None,
    workspace_config: dict[str, Any] | None,
) -> dict[str, Any]:
    if user_config is None and workspace_config is None:
        return default_delegate_config()
    return merge_delegate_configs(user_config, workspace_config)
