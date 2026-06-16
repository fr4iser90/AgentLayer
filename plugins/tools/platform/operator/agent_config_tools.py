"""Operator tools for agent-config tuning and benchmark orchestration."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Callable

from apps.backend.domain.agent_config_registry import all_knobs, load_knob_registry
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure import agent_config_service, agent_config_store, benchmark_runs_store
from apps.backend.infrastructure.agent_config_fingerprint import compute_fingerprint, snapshot
from apps.backend.infrastructure.auth import get_user_by_id
from apps.backend.infrastructure.benchmark_runner import start_benchmark_run
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "operator_agent_config"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "operator"
TOOL_LABEL = "Operator agent config tuning"
TOOL_DESCRIPTION = "Admin-only: read/apply agent-config knobs, changelog, start/get benchmark runs."
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_MIN_ROLE = "admin"
TOOL_CAPABILITIES = ("operator.console",)
_CAP = ("operator.console",)
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


def _knob_public(knob: dict[str, Any], *, tenant_id: int) -> dict[str, Any]:
    from apps.backend.infrastructure import agent_config_effective

    kid = str(knob.get("id") or "")
    layer = str(knob.get("layer") or "")
    out = dict(knob)
    if layer in ("code", "rubric", "bench") or not knob.get("writable"):
        out["effective"] = None
        out["source"] = "git" if layer in ("code", "rubric", "bench") else "file_default"
        return out
    val, src = agent_config_effective.effective_value(kid, tenant_id=tenant_id)
    out["effective"] = val
    out["source"] = src
    if knob.get("bootstrap_env_key"):
        out["bootstrap_env"] = knob["bootstrap_env_key"]
    return out


def agent_config_knobs(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    writable_only = bool(arguments.get("writable_only"))
    ui_group = str(arguments.get("ui_group") or "").strip() or None
    knobs = []
    for raw in all_knobs():
        if ui_group and str(raw.get("ui_group") or "") != ui_group:
            continue
        if writable_only and not raw.get("writable"):
            continue
        knobs.append(_knob_public(dict(raw), tenant_id=tid))
    reg = load_knob_registry()
    return _ok({"registry_version": reg.get("version"), "knobs": knobs})


def agent_config_snapshot(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    return _ok(snapshot(tenant_id=tid))


def agent_config_apply(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, uid = g
    patches = arguments.get("patches")
    if not isinstance(patches, list) or not patches:
        return _err("patches array required")
    session_id = _parse_uuid(arguments.get("session_id"), field="session_id")
    experiment_id = _parse_uuid(arguments.get("experiment_id"), field="experiment_id")
    result = agent_config_service.apply_patches(
        tenant_id=tid,
        patches=[dict(p) for p in patches if isinstance(p, dict)],
        actor_type="operator_agent",
        actor_user_id=uid,
        actor_agent_id="operator",
        session_id=session_id,
        experiment_id=experiment_id,
        hypothesis=str(arguments.get("hypothesis") or "").strip() or None,
    )
    if not result.get("ok"):
        return _err("validation failed", validation=result.get("validation"))
    benchmark_run_id = None
    if bool(arguments.get("trigger_benchmark")):
        bench = arguments.get("benchmark") if isinstance(arguments.get("benchmark"), dict) else {}
        suite = str(bench.get("suite") or bench.get("suite_preset") or "routing-core").strip()
        profiles = bench.get("profiles") or []
        if not profiles:
            return _err("benchmark.profiles required when trigger_benchmark=true")
        cohort = {
            "fingerprint": result.get("fingerprint"),
            "session_id": str(session_id) if session_id else None,
            "experiment_id": str(experiment_id) if experiment_id else None,
        }
        if session_id:
            sess = agent_config_store.get_session(session_id, tenant_id=tid)
            if sess:
                cohort["cohort_label"] = sess.get("cohort_label")

        async def _start() -> dict[str, Any]:
            return await start_benchmark_run(
                tenant_id=tid,
                user_id=uid,
                suite=suite,
                profiles=profiles,
                scenarios=bench.get("scenarios"),
                fixtures=bench.get("fixtures"),
                tier_max=bench.get("tier_max"),
                admin_user_id=uid,
                cohort_json=cohort,
            )

        try:
            row = asyncio.get_event_loop().run_until_complete(_start())
        except RuntimeError:
            row = asyncio.run(_start())
        benchmark_run_id = str(row.get("id"))
        if session_id:
            agent_config_store.append_session_run(session_id, tenant_id=tid, run_id=uuid.UUID(benchmark_run_id))
    return _ok({**result, "benchmark_run_id": benchmark_run_id})


def agent_config_changelog(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    limit = int(arguments.get("limit") or 50)
    session_id = _parse_uuid(arguments.get("session_id"), field="session_id")
    rows = agent_config_store.list_changelog(tid, limit=limit, session_id=session_id)
    return _ok({"events": rows})


def benchmark_run_start(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, uid = g
    suite = str(arguments.get("suite") or "").strip()
    profiles = arguments.get("profiles")
    if not suite or not isinstance(profiles, list) or not profiles:
        return _err("suite and profiles required")
    cohort = {"fingerprint": compute_fingerprint(tenant_id=tid)}
    session_id = _parse_uuid(arguments.get("session_id"), field="session_id")
    experiment_id = _parse_uuid(arguments.get("experiment_id"), field="experiment_id")
    if session_id:
        cohort["session_id"] = str(session_id)
        sess = agent_config_store.get_session(session_id, tenant_id=tid)
        if sess:
            cohort["cohort_label"] = sess.get("cohort_label")
    if experiment_id:
        cohort["experiment_id"] = str(experiment_id)
    label = str(arguments.get("cohort_label") or "").strip()
    if label:
        cohort["cohort_label"] = label
    harness = str(arguments.get("harness_preset") or "observability").strip().lower()
    if harness in ("observability", "chat_parity"):
        cohort["harness_preset"] = harness

    async def _start() -> dict[str, Any]:
        return await start_benchmark_run(
            tenant_id=tid,
            user_id=uid,
            suite=suite,
            profiles=[dict(p) for p in profiles if isinstance(p, dict)],
            scenarios=arguments.get("scenarios"),
            fixtures=arguments.get("fixtures"),
            tier_max=arguments.get("tier_max"),
            run_as_user_id=_parse_uuid(arguments.get("run_as_user_id"), field="run_as_user_id") or uid,
            admin_user_id=uid,
            scenario_timeout_sec=arguments.get("scenario_timeout_sec"),
            max_tool_rounds_override=arguments.get("max_tool_rounds_override"),
            scenario_failure_retries=int(arguments.get("scenario_failure_retries") or 0),
            retain_workspaces=bool(arguments.get("retain_workspaces")),
            prompt_locale=str(arguments.get("prompt_locale") or "en"),
            cohort_json=cohort,
            harness_preset=harness if harness in ("observability", "chat_parity") else None,
        )

    try:
        row = asyncio.get_event_loop().run_until_complete(_start())
    except RuntimeError:
        row = asyncio.run(_start())
    run_id = uuid.UUID(str(row["id"]))
    if session_id:
        agent_config_store.append_session_run(session_id, tenant_id=tid, run_id=run_id)
    if experiment_id:
        agent_config_store.append_experiment_run(experiment_id, tenant_id=tid, run_id=run_id)
    return _ok({"run": benchmark_runs_store.get_run(run_id)})


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
    out = dict(row)
    out.pop("report_json", None)
    return _ok({"run": out})


def agents_list(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    return _ok({"agents": reg.to_list_dict()})


def agents_get(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    aid = str(arguments.get("agent_id") or "").strip()
    if not aid:
        return _err("agent_id required")
    from apps.backend.domain.agent_registry import get_agent_registry

    agent = get_agent_registry().get_agent(aid)
    if not agent:
        return _err("agent not found")
    return _ok({"agent": agent})


def tuning_session_create(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    label = str(arguments.get("label") or "").strip()
    cohort_label = str(arguments.get("cohort_label") or label).strip()
    if not label or not cohort_label:
        return _err("label and cohort_label required")
    fp = compute_fingerprint(tenant_id=tid)
    session = agent_config_store.create_session(
        tenant_id=tid,
        label=label,
        hypothesis=str(arguments.get("hypothesis") or "").strip() or None,
        cohort_label=cohort_label,
        baseline_fingerprint=fp,
    )
    return _ok({"session": session})


def tuning_session_validate(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    sid = _parse_uuid(arguments.get("session_id"), field="session_id")
    if not sid:
        return _err("session_id required")
    session = agent_config_store.get_session(sid, tenant_id=tid)
    if not session:
        return _err("session not found")
    fp = compute_fingerprint(tenant_id=tid)
    baseline = str(session.get("baseline_fingerprint") or "")
    return _ok(
        {
            "session_id": str(sid),
            "current_fingerprint": fp,
            "baseline_fingerprint": baseline,
            "changed": fp != baseline if baseline else False,
        }
    )


def tuning_session_close(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    sid = _parse_uuid(arguments.get("session_id"), field="session_id")
    if not sid:
        return _err("session_id required")
    fp = compute_fingerprint(tenant_id=tid)
    session = agent_config_store.close_session(sid, tenant_id=tid, current_fingerprint=fp)
    if not session:
        return _err("session not found")
    return _ok({"session": session})


def benchmark_experiment_create(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, _uid = g
    label = str(arguments.get("label") or "").strip()
    if not label:
        return _err("label required")
    exp = agent_config_store.create_experiment(
        tenant_id=tid,
        label=label,
        hypothesis=str(arguments.get("hypothesis") or "").strip() or None,
        session_id=_parse_uuid(arguments.get("session_id"), field="session_id"),
        fingerprint_at_start=compute_fingerprint(tenant_id=tid),
        suite_preset=str(arguments.get("suite_preset") or "").strip() or None,
        harness_preset=str(arguments.get("harness_preset") or "").strip() or None,
        pending_patches=arguments.get("pending_patches") if isinstance(arguments.get("pending_patches"), list) else None,
    )
    return _ok({"experiment": exp})


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


def benchmark_experiment_run(arguments: dict[str, Any]) -> str:
    g = _require_admin()
    if isinstance(g, str):
        return g
    tid, uid = g
    eid = _parse_uuid(arguments.get("experiment_id"), field="experiment_id")
    if not eid:
        return _err("experiment_id required")
    exp = agent_config_store.get_experiment(eid, tenant_id=tid)
    if not exp:
        return _err("experiment not found")
    profiles = arguments.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return _err("profiles required")
    if bool(arguments.get("apply_pending_patches")) and exp.get("pending_patches_json"):
        patches = exp.get("pending_patches_json") or []
        if isinstance(patches, list) and patches:
            agent_config_service.apply_patches(
                tenant_id=tid,
                patches=[dict(p) for p in patches if isinstance(p, dict)],
                actor_type="operator_agent",
                actor_user_id=uid,
                experiment_id=eid,
                hypothesis=str(exp.get("hypothesis") or "") or None,
            )
    suite = str(arguments.get("suite") or exp.get("suite_preset") or "routing-core").strip()
    harness = str(arguments.get("harness_preset") or exp.get("harness_preset") or "observability").strip().lower()
    if harness not in ("observability", "chat_parity"):
        harness = "observability"
    cohort = {
        "fingerprint": compute_fingerprint(tenant_id=tid),
        "experiment_id": str(eid),
        "cohort_label": str(exp.get("label") or eid),
        "harness_preset": harness,
    }
    session_raw = exp.get("session_id")
    if session_raw:
        cohort["session_id"] = str(session_raw)

    async def _start() -> dict[str, Any]:
        return await start_benchmark_run(
            tenant_id=tid,
            user_id=uid,
            suite=suite,
            profiles=[dict(p) for p in profiles if isinstance(p, dict)],
            scenarios=arguments.get("scenarios"),
            admin_user_id=uid,
            prompt_locale=str(arguments.get("prompt_locale") or "en"),
            cohort_json=cohort,
            harness_preset=harness,
        )

    try:
        row = asyncio.get_event_loop().run_until_complete(_start())
    except RuntimeError:
        row = asyncio.run(_start())
    run_id = uuid.UUID(str(row["id"]))
    agent_config_store.append_experiment_run(eid, tenant_id=tid, run_id=run_id)
    return _ok({"run": benchmark_runs_store.get_run(run_id), "experiment_id": str(eid)})


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "agent_config_knobs": agent_config_knobs,
    "agent_config_snapshot": agent_config_snapshot,
    "agent_config_apply": agent_config_apply,
    "agent_config_changelog": agent_config_changelog,
    "benchmark_run_start": benchmark_run_start,
    "benchmark_run_get": benchmark_run_get,
    "agents_list": agents_list,
    "agents_get": agents_get,
    "tuning_session_create": tuning_session_create,
    "tuning_session_validate": tuning_session_validate,
    "tuning_session_close": tuning_session_close,
    "benchmark_experiment_create": benchmark_experiment_create,
    "benchmark_experiment_get": benchmark_experiment_get,
    "benchmark_experiment_run": benchmark_experiment_run,
}

for _name in HANDLERS:
    AGENT_TOOL_META_BY_NAME[_name] = {"min_role": "admin", "capabilities": _CAP}


def _tool_fn(name: str, desc: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "TOOL_DESCRIPTION": desc,
            "parameters": parameters,
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool_fn(
        "agent_config_knobs",
        "List agent tuning knobs (registry-driven). Optional writable_only, ui_group.",
        {
            "type": "object",
            "properties": {
                "writable_only": {"type": "boolean"},
                "ui_group": {"type": "string"},
            },
        },
    ),
    _tool_fn(
        "agent_config_snapshot",
        "Export effective agent config snapshot + fingerprint.",
        {"type": "object", "properties": {}},
    ),
    _tool_fn(
        "agent_config_apply",
        "Apply agent-config patches (DB). Optional trigger_benchmark + benchmark body.",
        {
            "type": "object",
            "properties": {
                "patches": {"type": "array"},
                "session_id": {"type": "string"},
                "experiment_id": {"type": "string"},
                "hypothesis": {"type": "string"},
                "trigger_benchmark": {"type": "boolean"},
                "benchmark": {"type": "object"},
            },
            "required": ["patches"],
        },
    ),
    _tool_fn(
        "agent_config_changelog",
        "List agent-config changelog events.",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "session_id": {"type": "string"},
            },
        },
    ),
    _tool_fn(
        "benchmark_run_start",
        "Start a benchmark run when the user asks. Requires suite + profiles.",
        {
            "type": "object",
            "properties": {
                "suite": {"type": "string"},
                "profiles": {"type": "array"},
                "scenarios": {"type": "array"},
                "session_id": {"type": "string"},
                "experiment_id": {"type": "string"},
                "cohort_label": {"type": "string"},
            },
            "required": ["suite", "profiles"],
        },
    ),
    _tool_fn(
        "benchmark_run_get",
        "Get benchmark run status (without full report_json).",
        {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    ),
    _tool_fn("agents_list", "List registered agents.", {"type": "object", "properties": {}}),
    _tool_fn(
        "agents_get",
        "Get one agent definition by id.",
        {
            "type": "object",
            "properties": {"agent_id": {"type": "string"}},
            "required": ["agent_id"],
        },
    ),
    _tool_fn(
        "tuning_session_create",
        "Open a tuning session with baseline fingerprint.",
        {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "cohort_label": {"type": "string"},
                "hypothesis": {"type": "string"},
            },
            "required": ["label", "cohort_label"],
        },
    ),
    _tool_fn(
        "tuning_session_validate",
        "Compare session baseline fingerprint to current.",
        {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    ),
    _tool_fn(
        "tuning_session_close",
        "Close tuning session.",
        {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    ),
    _tool_fn(
        "benchmark_experiment_create",
        "Create benchmark experiment record.",
        {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "hypothesis": {"type": "string"},
                "session_id": {"type": "string"},
                "suite_preset": {"type": "string"},
            },
            "required": ["label"],
        },
    ),
    _tool_fn(
        "benchmark_experiment_get",
        "Get experiment by id.",
        {
            "type": "object",
            "properties": {"experiment_id": {"type": "string"}},
            "required": ["experiment_id"],
        },
    ),
    _tool_fn(
        "benchmark_experiment_run",
        "Start benchmark for an experiment (optional apply pending patches).",
        {
            "type": "object",
            "properties": {
                "experiment_id": {"type": "string"},
                "profiles": {"type": "array"},
                "suite": {"type": "string"},
                "scenarios": {"type": "array", "items": {"type": "string"}},
                "harness_preset": {"type": "string", "enum": ["observability", "chat_parity"]},
                "apply_pending_patches": {"type": "boolean"},
                "prompt_locale": {"type": "string"},
            },
            "required": ["experiment_id", "profiles"],
        },
    ),
]
