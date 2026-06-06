"""Auto-sync projects portfolio KPI stat blocks from ``projects[]`` rows."""

from __future__ import annotations

from typing import Any

_INACTIVE_STATUSES = frozenset({"archived", "inactive", "paused", "done", "completed"})

_DEFAULT_LABELS = {
    "stat_projects": "Total repos",
    "stat_linked": "With workspace",
    "stat_active": "Active",
}


def projects_data_path(dashboard: dict[str, Any]) -> str:
    """Resolve list key used for project rows (usually ``projects``)."""
    ul = dashboard.get("ui_layout") if isinstance(dashboard.get("ui_layout"), dict) else {}
    blocks = ul.get("blocks") if isinstance(ul.get("blocks"), list) else []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        btype = str(b.get("type") or "").strip().lower()
        props = b.get("props") if isinstance(b.get("props"), dict) else {}
        dp = str(props.get("dataPath") or "").strip()
        if btype in ("table", "card_grid") and dp:
            return dp
        if btype == "section":
            nested = props.get("nested") if isinstance(props.get("nested"), dict) else {}
            for nb in nested.get("blocks") or []:
                if not isinstance(nb, dict):
                    continue
                nprops = nb.get("props") if isinstance(nb.get("props"), dict) else {}
                ndp = str(nprops.get("dataPath") or "").strip()
                ntype = str(nb.get("type") or "").strip().lower()
                if ntype in ("table", "card_grid") and ndp:
                    return ndp
    return "projects"


def row_is_active(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status in _INACTIVE_STATUSES:
        return False
    return True


def compute_projects_kpis(projects: list[Any]) -> tuple[int, int, int]:
    rows = [p for p in projects if isinstance(p, dict)]
    total = len(rows)
    linked = sum(1 for p in rows if str(p.get("workspace_id") or "").strip())
    active = sum(1 for p in rows if row_is_active(p))
    return total, linked, active


def _merge_stat(existing: Any, *, value: int, default_label: str) -> dict[str, Any]:
    if isinstance(existing, dict):
        out = dict(existing)
        out["value"] = str(value)
        if not str(out.get("label") or "").strip():
            out["label"] = default_label
        return out
    return {
        "value": str(value),
        "label": default_label,
        "suffix": "",
        "trend": "",
    }


def sync_projects_kpis_in_data(
    data: dict[str, Any],
    projects_key: str = "projects",
) -> dict[str, Any]:
    """Return ``data`` copy with ``stat_*`` KPI values derived from the projects list."""
    if not isinstance(data, dict):
        return {}
    pk = (projects_key or "projects").strip() or "projects"
    raw = data.get(pk)
    projects = raw if isinstance(raw, list) else []
    total, linked, active = compute_projects_kpis(projects)

    out = dict(data)
    out["stat_projects"] = _merge_stat(
        out.get("stat_projects"), value=total, default_label=_DEFAULT_LABELS["stat_projects"]
    )
    out["stat_linked"] = _merge_stat(
        out.get("stat_linked"), value=linked, default_label=_DEFAULT_LABELS["stat_linked"]
    )
    out["stat_active"] = _merge_stat(
        out.get("stat_active"), value=active, default_label=_DEFAULT_LABELS["stat_active"]
    )
    return out


def patches_touch_projects_list(patches: list[Any], projects_key: str) -> bool:
    pk = (projects_key or "projects").strip() or "projects"
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        path = str(patch.get("path") or "").strip()
        if path == pk or path.startswith(f"{pk}."):
            return True
    return False
