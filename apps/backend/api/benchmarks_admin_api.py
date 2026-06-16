"""Admin API: model benchmark runs (suites, start, history)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.core.config import config
from apps.backend.infrastructure import benchmark_runs_store
from apps.backend.infrastructure.benchmark_stats import aggregate_benchmark_stats
from apps.backend.infrastructure.benchmark_analysis import analyze_runs, compare_cohorts, list_cohorts, _cohort_label_from_run, _fingerprint_from_run
from apps.backend.infrastructure.benchmark_review_service import run_review
from apps.backend.infrastructure import agent_config_service
from apps.backend.infrastructure import agent_config_store
from apps.backend.infrastructure.agent_config_fingerprint import compute_fingerprint
from apps.backend.infrastructure.auth import get_user_by_id, require_admin
from apps.backend.infrastructure.benchmark_runner import (
    benchmark_catalog,
    list_benchmark_llm_providers,
    list_suites,
    request_benchmark_cancel,
    start_benchmark_run,
)
from apps.backend.infrastructure.db import db

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
    session_id: uuid.UUID | None = None
    experiment_id: uuid.UUID | None = None
    cohort_label: str | None = Field(default=None, max_length=128)
    harness_preset: str | None = Field(default="observability", max_length=64)
    use_harness_matrix: bool = False


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
    from apps.backend.infrastructure.benchmark_resource_service import benchmark_sandbox_snapshot

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

    from apps.backend.infrastructure.benchmark_resource_service import (
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
    harness = (body.harness_preset or "observability").strip().lower()
    if harness not in ("observability", "chat_parity"):
        raise HTTPException(status_code=400, detail="harness_preset must be observability or chat_parity")
    cohort["harness_preset"] = harness
    cohort["use_harness_matrix"] = bool(body.use_harness_matrix)
    if body.cohort_label:
        cohort["cohort_label"] = body.cohort_label.strip()
    if body.session_id:
        cohort["session_id"] = str(body.session_id)
        sess = agent_config_store.get_session(body.session_id, tenant_id=tid)
        if sess and not body.cohort_label:
            cohort["cohort_label"] = sess.get("cohort_label")
    if body.experiment_id:
        cohort["experiment_id"] = str(body.experiment_id)
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
            cohort_json=cohort,
            harness_preset=harness,
            use_harness_matrix=body.use_harness_matrix,
        )
        if body.session_id:
            agent_config_store.append_session_run(body.session_id, tenant_id=tid, run_id=uuid.UUID(str(row["id"])))
        if body.experiment_id:
            agent_config_store.append_experiment_run(
                body.experiment_id, tenant_id=tid, run_id=uuid.UUID(str(row["id"]))
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "run": _public_run(row)}


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


@router.get("/experiments")
async def list_benchmark_experiments(
    request: Request,
    limit: int = 50,
    session_id: uuid.UUID | None = None,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    return {"ok": True, "experiments": agent_config_store.list_experiments(tid, limit=limit, session_id=session_id)}


@router.post("/experiments")
async def create_benchmark_experiment(request: Request, body: ExperimentCreateBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    fp = compute_fingerprint(tenant_id=tid)
    exp = agent_config_store.create_experiment(
        tenant_id=tid,
        label=body.label.strip(),
        hypothesis=body.hypothesis,
        session_id=body.session_id,
        fingerprint_at_start=fp,
        suite_preset=body.suite_preset,
        harness_preset=body.harness_preset,
        pending_patches=body.pending_patches,
    )
    return {"ok": True, "experiment": exp}


@router.get("/experiments/{experiment_id}")
async def get_benchmark_experiment(request: Request, experiment_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    exp = agent_config_store.get_experiment(experiment_id, tenant_id=tid)
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"ok": True, "experiment": exp}


@router.patch("/experiments/{experiment_id}")
async def patch_benchmark_experiment(
    request: Request,
    experiment_id: uuid.UUID,
    body: ExperimentPatchBody,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    exp = agent_config_store.patch_experiment(
        experiment_id,
        tenant_id=tid,
        label=body.label,
        hypothesis=body.hypothesis,
        status=body.status,
        pending_patches=body.pending_patches,
    )
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"ok": True, "experiment": exp}


@router.post("/review")
async def post_benchmark_review(request: Request, body: BenchmarkReviewBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    review = run_review(
        tenant_id=tid,
        experiment_id=body.experiment_id,
        session_id=body.session_id,
        run_ids=body.run_ids,
        mode=body.mode,
        reviewer_model=body.reviewer_model,
        actor_type="user",
        summary_hint=body.summary_hint,
    )
    return {"ok": True, "review": review}


@router.get("/reviews/{review_id}")
async def get_benchmark_review(request: Request, review_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    review = agent_config_store.get_review(review_id, tenant_id=tid)
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    return {"ok": True, "review": review}


@router.get("/runs/{run_id}/analysis")
async def get_benchmark_run_analysis(request: Request, run_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    row = benchmark_runs_store.get_run(run_id)
    if not row or int(row.get("tenant_id") or 0) != tid:
        raise HTTPException(status_code=404, detail="benchmark run not found")
    analysis = analyze_runs([row])
    cohort = row.get("cohort_json") if isinstance(row.get("cohort_json"), dict) else {}
    return {
        "ok": True,
        "run_id": str(run_id),
        "suite": row.get("suite"),
        "status": row.get("status"),
        "cohort": cohort,
        "fingerprint": _fingerprint_from_run(row),
        "harness_preset": cohort.get("harness_preset") if isinstance(cohort, dict) else None,
        **analysis,
    }


@router.get("/runs/{run_id}/export")
async def export_benchmark_run(request: Request, run_id: uuid.UUID, format: str = "json") -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    row = benchmark_runs_store.get_run(run_id)
    if not row or int(row.get("tenant_id") or 0) != tid:
        raise HTTPException(status_code=404, detail="benchmark run not found")
    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "jsonl"):
        raise HTTPException(status_code=400, detail="format must be json or jsonl")
    return {"ok": True, "format": fmt, "run": row}


@router.post("/experiments/{experiment_id}/run")
async def run_benchmark_experiment(
    request: Request,
    experiment_id: uuid.UUID,
    body: ExperimentRunBody,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    exp = agent_config_store.get_experiment(experiment_id, tenant_id=tid)
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    if body.apply_pending_patches and exp.get("pending_patches_json"):
        patches = exp.get("pending_patches_json") or []
        if isinstance(patches, list) and patches:
            agent_config_service.apply_patches(
                tenant_id=tid,
                patches=[dict(p) for p in patches if isinstance(p, dict)],
                actor_type="user",
                actor_user_id=admin.id,
                experiment_id=experiment_id,
                hypothesis=str(exp.get("hypothesis") or "") or None,
            )
    suite = (body.suite or exp.get("suite_preset") or "routing-core").strip()
    profiles = body.profiles
    if not profiles:
        raise HTTPException(status_code=400, detail="profiles required to run experiment")
    cohort = {
        "fingerprint": compute_fingerprint(tenant_id=tid),
        "experiment_id": str(experiment_id),
        "cohort_label": str(exp.get("label") or experiment_id),
    }
    session_raw = exp.get("session_id")
    if session_raw:
        cohort["session_id"] = str(session_raw)
    harness = str(exp.get("harness_preset") or "observability").strip().lower()
    if harness not in ("observability", "chat_parity"):
        harness = "observability"
    cohort["harness_preset"] = harness
    try:
        row = await start_benchmark_run(
            tenant_id=tid,
            user_id=admin.id,
            suite=suite,
            profiles=profiles,
            scenarios=body.scenarios,
            admin_user_id=admin.id,
            prompt_locale=body.prompt_locale.strip().lower(),
            cohort_json=cohort,
            harness_preset=harness,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    agent_config_store.append_experiment_run(experiment_id, tenant_id=tid, run_id=uuid.UUID(str(row["id"])))
    return {"ok": True, "run": _public_run(row), "experiment_id": str(experiment_id)}


@router.get("/experiments/{experiment_id}/report")
async def get_benchmark_experiment_report(request: Request, experiment_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    report = agent_config_store.experiment_report(experiment_id, tenant_id=tid)
    if not report:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"ok": True, **report}
