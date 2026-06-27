"""Admin API: model benchmark runs (suites, start, history)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import config
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import benchmark_runs_store
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import benchmark_tuning_store
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import (
    create_tuning_session,
    run_tuning_session,
    tuning_presets,
)
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import aggregate_benchmark_stats
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import analyze_runs, compare_cohorts, list_cohorts, _cohort_label_from_run, _fingerprint_from_run
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import run_review
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import agent_config_service
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import agent_config_store
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import compute_fingerprint
from apps.backend.application.identity.use_cases.request_auth import get_user_by_id, require_admin
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import (
    benchmark_catalog,
    list_benchmark_llm_providers,
    list_suites,
    request_benchmark_cancel,
    start_benchmark_run,
)
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import db

router = APIRouter(prefix="/v1/admin/benchmarks", tags=["benchmarks-admin"])

_BENCH_READINESS_SECRETS = ("gmail", "ssc_api_key")


class BenchmarkProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = ""
    model: str = ""
    agent_id: str = "general"
    endpoint_id: int | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_header_name: str | None = None
    catalog_owned_by: str | None = None


class StartBenchmarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str = Field(..., min_length=1, max_length=64)
    profiles: list[BenchmarkProfileInput] = Field(..., min_length=1)
    scenarios: list[str] | None = Field(default=None, max_length=32)
    fixtures: list[str] | None = Field(default=None, max_length=16)
    tier_max: int | None = Field(default=None, ge=1, le=4)
    run_as_user_id: uuid.UUID | None = None
    friend_user_id: uuid.UUID | None = None
    scenario_timeout_sec: float | None = Field(default=None, ge=30, le=86400)
    max_tool_rounds_override: int | None = Field(default=None, ge=1, le=512)
    scenario_failure_retries: int = Field(default=0, ge=0, le=20)
    retain_workspaces: bool = False
    prompt_locale: str = Field(default="en", min_length=2, max_length=16)
    prompt_variant: str = Field(default="canonical", min_length=1, max_length=32)
    cohort_label: str | None = Field(default=None, max_length=128)
    harness_overrides: list[dict[str, Any]] | None = None


class StartBenchmarkTuneBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: BenchmarkProfileInput
    mode: str = Field(default="fast", max_length=32)
    run_as_user_id: uuid.UUID | None = None
    friend_user_id: uuid.UUID | None = None
    reviewer_mode: str = Field(default="off", max_length=32)
    reviewer_provider_id: str | None = Field(default=None, max_length=128)
    reviewer_model: str | None = Field(default=None, max_length=256)
    max_patch_rounds: int = Field(default=0, ge=0, le=10)


class ExperimentCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=128)
    hypothesis: str | None = Field(default=None, max_length=4000)
    session_id: uuid.UUID | None = None
    suite_preset: str | None = Field(default=None, max_length=64)
    harness_preset: str | None = Field(default=None, max_length=64)
    pending_patches: list[dict[str, Any]] | None = None


class ExperimentPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=128)
    hypothesis: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=32)
    pending_patches: list[dict[str, Any]] | None = None


class BenchmarkReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    run_ids: list[uuid.UUID] | None = None
    mode: str = Field(default="deterministic", max_length=32)
    reviewer_model: str | None = Field(default=None, max_length=256)
    summary_hint: str | None = Field(default=None, max_length=4000)


class ExperimentRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str | None = Field(default=None, max_length=64)
    profiles: list[dict[str, Any]] | None = None
    scenarios: list[str] | None = None
    apply_pending_patches: bool = True
    prompt_locale: str = Field(default="en", min_length=2, max_length=16)
    prompt_variant: str = Field(default="canonical", min_length=1, max_length=32)


class BulkDeleteRunsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str | None = Field(default=None, max_length=64)
    older_than_days: int | None = Field(default=None, ge=1, le=3650)


def _assert_tenant_user(user_id: uuid.UUID, tenant_id: int) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    if db.user_tenant_id(user_id) != tenant_id:
        raise HTTPException(status_code=403, detail="user not in this tenant")
    return {
        "id": str(user.id),
        "email": user.email or "",
        "role": user.role,
    }


def _sandbox_stats_for_user(user_id: uuid.UUID) -> dict[str, int | bool]:
    from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import benchmark_sandbox_snapshot

    return benchmark_sandbox_snapshot(user_id, include_legacy_prefix=True)


def _readiness_for_user(user_id: uuid.UUID) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    secrets_enabled = bool(config.SECRETS_MASTER_KEY)
    configured: set[str] = set()
    if secrets_enabled:
        configured = {k.lower() for k in db.user_secret_list_service_keys(user_id)}
    return {
        "user_id": str(user_id),
        "email": user.email or "",
        "role": user.role,
        "secrets_enabled": secrets_enabled,
        "secrets": {key: key in configured for key in _BENCH_READINESS_SECRETS},
        **_sandbox_stats_for_user(user_id),
    }


def _public_run(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out.pop("report_json", None)
    return out


def _public_run_detail(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


@router.get("/suites")
async def get_benchmark_suites(request: Request) -> dict:
    await require_admin(request)
    return {"ok": True, "suites": list_suites()}


@router.get("/catalog")
async def get_benchmark_catalog(request: Request) -> dict:
    await require_admin(request)
    return {"ok": True, **benchmark_catalog()}


@router.get("/llm-providers")
async def get_benchmark_llm_providers(request: Request) -> dict:
    """LLM providers for benchmark compare list (.env LLM_PROVIDER_* + Admin DB endpoints)."""
    await require_admin(request)
    return {"ok": True, "providers": list_benchmark_llm_providers()}


@router.get("/run-readiness")
async def get_benchmark_run_readiness(request: Request, user_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    _assert_tenant_user(user_id, tid)
    return {"ok": True, **_readiness_for_user(user_id)}


def _cleanup_benchmark_sandboxes_sync(user_id: uuid.UUID) -> dict[str, Any]:
    import os

    from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import (
        prepare_benchmark_sandbox_cleanup,
    )
    from tests.benchmarks.agent.harness import bench_base_url, load_bench_env, require_server
    from tests.e2e.support.helpers import resolve_local_agent_base_url

    load_bench_env()
    os.environ.setdefault("AGENT_E2E_BASE_URL", resolve_local_agent_base_url())
    require_server()
    return prepare_benchmark_sandbox_cleanup(user_id, include_legacy_prefix=True)


@router.post("/cleanup-resources")
@router.post("/cleanup-workspaces")
async def post_cleanup_benchmark_resources(request: Request, user_id: uuid.UUID) -> dict:
    """Delete all benchmark sandboxes (workspaces, dashboards, conversations) for the run-as user."""
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    _assert_tenant_user(user_id, tid)
    try:
        cleanup = await asyncio.to_thread(_cleanup_benchmark_sandboxes_sync, user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:2000]) from exc
    return {"ok": True, "cleanup": cleanup, **_readiness_for_user(user_id)}


@router.get("/stats")
async def get_benchmark_stats(
    request: Request,
    limit: int = 200,
    suite: str | None = None,
    since_days: int | None = None,
    cohort: str | None = None,
    fingerprint: str | None = None,
    badge_min_samples: int = 2,
    fastest_min_pass_rate: float = 0.0,
) -> dict:
    """Cross-run leaderboard: pass rate and latency by provider + model."""
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    since = since_days if since_days is not None and since_days >= 1 else None
    if since is not None:
        since = min(3650, since)
    badge_min = max(1, min(100, int(badge_min_samples)))
    fastest_threshold = max(0.0, min(1.0, float(fastest_min_pass_rate)))
    rows = benchmark_runs_store.list_runs_for_stats(
        tenant_id=tid,
        limit=limit,
        suite=suite,
        since_days=since,
    )
    if cohort:
        rows = [r for r in rows if _cohort_label_from_run(r) == cohort]
    if fingerprint:
        rows = [r for r in rows if _fingerprint_from_run(r) == fingerprint]
    return {
        "ok": True,
        "stats": aggregate_benchmark_stats(
            rows,
            suite_filter=suite,
            since_days=since,
            badge_min_samples=badge_min,
            fastest_min_pass_rate=fastest_threshold,
        ),
    }


@router.post("/runs/bulk-delete")
async def bulk_delete_benchmark_runs(request: Request, body: BulkDeleteRunsBody) -> dict:
    """Delete finished benchmark runs (history + stats source). Skips queued/running."""
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    deleted = benchmark_runs_store.delete_finished_runs(
        tenant_id=tid,
        suite=body.suite.strip() if body.suite else None,
        older_than_days=body.older_than_days,
    )
    return {"ok": True, "deleted": deleted}


@router.get("/runs")
async def list_benchmark_runs(request: Request, limit: int = 50) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    rows = benchmark_runs_store.list_runs(tenant_id=tid, limit=limit)
    return {"ok": True, "runs": [_public_run(r) for r in rows]}


@router.get("/runs/{run_id}")
async def get_benchmark_run(request: Request, run_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    row = benchmark_runs_store.get_run(run_id)
    if not row or int(row.get("tenant_id") or 0) != tid:
        raise HTTPException(status_code=404, detail="benchmark run not found")
    return {"ok": True, "run": _public_run_detail(row)}


@router.delete("/runs/{run_id}")
async def delete_benchmark_run(request: Request, run_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    outcome = benchmark_runs_store.delete_run(run_id=run_id, tenant_id=tid)
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="benchmark run not found")
    if outcome == "running":
        raise HTTPException(
            status_code=409,
            detail="benchmark run is still queued or running",
        )
    return {"ok": True, "deleted": str(run_id)}


@router.post("/runs/{run_id}/cancel")
async def cancel_benchmark_run(request: Request, run_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    row = benchmark_runs_store.get_run(run_id)
    if not row or int(row.get("tenant_id") or 0) != tid:
        raise HTTPException(status_code=404, detail="benchmark run not found")
    if not request_benchmark_cancel(run_id):
        status = str(row.get("status") or "")
        if status in ("cancelled", "completed", "failed"):
            return {"ok": True, "run": _public_run(row), "already_finished": True}
        raise HTTPException(status_code=409, detail=f"benchmark run is not active (status={status})")
    return {"ok": True, "run_id": str(run_id), "cancelling": True}


@router.post("/runs")
async def post_start_benchmark(request: Request, body: StartBenchmarkBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    run_as_id = body.run_as_user_id or admin.id
    _assert_tenant_user(run_as_id, tid)
    if body.friend_user_id is not None:
        friend = _assert_tenant_user(body.friend_user_id, tid)
        if friend["id"] == str(run_as_id):
            raise HTTPException(status_code=400, detail="friend user must differ from run-as user")
    profiles = [p.model_dump(exclude_none=True) for p in body.profiles]
    cohort: dict[str, Any] = {"fingerprint": compute_fingerprint(tenant_id=tid)}
    if body.cohort_label:
        cohort["cohort_label"] = body.cohort_label.strip()
    overrides = body.harness_overrides or []
    if overrides:
        validation = agent_config_service.validate_patches(overrides)
        if not validation.get("valid"):
            raise HTTPException(status_code=400, detail=validation.get("errors") or "invalid harness_overrides")
        cohort["harness_overrides"] = overrides
    try:
        row = await start_benchmark_run(
            tenant_id=tid,
            user_id=admin.id,
            suite=body.suite.strip(),
            profiles=profiles,
            scenarios=body.scenarios,
            fixtures=body.fixtures,
            tier_max=body.tier_max,
            run_as_user_id=run_as_id,
            friend_user_id=body.friend_user_id,
            admin_user_id=admin.id,
            scenario_timeout_sec=body.scenario_timeout_sec,
            max_tool_rounds_override=body.max_tool_rounds_override,
            scenario_failure_retries=body.scenario_failure_retries,
            retain_workspaces=body.retain_workspaces,
            prompt_locale=body.prompt_locale.strip().lower(),
            prompt_variant=body.prompt_variant.strip().lower(),
            cohort_json=cohort,
            harness_preset=None,
            use_harness_matrix=False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "run": _public_run(row)}


@router.get("/tune/presets")
async def get_benchmark_tune_presets(request: Request) -> dict:
    await require_admin(request)
    return {"ok": True, "presets": tuning_presets()}


@router.get("/tune/sessions")
async def list_benchmark_tune_sessions(request: Request, limit: int = 50) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    return {
        "ok": True,
        "sessions": benchmark_tuning_store.list_sessions(tenant_id=tid, limit=limit),
    }


@router.post("/tune/sessions")
async def post_start_benchmark_tune(request: Request, body: StartBenchmarkTuneBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    run_as_id = body.run_as_user_id or admin.id
    _assert_tenant_user(run_as_id, tid)
    if body.friend_user_id is not None:
        friend = _assert_tenant_user(body.friend_user_id, tid)
        if friend["id"] == str(run_as_id):
            raise HTTPException(status_code=400, detail="friend user must differ from run-as user")
    profile = body.profile.model_dump(exclude_none=True)
    validation = agent_config_service.validate_patches(
        [p for preset in tuning_presets() for p in (preset.get("patches") or [])]
    )
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail=validation.get("errors") or "invalid tuning presets")
    try:
        session = create_tuning_session(
            tenant_id=tid,
            user_id=admin.id,
            mode=body.mode,
            profile=profile,
            run_as_user_id=run_as_id,
            friend_user_id=body.friend_user_id,
            reviewer_mode=body.reviewer_mode,
            reviewer_provider_id=body.reviewer_provider_id,
            reviewer_model=body.reviewer_model,
            max_patch_rounds=body.max_patch_rounds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asyncio.create_task(run_tuning_session(uuid.UUID(str(session["id"]))))
    return {"ok": True, "session": session}


@router.get("/tune/sessions/{session_id}")
async def get_benchmark_tune_session(request: Request, session_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    session = benchmark_tuning_store.get_session(session_id, tenant_id=tid)
    if not session:
        raise HTTPException(status_code=404, detail="benchmark tuning session not found")
    return {"ok": True, "session": session}


@router.post("/tune/sessions/{session_id}/promote")
async def promote_benchmark_tune_session(request: Request, session_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    session = benchmark_tuning_store.get_session(session_id, tenant_id=tid)
    if not session:
        raise HTTPException(status_code=404, detail="benchmark tuning session not found")
    if session.get("status") != "completed":
        raise HTTPException(status_code=409, detail="tuning session is not completed")
    patches = session.get("best_patches_json")
    if not isinstance(patches, list) or not patches:
        raise HTTPException(status_code=409, detail="tuning session has no promotable patches")
    result = agent_config_service.apply_model_patches(
        tenant_id=tid,
        catalog_owned_by=str(session.get("catalog_owned_by") or ""),
        model=str(session.get("model") or ""),
        patches=[dict(p) for p in patches if isinstance(p, dict)],
        actor_type="user",
        actor_user_id=admin.id,
        label=f"autotune:{session.get('mode') or 'benchmark'}",
        hypothesis=f"Promoted from benchmark tuning session {session_id}",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("validation") or "promotion failed")
    benchmark_tuning_store.update_session(
        session_id,
        promoted_at=datetime.now(timezone.utc),
    )
    return {"ok": True, "result": result}


@router.get("/analysis")
async def get_benchmark_analysis(
    request: Request,
    cohort: str | None = None,
    fingerprint: str | None = None,
    git_sha: str | None = None,
    suite: str | None = None,
    since_days: int | None = None,
    experiment_id: uuid.UUID | None = None,
    limit: int = 200,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    rows = benchmark_runs_store.list_runs_for_stats(
        tenant_id=tid,
        limit=limit,
        suite=suite,
        since_days=since_days if since_days and since_days >= 1 else None,
    )
    analysis = analyze_runs(
        rows,
        cohort=cohort,
        fingerprint=fingerprint,
        suite=suite,
        since_days=since_days,
        experiment_id=str(experiment_id) if experiment_id else None,
    )
    if git_sha:
        analysis["git_sha_filter"] = git_sha
    return {"ok": True, **analysis}


@router.get("/cohorts")
async def get_benchmark_cohorts(request: Request, limit: int = 200) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=limit)
    return {"ok": True, "cohorts": list_cohorts(rows)}


@router.get("/cohorts/compare")
async def get_benchmark_cohort_compare(
    request: Request,
    cohort_a: str,
    cohort_b: str,
    suite: str | None = None,
    limit: int = 200,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tid, limit=limit, suite=suite)
    return {"ok": True, **compare_cohorts(rows, cohort_a=cohort_a, cohort_b=cohort_b, suite=suite)}

from apps.backend.api.benchmarks.controllers.benchmarks_experiments_api import router as experiments_router

router.include_router(experiments_router)
