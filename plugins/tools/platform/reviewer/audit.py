"""Reviewer agent tools — read-only benchmark audit (no config writes, no bench starts)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.agent_runtime.registry import get_agent_registry
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.agent_runtime import agent_config_service, agent_config_store
from apps.backend.infrastructure.benchmarks import benchmark_runs_store
from apps.backend.infrastructure.agent_runtime.agent_config_fingerprint import fingerprint_response, snapshot
from apps.backend.infrastructure.identity.auth import get_user_by_id
from apps.backend.infrastructure.benchmarks.benchmark_analysis import analyze_runs, compare_cohorts, list_cohorts
from apps.backend.infrastructure.benchmarks.benchmark_review_service import run_review
from apps.backend.infrastructure.benchmarks.benchmark_stats import aggregate_benchmark_stats
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "reviewer_audit"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "reviewer"
TOOL_LABEL = "Reviewer benchmark audit"
TOOL_DESCRIPTION = "Read-only benchmark analysis, cohort compare, config snapshot, review submit."
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_MIN_ROLE = "admin"
TOOL_CAPABILITIES = ("review.benchmark", "review.config")
_CAP = ("review.benchmark", "review.config")
AGENT_TOOL_META_BY_NAME: dict[str, dict[str, Any]] = {}


def _err(msg: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _admin_tid_uid() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    user = get_user_by_id(uid)
    if not user or str(getattr(user, "role", "") or "").lower() != "admin":
        return None
    tenant_id = db.user_tenant_id(uid)
    if tenant_id is None:
        return None
    return int(tenant_id), uid


def _require_admin() -> tuple[int, uuid.UUID] | str:
    g = _admin_tid_uid()
    if g is None:
        return _err("authentication and admin role required for this tool")
    return g


def _parse_uuid(raw: Any, *, field: str) -> uuid.UUID | None:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, TypeError):
        return None


def benchmark_analysis_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=int(arguments.get("limit") or 200))
    return _ok(
        analyze_runs(
            rows,
            cohort=str(arguments.get("cohort") or "").strip() or None,
            fingerprint=str(arguments.get("fingerprint") or "").strip() or None,
            suite=str(arguments.get("suite") or "").strip() or None,
        )
    )


def benchmark_cohorts_list(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=200)
    return _ok({"cohorts": list_cohorts(rows)})


def benchmark_cohort_compare(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    a = str(arguments.get("cohort_a") or "").strip()
    b = str(arguments.get("cohort_b") or "").strip()
    if not a or not b:
        return _err("cohort_a and cohort_b required")
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=200)
    return _ok(compare_cohorts(rows, cohort_a=a, cohort_b=b))


def benchmark_stats_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=int(arguments.get("limit") or 200))
    return _ok({"stats": aggregate_benchmark_stats(rows)})


def benchmark_experiment_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    eid = _parse_uuid(arguments.get("experiment_id"), field="experiment_id")
    if not eid:
        return _err("experiment_id required")
    exp = agent_config_store.get_experiment(eid, tenant_id=tid)
    if not exp:
        return _err("experiment not found")
    return _ok({"experiment": exp})


def benchmark_experiment_report(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    eid = _parse_uuid(arguments.get("experiment_id"), field="experiment_id")
    if not eid:
        return _err("experiment_id required")
    report = agent_config_store.experiment_report(eid, tenant_id=tid)
    if not report:
        return _err("experiment not found")
    return _ok(report)


def benchmark_run_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    run_id = _parse_uuid(arguments.get("run_id"), field="run_id")
    if not run_id:
        return _err("run_id required")
    row = benchmark_runs_store.get_run(run_id)
    if not row or int(row.get("tenant_id") or 0) != tid:
        return _err("benchmark run not found")
    return _ok({"run": row})


def agent_config_snapshot(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    return _ok(snapshot(tenant_id=tid))


def agent_config_fingerprint(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    return _ok(fingerprint_response(tenant_id=tid))


def agent_config_changelog(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    rows = agent_config_store.list_changelog(
        tid,
        limit=int(arguments.get("limit") or 50),
        actor_type=str(arguments.get("actor_type") or "").strip() or None,
    )
    return _ok({"events": rows})


def agents_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    aid = str(arguments.get("agent_id") or "").strip()
    if not aid:
        return _err("agent_id required")
    agent = get_agent_registry().get_agent(aid)
    if not agent:
        return _err("agent not found")
    return _ok({"agent": agent})


def review_recommend_patches(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    patches = arguments.get("patches")
    if not isinstance(patches, list):
        return _err("patches array required")
    result = agent_config_service.draft_patches(
        tenant_id=tid,
        patches=[dict(p) for p in patches if isinstance(p, dict)],
        hypothesis=str(arguments.get("hypothesis") or "").strip() or None,
    )
    return _ok(result)


def review_submit(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    run_ids_raw = arguments.get("run_ids")
    run_ids = None
    if isinstance(run_ids_raw, list):
        run_ids = [_parse_uuid(r, field="run_id") for r in run_ids_raw]
        run_ids = [r for r in run_ids if r is not None]
    review = run_review(
        tenant_id=tid,
        experiment_id=_parse_uuid(arguments.get("experiment_id"), field="experiment_id"),
        session_id=_parse_uuid(arguments.get("session_id"), field="session_id"),
        run_ids=run_ids,
        mode=str(arguments.get("mode") or "llm"),
        reviewer_model=str(arguments.get("reviewer_model") or "reviewer"),
        actor_type="reviewer_agent",
        summary_hint=str(arguments.get("summary") or "").strip() or None,
    )
    return _ok({"review": review})


def review_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    rid = _parse_uuid(arguments.get("review_id"), field="review_id")
    if not rid:
        return _err("review_id required")
    review = agent_config_store.get_review(rid, tenant_id=tid)
    if not review:
        return _err("review not found")
    return _ok({"review": review})


def run_trace_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    run_id = _parse_uuid(arguments.get("run_id"), field="run_id")
    if not run_id:
        return _err("run_id required")
    from apps.backend.infrastructure.agent_runtime import agent_runs_store, agent_tasks_store
    from apps.backend.infrastructure.db import db
    from psycopg.rows import dict_row

    run = agent_runs_store.get_run(run_id=run_id, tenant_id=tid)
    if not run:
        return _err("run trace not found")
    tools: list[dict] = []
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tool_name, args_json, result_excerpt, ok, created_at, agent_run_id
                FROM tool_invocations
                WHERE agent_run_id = %s
                ORDER BY id ASC
                LIMIT 500
                """,
                (run_id,),
            )
            tools = [dict(r) for r in cur.fetchall()]
        conn.commit()
    child_runs = agent_runs_store.list_runs(tenant_id=tid, parent_run_id=run_id, limit=50)
    task = None
    if run.get("task_id"):
        task = agent_tasks_store.get_task(
            task_id=uuid.UUID(str(run["task_id"])), tenant_id=tid
        )
    return _ok(
        {
            "run": agent_runs_store.row_to_public(run),
            "task": agent_tasks_store.row_to_public(task) if task else None,
            "tool_invocations": tools,
            "child_runs": [agent_runs_store.row_to_public(r) for r in child_runs],
        }
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "benchmark_analysis_get": benchmark_analysis_get,
    "benchmark_cohorts_list": benchmark_cohorts_list,
    "benchmark_cohort_compare": benchmark_cohort_compare,
    "benchmark_stats_get": benchmark_stats_get,
    "benchmark_experiment_get": benchmark_experiment_get,
    "benchmark_experiment_report": benchmark_experiment_report,
    "benchmark_run_get": benchmark_run_get,
    "agent_config_snapshot": agent_config_snapshot,
    "agent_config_fingerprint": agent_config_fingerprint,
    "agent_config_changelog": agent_config_changelog,
    "agents_get": agents_get,
    "review_recommend_patches": review_recommend_patches,
    "review_submit": review_submit,
    "review_get": review_get,
    "run_trace_get": run_trace_get,
}

for _name in HANDLERS:
    AGENT_TOOL_META_BY_NAME[_name] = {"min_role": "admin", "capabilities": _CAP}


def _tool_fn(name: str, desc: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": name, "TOOL_DESCRIPTION": desc, "parameters": parameters},
    }


TOOLS: list[dict[str, Any]] = [
    _tool_fn("benchmark_analysis_get", "Read-only benchmark analysis.", {"type": "object", "properties": {}}),
    _tool_fn("benchmark_cohorts_list", "List cohort labels from run history.", {"type": "object", "properties": {}}),
    _tool_fn(
        "benchmark_cohort_compare",
        "Compare two cohorts.",
        {
            "type": "object",
            "properties": {"cohort_a": {"type": "string"}, "cohort_b": {"type": "string"}},
            "required": ["cohort_a", "cohort_b"],
        },
    ),
    _tool_fn("benchmark_stats_get", "Cross-run stats leaderboard.", {"type": "object", "properties": {}}),
    _tool_fn(
        "benchmark_experiment_get",
        "Get experiment record.",
        {"type": "object", "properties": {"experiment_id": {"type": "string"}}, "required": ["experiment_id"]},
    ),
    _tool_fn(
        "benchmark_experiment_report",
        "Experiment report with analysis + reviews.",
        {"type": "object", "properties": {"experiment_id": {"type": "string"}}, "required": ["experiment_id"]},
    ),
    _tool_fn(
        "benchmark_run_get",
        "Get benchmark run including report_json.",
        {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]},
    ),
    _tool_fn("agent_config_snapshot", "Read-only config snapshot.", {"type": "object", "properties": {}}),
    _tool_fn("agent_config_fingerprint", "Read-only fingerprint.", {"type": "object", "properties": {}}),
    _tool_fn("agent_config_changelog", "Read config changelog.", {"type": "object", "properties": {}}),
    _tool_fn(
        "agents_get",
        "Read agent definition.",
        {"type": "object", "properties": {"agent_id": {"type": "string"}}, "required": ["agent_id"]},
    ),
    _tool_fn(
        "review_recommend_patches",
        "Draft patches only (no apply).",
        {"type": "object", "properties": {"patches": {"type": "array"}}, "required": ["patches"]},
    ),
    _tool_fn(
        "review_submit",
        "Persist structured review verdict.",
        {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
    ),
    _tool_fn(
        "review_get",
        "Fetch stored review.",
        {"type": "object", "properties": {"review_id": {"type": "string"}}, "required": ["review_id"]},
    ),
    _tool_fn(
        "run_trace_get",
        "Fetch persisted agent run trace with tool invocations and child subagent runs.",
        {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]},
    ),
]
