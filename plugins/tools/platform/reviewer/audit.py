"""Reviewer agent tools — read-only benchmark audit (no config writes, no bench starts).

Every handler asks the two questions its mirrored route asks, through
:func:`console_scope`. Benchmarks, experiments and reviews mirror
``/v1/admin/benchmarks/*``, which carries no capability slug at all and admits a site
admin; the config reads and the draft mirror ``/v1/admin/agent-config/*`` and need
``agent.assign`` inside the caller's own company; ``agents_get`` mirrors
``/v1/admin/agents/{agent_id}`` — same slug, nothing company-shaped, since the registry is
instance-wide; the run trace mirrors ``/v1/admin/run-traces/runs/{run_id}`` and needs
``observability.read``. The legacy ``users.role`` column is not consulted here.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.application.agent_runtime.use_cases.run_traces import tool_invocations_for_run
from apps.backend.domain.access.capabilities import (
    AdminScope,
    AdminScopeError,
    CAP_AGENT_ASSIGN,
    CAP_OBSERVABILITY_READ,
)
from apps.backend.domain.agent_runtime.registry import get_agent_registry
from apps.backend.infrastructure.agent_runtime import agent_config_service, agent_config_store
from apps.backend.infrastructure.agent_runtime import agent_runs_store, agent_tasks_store
from apps.backend.infrastructure.benchmarks import benchmark_runs_store
from apps.backend.infrastructure.agent_runtime.agent_config_fingerprint import fingerprint_response, snapshot
from apps.backend.infrastructure.identity.console_access import console_scope
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


def _site_wide() -> AdminScope | str:
    """Work whose routes have no capability slug: benchmarks and reviews."""
    try:
        return console_scope()
    except AdminScopeError as e:
        return _err(str(e))


def _scope(capability: str) -> AdminScope | str:
    try:
        return console_scope(capability)
    except AdminScopeError as e:
        return _err(str(e))


def _home_tenant(scope: AdminScope) -> int:
    """The company the mirrored route reads off the caller and every store filters on.

    An identity without a company falls back to company 1 rather than an unscoped
    ``None``: these are tenant-scoped reads, so a missing company must narrow one,
    never widen it.
    """
    return int(db.user_tenant_id(scope.actor_id) or 1)


def _parse_uuid(raw: Any, *, field: str) -> uuid.UUID | None:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, TypeError):
        return None


def benchmark_analysis_get(arguments: dict[str, Any]) -> str:
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
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
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=200)
    return _ok({"cohorts": list_cohorts(rows)})


def benchmark_cohort_compare(arguments: dict[str, Any]) -> str:
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    a = str(arguments.get("cohort_a") or "").strip()
    b = str(arguments.get("cohort_b") or "").strip()
    if not a or not b:
        return _err("cohort_a and cohort_b required")
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=200)
    return _ok(compare_cohorts(rows, cohort_a=a, cohort_b=b))


def benchmark_stats_get(arguments: dict[str, Any]) -> str:
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=int(arguments.get("limit") or 200))
    return _ok({"stats": aggregate_benchmark_stats(rows)})


def benchmark_experiment_get(arguments: dict[str, Any]) -> str:
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    eid = _parse_uuid(arguments.get("experiment_id"), field="experiment_id")
    if not eid:
        return _err("experiment_id required")
    exp = agent_config_store.get_experiment(eid, tenant_id=tid)
    if not exp:
        return _err("experiment not found")
    return _ok({"experiment": exp})


def benchmark_experiment_report(arguments: dict[str, Any]) -> str:
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    eid = _parse_uuid(arguments.get("experiment_id"), field="experiment_id")
    if not eid:
        return _err("experiment_id required")
    report = agent_config_store.experiment_report(eid, tenant_id=tid)
    if not report:
        return _err("experiment not found")
    return _ok(report)


def benchmark_run_get(arguments: dict[str, Any]) -> str:
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    run_id = _parse_uuid(arguments.get("run_id"), field="run_id")
    if not run_id:
        return _err("run_id required")
    row = benchmark_runs_store.get_run(run_id)
    if not row or int(row.get("tenant_id") or 0) != tid:
        return _err("benchmark run not found")
    return _ok({"run": row})


def agent_config_snapshot(arguments: dict[str, Any]) -> str:
    scope = _scope(CAP_AGENT_ASSIGN)
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    return _ok(snapshot(tenant_id=tid))


def agent_config_fingerprint(arguments: dict[str, Any]) -> str:
    scope = _scope(CAP_AGENT_ASSIGN)
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    return _ok(fingerprint_response(tenant_id=tid))


def agent_config_changelog(arguments: dict[str, Any]) -> str:
    scope = _scope(CAP_AGENT_ASSIGN)
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    rows = agent_config_store.list_changelog(
        tid,
        limit=int(arguments.get("limit") or 50),
        actor_type=str(arguments.get("actor_type") or "").strip() or None,
    )
    return _ok({"events": rows})


def agents_get(arguments: dict[str, Any]) -> str:
    scope = _scope(CAP_AGENT_ASSIGN)
    if isinstance(scope, str):
        return scope
    aid = str(arguments.get("agent_id") or "").strip()
    if not aid:
        return _err("agent_id required")
    agent = get_agent_registry().get_agent(aid)
    if not agent:
        return _err("agent not found")
    return _ok({"agent": agent})


def review_recommend_patches(arguments: dict[str, Any]) -> str:
    scope = _scope(CAP_AGENT_ASSIGN)
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
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
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
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
    scope = _site_wide()
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    rid = _parse_uuid(arguments.get("review_id"), field="review_id")
    if not rid:
        return _err("review_id required")
    review = agent_config_store.get_review(rid, tenant_id=tid)
    if not review:
        return _err("review not found")
    return _ok({"review": review})


def run_trace_get(arguments: dict[str, Any]) -> str:
    scope = _scope(CAP_OBSERVABILITY_READ)
    if isinstance(scope, str):
        return scope
    tid = _home_tenant(scope)
    run_id = _parse_uuid(arguments.get("run_id"), field="run_id")
    if not run_id:
        return _err("run_id required")
    run = agent_runs_store.get_run(run_id=run_id, tenant_id=tid)
    if not run:
        return _err("run trace not found")
    tools = tool_invocations_for_run(run_id)
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
