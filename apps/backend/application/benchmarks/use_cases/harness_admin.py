from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request

from apps.backend.infrastructure.benchmarks import benchmark_harness_resolve, benchmark_harness_store
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.identity.auth import require_admin


def validate_harness_preset(preset: str) -> str:
    value = str(preset or "observability").strip().lower()
    if value not in ("observability", "chat_parity"):
        raise ValueError("harness_preset must be observability or chat_parity")
    return value


async def harness_admin_tenant_id(request: Request) -> int:
    admin = await require_admin(request)
    return db.user_tenant_id(admin.id)


async def get_harness_matrix_for_admin(request: Request) -> dict[str, Any]:
    tid = await harness_admin_tenant_id(request)
    return {
        "global": benchmark_harness_store.get_global(tid),
        "overrides": benchmark_harness_store.list_overrides(tid),
    }


async def set_global_harness_for_admin(request: Request, *, fields: Any) -> dict[str, Any]:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    return benchmark_harness_store.set_global(
        tid,
        harness_preset=validate_harness_preset(fields.harness_preset),
        max_tool_rounds_override=fields.max_tool_rounds_override,
        scenario_timeout_sec=fields.scenario_timeout_sec,
        capture_timeline=fields.capture_timeline,
        stream_llm=fields.stream_llm,
        notes=fields.notes,
        user_id=admin.id,
    )


async def upsert_harness_override_for_admin(
    request: Request,
    *,
    fields: Any,
    override_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    return benchmark_harness_store.upsert_override(
        tid,
        catalog_owned_by=fields.catalog_owned_by.strip(),
        model=fields.model.strip() if fields.model else None,
        label=fields.label,
        harness_preset=validate_harness_preset(fields.harness_preset),
        max_tool_rounds_override=fields.max_tool_rounds_override,
        scenario_timeout_sec=fields.scenario_timeout_sec,
        capture_timeline=fields.capture_timeline,
        stream_llm=fields.stream_llm,
        notes=fields.notes,
        user_id=admin.id,
        override_id=override_id,
    )


async def ensure_harness_override_for_admin(request: Request, override_id: uuid.UUID) -> int:
    tid = await harness_admin_tenant_id(request)
    if not benchmark_harness_store.get_override(override_id, tenant_id=tid):
        raise LookupError("harness override not found")
    return tid


async def delete_harness_override_for_admin(request: Request, override_id: uuid.UUID) -> bool:
    tid = await harness_admin_tenant_id(request)
    return benchmark_harness_store.delete_override(override_id, tenant_id=tid)


async def resolve_harness_for_admin(
    request: Request,
    *,
    catalog_owned_by: str,
    model: str,
    use_matrix: bool,
    harness_preset: str | None,
    max_tool_rounds_override: int | None,
    scenario_timeout_sec: float | None,
) -> Any:
    tid = await harness_admin_tenant_id(request)
    return benchmark_harness_resolve.resolve_for_profile(
        tenant_id=tid,
        catalog_owned_by=catalog_owned_by,
        model=model,
        run_harness_preset=harness_preset,
        run_max_tool_rounds_override=max_tool_rounds_override,
        run_scenario_timeout_sec=scenario_timeout_sec,
        use_matrix=use_matrix,
    )
