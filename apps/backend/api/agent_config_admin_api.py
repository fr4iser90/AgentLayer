"""Admin API: registry-driven agent config tuning (knobs, apply, fingerprint, sessions)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.domain.agent_config_registry import is_harness_knob, knob_by_id, load_knob_registry
from apps.backend.infrastructure import agent_config_effective, agent_config_fingerprint, agent_config_service, agent_config_store
from apps.backend.infrastructure.auth import require_admin
from apps.backend.infrastructure.benchmark_runner import start_benchmark_run
from apps.backend.infrastructure.db import db

router = APIRouter(prefix="/v1/admin/agent-config", tags=["agent-config"])


class ConfigPatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knob_id: str = Field(..., min_length=1, max_length=128)
    value: Any = None


class ApplyConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patches: list[ConfigPatchItem] = Field(..., min_length=1, max_length=64)
    session_id: uuid.UUID | None = None
    experiment_id: uuid.UUID | None = None
    hypothesis: str | None = Field(default=None, max_length=4000)
    trigger_benchmark: bool = False
    benchmark: dict[str, Any] | None = None


class DraftConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patches: list[ConfigPatchItem] = Field(..., min_length=1, max_length=64)
    hypothesis: str | None = Field(default=None, max_length=4000)


class CreateSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=128)
    hypothesis: str | None = Field(default=None, max_length=4000)
    cohort_label: str = Field(..., min_length=1, max_length=128)


class PatchSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=128)
    hypothesis: str | None = Field(default=None, max_length=4000)


def _knob_public(
    knob: dict[str, Any],
    *,
    tenant_id: int,
    catalog_owned_by: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    kid = str(knob.get("id") or "")
    layer = str(knob.get("layer") or "")
    out = dict(knob)
    if layer in ("code", "rubric", "bench") or not knob.get("writable"):
        out["effective"] = None
        out["source"] = "git" if layer in ("code", "rubric", "bench") else "file_default"
        return out
    val, src = agent_config_effective.display_value(
        kid,
        tenant_id=tenant_id,
        catalog_owned_by=catalog_owned_by,
        model=model,
    )
    out["effective"] = val
    out["source"] = src
    if val is None and kid == "tool_routing.domain_order":
        out["effective_label"] = "router module scan order (no explicit override)"
    return out


def _changelog_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "at": row.get("created_at"),
        "actor": {
            "type": row.get("actor_type"),
            "user_id": row.get("actor_user_id"),
            "agent_id": row.get("actor_agent_id"),
        },
        "session_id": row.get("session_id"),
        "experiment_id": row.get("experiment_id"),
        "hypothesis": row.get("hypothesis"),
        "patches": row.get("patches_json") or [],
        "fingerprint_before": row.get("fingerprint_before"),
        "fingerprint_after": row.get("fingerprint_after"),
    }


class ApplyModelConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_owned_by: str = Field(..., min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=512)
    label: str | None = Field(default=None, max_length=128)
    patches: list[ConfigPatchItem] = Field(..., min_length=1, max_length=64)
    hypothesis: str | None = Field(default=None, max_length=4000)
    override_id: uuid.UUID | None = None


@router.get("/knobs")
async def get_agent_config_knobs(
    request: Request,
    ui_group: str | None = None,
    layer: str | None = None,
    benchmark_sensitive: bool | None = None,
    agent_id: str | None = None,
    writable_only: bool = False,
    harness_only: bool = False,
    catalog_owned_by: str | None = None,
    model: str | None = None,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    reg = load_knob_registry()
    knobs: list[dict[str, Any]] = []
    for raw in reg.get("knobs") or []:
        if not isinstance(raw, dict):
            continue
        if harness_only and not is_harness_knob(raw):
            continue
        if ui_group and str(raw.get("ui_group") or "") != ui_group:
            continue
        if layer and str(raw.get("layer") or "") != layer:
            continue
        if benchmark_sensitive is not None and bool(raw.get("benchmark_sensitive")) != benchmark_sensitive:
            continue
        if agent_id:
            affects = raw.get("affects_agents") or []
            if agent_id not in affects and affects:
                continue
        if writable_only and not raw.get("writable"):
            continue
        knobs.append(
            _knob_public(
                dict(raw),
                tenant_id=tid,
                catalog_owned_by=catalog_owned_by,
                model=model,
            )
        )
    return {
        "ok": True,
        "registry_version": reg.get("version"),
        "ui_groups": reg.get("ui_groups") or [],
        "knobs": knobs,
    }


@router.get("/knobs/{knob_id}")
async def get_agent_config_knob(request: Request, knob_id: str) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    knob = knob_by_id(knob_id)
    if not knob:
        raise HTTPException(status_code=404, detail="knob not found")
    events = agent_config_store.list_changelog(tid, limit=1)
    last = None
    for ev in events:
        patches = ev.get("patches_json") or []
        if any(str(p.get("knob_id") or "") == knob_id for p in patches if isinstance(p, dict)):
            last = _changelog_event(ev)
            break
    return {"ok": True, "knob": _knob_public(knob, tenant_id=tid), "last_changelog": last}


@router.get("/fingerprint")
async def get_agent_config_fingerprint(request: Request) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    return {"ok": True, **agent_config_fingerprint.fingerprint_response(tenant_id=tid)}


@router.get("/snapshot")
async def get_agent_config_snapshot(request: Request) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    return {"ok": True, **agent_config_fingerprint.snapshot(tenant_id=tid)}


@router.get("/changelog")
async def get_agent_config_changelog(
    request: Request,
    limit: int = 50,
    session_id: uuid.UUID | None = None,
    actor_type: str | None = None,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    rows = agent_config_store.list_changelog(
        tid, limit=limit, session_id=session_id, actor_type=actor_type
    )
    return {"ok": True, "events": [_changelog_event(r) for r in rows]}


@router.post("/initialize-defaults")
async def post_initialize_agent_config_defaults(request: Request, overwrite: bool = False) -> dict:
    """Write registry/file defaults into DB overrides (WebUI-owned, not .env)."""
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    result = agent_config_service.initialize_defaults_to_db(
        tenant_id=tid,
        actor_user_id=admin.id,
        overwrite=overwrite,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("validation"))
    return {"ok": True, **result}


@router.post("/draft")
async def post_agent_config_draft(request: Request, body: DraftConfigBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    patches = [p.model_dump() for p in body.patches]
    result = agent_config_service.draft_patches(tenant_id=tid, patches=patches, hypothesis=body.hypothesis)
    return {"ok": result.get("ok", False), **result}


@router.post("/apply")
async def post_agent_config_apply(request: Request, body: ApplyConfigBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    patches = [p.model_dump() for p in body.patches]
    result = agent_config_service.apply_patches(
        tenant_id=tid,
        patches=patches,
        actor_type="user",
        actor_user_id=admin.id,
        session_id=body.session_id,
        experiment_id=body.experiment_id,
        hypothesis=body.hypothesis,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("validation"))
    benchmark_run_id: str | None = None
    if body.trigger_benchmark and body.benchmark:
        bench = body.benchmark
        suite = str(bench.get("suite") or bench.get("suite_preset") or "routing-core").strip()
        profiles = bench.get("profiles") or []
        if not profiles:
            raise HTTPException(status_code=400, detail="benchmark.profiles required when trigger_benchmark=true")
        cohort = {
            "fingerprint": result.get("fingerprint"),
            "session_id": str(body.session_id) if body.session_id else None,
            "experiment_id": str(body.experiment_id) if body.experiment_id else None,
        }
        if body.session_id:
            sess = agent_config_store.get_session(body.session_id, tenant_id=tid)
            if sess:
                cohort["cohort_label"] = sess.get("cohort_label")
        try:
            row = await start_benchmark_run(
                tenant_id=tid,
                user_id=admin.id,
                suite=suite,
                profiles=profiles,
                scenarios=bench.get("scenarios"),
                fixtures=bench.get("fixtures"),
                tier_max=bench.get("tier_max"),
                admin_user_id=admin.id,
                cohort_json=cohort,
            )
            benchmark_run_id = str(row.get("id"))
            if body.session_id:
                agent_config_store.append_session_run(body.session_id, tenant_id=tid, run_id=uuid.UUID(benchmark_run_id))
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "applied": result.get("applied") or [],
        "skipped": result.get("skipped") or [],
        "fingerprint": result.get("fingerprint"),
        "changelog_event_id": result.get("changelog_event_id"),
        "benchmark_run_id": benchmark_run_id,
    }


@router.get("/model-overrides")
async def list_agent_config_model_overrides(request: Request) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    rows = agent_config_store.list_model_overrides(tid)
    return {"ok": True, "overrides": rows}


@router.post("/model-overrides/apply")
async def post_agent_config_model_apply(request: Request, body: ApplyModelConfigBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    patches = [p.model_dump() for p in body.patches]
    result = agent_config_service.apply_model_patches(
        tenant_id=tid,
        catalog_owned_by=body.catalog_owned_by.strip(),
        model=(body.model or "").strip() or None,
        label=body.label.strip() if body.label else None,
        patches=patches,
        actor_type="user",
        actor_user_id=admin.id,
        hypothesis=body.hypothesis,
        override_id=body.override_id,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("validation"))
    return {"ok": True, **result}


@router.delete("/model-overrides/{override_id}")
async def delete_agent_config_model_override(request: Request, override_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    deleted = agent_config_store.delete_model_override(override_id, tenant_id=tid)
    if not deleted:
        raise HTTPException(status_code=404, detail="model override not found")
    agent_config_effective.invalidate_agent_config_cache(tid)
    return {"ok": True, "deleted": str(override_id)}


@router.post("/sessions")
async def post_agent_config_session(request: Request, body: CreateSessionBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    fp = agent_config_fingerprint.compute_fingerprint(tenant_id=tid)
    session = agent_config_store.create_session(
        tenant_id=tid,
        label=body.label.strip(),
        hypothesis=body.hypothesis,
        cohort_label=body.cohort_label.strip(),
        baseline_fingerprint=fp,
    )
    return {"ok": True, "session": session}


@router.get("/sessions")
async def list_agent_config_sessions(request: Request, limit: int = 50) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    return {"ok": True, "sessions": agent_config_store.list_sessions(tid, limit=limit)}


@router.get("/sessions/{session_id}")
async def get_agent_config_session(request: Request, session_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    session = agent_config_store.get_session(session_id, tenant_id=tid)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, "session": session}


@router.patch("/sessions/{session_id}")
async def patch_agent_config_session(request: Request, session_id: uuid.UUID, body: PatchSessionBody) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    session = agent_config_store.patch_session_metadata(
        session_id,
        tenant_id=tid,
        label=body.label,
        hypothesis=body.hypothesis,
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, "session": session}


@router.post("/sessions/{session_id}/validate")
async def validate_agent_config_session(request: Request, session_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    session = agent_config_store.get_session(session_id, tenant_id=tid)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    fp = agent_config_fingerprint.compute_fingerprint(tenant_id=tid)
    baseline = str(session.get("baseline_fingerprint") or "")
    return {
        "ok": True,
        "session_id": str(session_id),
        "current_fingerprint": fp,
        "baseline_fingerprint": baseline,
        "changed": fp != baseline if baseline else False,
    }


@router.post("/sessions/{session_id}/close")
async def close_agent_config_session(request: Request, session_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    fp = agent_config_fingerprint.compute_fingerprint(tenant_id=tid)
    session = agent_config_store.close_session(session_id, tenant_id=tid, current_fingerprint=fp)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, "session": session}
