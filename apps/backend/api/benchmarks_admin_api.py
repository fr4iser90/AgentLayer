"""Admin API: model benchmark runs (suites, start, history)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.core.config import config
from apps.backend.infrastructure import benchmark_runs_store
from apps.backend.infrastructure.auth import get_user_by_id, require_admin
from apps.backend.infrastructure.benchmark_runner import (
    benchmark_catalog,
    list_benchmark_llm_providers,
    list_suites,
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
    profiles: list[BenchmarkProfileInput] = Field(..., min_length=1, max_length=8)
    scenarios: list[str] | None = Field(default=None, max_length=32)
    fixtures: list[str] | None = Field(default=None, max_length=16)
    tier_max: int | None = Field(default=None, ge=1, le=4)
    run_as_user_id: uuid.UUID | None = None
    friend_user_id: uuid.UUID | None = None


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
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "run": _public_run(row)}
