"""Dashboard layout-driven stat recomputation — no dashboard-kind hardcoding."""

from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.dashboards.dashboard_data_paths import get_path, set_path
from apps.backend.infrastructure.dashboards.dashboard_layout_tree import iter_layout_blocks

_COMPUTE_OPS = frozenset({"count", "count_where", "count_nonempty", "sum"})


def _row_field(row: dict[str, Any], field: str) -> Any:
    path = (field or "").strip()
    if not path:
        return None
    if "." not in path:
        return row.get(path)
    cur: Any = row
    for seg in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
    return cur


def _eval_where(row: dict[str, Any], clause: dict[str, Any]) -> bool:
    field = str(clause.get("field") or "").strip()
    if not field:
        return True
    val = _row_field(row, field)
    if clause.get("nonempty") is True:
        return bool(str(val or "").strip())
    if clause.get("empty") is True:
        return not str(val or "").strip()
    if "eq" in clause:
        return str(val or "") == str(clause.get("eq"))
    if "neq" in clause:
        return str(val or "") != str(clause.get("neq"))
    if "in" in clause and isinstance(clause.get("in"), list):
        return str(val or "").strip().lower() in {
            str(x).strip().lower() for x in clause["in"]
        }
    not_in = clause.get("not_in")
    if isinstance(not_in, list):
        return str(val or "").strip().lower() not in {
            str(x).strip().lower() for x in not_in
        }
    return True


def _rows_match_where(rows: list[Any], where: list[Any]) -> list[dict[str, Any]]:
    clauses = [c for c in where if isinstance(c, dict)]
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if all(_eval_where(row, c) for c in clauses):
            out.append(row)
    return out


def _list_at(data: dict[str, Any], path: str) -> list[Any]:
    raw = get_path(data, path)
    return raw if isinstance(raw, list) else []


def evaluate_compute(data: dict[str, Any], spec: dict[str, Any]) -> int | float:
    op = str(spec.get("op") or "").strip().lower()
    src = str(spec.get("from") or spec.get("source") or "").strip()
    if not src:
        return 0
    rows = _list_at(data, src)
    dict_rows = [r for r in rows if isinstance(r, dict)]

    if op == "count":
        return len(dict_rows)
    if op == "count_where":
        where = spec.get("where")
        filtered = _rows_match_where(dict_rows, where if isinstance(where, list) else [])
        return len(filtered)
    if op == "count_nonempty":
        field = str(spec.get("field") or "").strip()
        return sum(1 for r in dict_rows if _eval_where(r, {"field": field, "nonempty": True}))
    if op == "sum":
        field = str(spec.get("field") or "").strip()
        total = 0.0
        for row in dict_rows:
            raw = _row_field(row, field)
            try:
                total += float(raw)
            except (TypeError, ValueError):
                continue
        return int(total) if total == int(total) else total
    return 0


def collect_compute_bindings(ui_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Stat blocks with ``props.compute`` → {dataPath, compute, label}."""
    bindings: list[dict[str, Any]] = []
    for block in iter_layout_blocks(ui_layout):
        if str(block.get("type") or "").strip().lower() != "stat":
            continue
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        compute = props.get("compute")
        if not isinstance(compute, dict):
            continue
        op = str(compute.get("op") or "").strip().lower()
        if op not in _COMPUTE_OPS:
            continue
        dp = str(props.get("dataPath") or "").strip()
        if not dp:
            continue
        bindings.append(
            {
                "block_id": str(block.get("id") or "").strip(),
                "dataPath": dp,
                "compute": compute,
                "label": str(props.get("title") or props.get("label") or "").strip(),
            }
        )
    return bindings


def compute_source_paths(ui_layout: dict[str, Any] | None) -> set[str]:
    paths: set[str] = set()
    for binding in collect_compute_bindings(ui_layout):
        compute = binding.get("compute")
        if not isinstance(compute, dict):
            continue
        src = str(compute.get("from") or compute.get("source") or "").strip()
        if src:
            paths.add(src)
    return paths


def patches_touch_compute_sources(
    patches: list[Any],
    source_paths: set[str],
) -> bool:
    if not source_paths:
        return False
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        path = str(patch.get("path") or "").strip()
        if not path:
            continue
        for src in source_paths:
            if path == src or path.startswith(f"{src}."):
                return True
    return False


def _merge_stat_value(existing: Any, *, value: int | float, label: str) -> dict[str, Any]:
    if isinstance(existing, dict):
        out = dict(existing)
        out["value"] = str(value)
        if label and not str(out.get("label") or "").strip():
            out["label"] = label
        return out
    return {
        "value": str(value),
        "label": label or "",
        "suffix": "",
        "trend": "",
    }


def sync_computed_stats_in_data(
    data: dict[str, Any],
    ui_layout: dict[str, Any] | None,
) -> dict[str, Any]:
    """Recompute all stat blocks that declare ``props.compute``."""
    if not isinstance(data, dict):
        return {}
    bindings = collect_compute_bindings(ui_layout)
    if not bindings:
        return dict(data)
    out = dict(data)
    for binding in bindings:
        dp = str(binding.get("dataPath") or "").strip()
        compute = binding.get("compute")
        if not dp or not isinstance(compute, dict):
            continue
        value = evaluate_compute(out, compute)
        label = str(binding.get("label") or "").strip()
        existing = get_path(out, dp)
        merged = _merge_stat_value(existing, value=value, label=label)
        out = set_path(out, dp, merged)
    return out


def finalize_dashboard_data(
    data: dict[str, Any],
    ui_layout: dict[str, Any] | None,
) -> dict[str, Any]:
    """Recompute stat blocks that declare ``props.compute`` (any dashboard kind)."""
    return sync_computed_stats_in_data(data, ui_layout)


def patches_should_recompute_stats(
    patches: list[Any],
    ui_layout: dict[str, Any] | None,
) -> bool:
    return patches_touch_compute_sources(patches, compute_source_paths(ui_layout))
