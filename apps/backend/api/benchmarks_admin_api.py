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
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "run": _public_run(row)}
