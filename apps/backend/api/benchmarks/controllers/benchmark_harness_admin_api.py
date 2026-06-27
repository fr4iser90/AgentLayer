"""Admin API: benchmark harness matrix (global defaults + per-model overrides)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.benchmarks.use_cases.harness_admin import (
    delete_harness_override_for_admin,
    ensure_harness_override_for_admin,
    get_harness_matrix_for_admin,
    resolve_harness_for_admin,
    set_global_harness_for_admin,
    upsert_harness_override_for_admin,
    validate_harness_preset,
)

router = APIRouter(prefix="/v1/admin/benchmark-harness", tags=["benchmark-harness"])


class HarnessConfigFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    harness_preset: str = Field(default="observability", max_length=64)
    max_tool_rounds_override: int | None = Field(default=None, ge=1, le=512)
    scenario_timeout_sec: float | None = Field(default=None, ge=30, le=86400)
    capture_timeline: bool | None = None
    stream_llm: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)


class HarnessOverrideBody(HarnessConfigFields):
    model_config = ConfigDict(extra="forbid")

    catalog_owned_by: str = Field(..., min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=512)
    label: str | None = Field(default=None, max_length=128)


def _validate_preset(preset: str) -> str:
    try:
        return validate_harness_preset(preset)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="harness_preset must be observability or chat_parity",
        ) from exc


@router.get("")
async def get_harness_matrix(request: Request) -> dict[str, Any]:
    return await get_harness_matrix_for_admin(request)


@router.put("/global")
async def put_global_harness(request: Request, body: HarnessConfigFields) -> dict[str, Any]:
    try:
        global_cfg = await set_global_harness_for_admin(request, fields=body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "global": global_cfg}


@router.post("/overrides")
async def post_harness_override(request: Request, body: HarnessOverrideBody) -> dict[str, Any]:
    try:
        row = await upsert_harness_override_for_admin(request, fields=body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "override": row}


@router.patch("/overrides/{override_id}")
async def patch_harness_override(
    request: Request,
    override_id: uuid.UUID,
    body: HarnessOverrideBody,
) -> dict[str, Any]:
    try:
        await ensure_harness_override_for_admin(request, override_id)
        row = await upsert_harness_override_for_admin(request, fields=body, override_id=override_id)
    except (ValueError, LookupError) as exc:
        status = 404 if isinstance(exc, LookupError) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"ok": True, "override": row}


@router.delete("/overrides/{override_id}")
async def delete_harness_override(request: Request, override_id: uuid.UUID) -> dict[str, Any]:
    if not await delete_harness_override_for_admin(request, override_id):
        raise HTTPException(status_code=404, detail="harness override not found")
    return {"ok": True, "deleted": str(override_id)}


@router.get("/resolve")
async def resolve_harness_preview(
    request: Request,
    catalog_owned_by: str,
    model: str,
    use_matrix: bool = True,
    harness_preset: str | None = None,
    max_tool_rounds_override: int | None = None,
    scenario_timeout_sec: float | None = None,
) -> dict[str, Any]:
    eff = await resolve_harness_for_admin(
        request,
        catalog_owned_by=catalog_owned_by,
        model=model,
        harness_preset=harness_preset,
        max_tool_rounds_override=max_tool_rounds_override,
        scenario_timeout_sec=scenario_timeout_sec,
        use_matrix=use_matrix,
    )
    return {
        "catalog_owned_by": catalog_owned_by,
        "model": model,
        "effective": {
            "harness_preset": eff.harness_preset,
            "max_tool_rounds_override": eff.max_tool_rounds_override,
            "scenario_timeout_sec": eff.scenario_timeout_sec,
            "capture_timeline": eff.capture_timeline,
            "stream_llm": eff.stream_llm,
            "source": eff.source,
            "override_id": eff.override_id,
        },
    }
