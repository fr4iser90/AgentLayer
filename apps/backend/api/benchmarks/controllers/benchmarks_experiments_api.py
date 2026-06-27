"""Benchmark experiment, review, analysis, and report endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from apps.backend.api.benchmarks.controllers.benchmarks_admin_api import (
    BenchmarkReviewBody,
    ExperimentCreateBody,
    ExperimentPatchBody,
    ExperimentRunBody,
    _public_run_detail,
)
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import benchmark_runs_store
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import analyze_runs
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import run_review
from apps.backend.application.identity.use_cases.request_auth import require_admin
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import start_benchmark_run
from apps.backend.application.benchmarks.use_cases.benchmark_controller_services import db

router = APIRouter()

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
            prompt_variant=body.prompt_variant.strip().lower(),
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
