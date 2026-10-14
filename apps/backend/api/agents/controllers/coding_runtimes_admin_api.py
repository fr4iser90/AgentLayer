"""Admin API: install / update / enable external coding runtimes (Qwen, DeepSeek Harness)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.agent_runtime.use_cases.coding_runtime_admin_services import (
    CODING_RUNTIME_PACKAGES,
    OperatorSettingsPatch,
    apply_operator_settings_patch,
    coding_runtime_enabled_effective,
    dsh_runtime_enabled_effective,
    external_runtime_enabled_effective,
    install_coding_runtime_package,
    invalidate_operator_settings_cache,
    list_coding_runtime_package_status,
    list_npm_package_versions,
    preferred_coding_runtime_effective,
    qwen_runtime_enabled_effective,
    uninstall_coding_runtime_package,
    update_coding_runtime_package,
)
from apps.backend.application.identity.use_cases.request_auth import require_site_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/coding-runtimes", tags=["admin-coding-runtimes"])

_KNOWN = frozenset(CODING_RUNTIME_PACKAGES.keys())


class CodingRuntimeInstallBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="latest", max_length=64)


class CodingRuntimesPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled_ids: list[str] | None = None
    preferred_id: str | None = Field(default=None, max_length=64)


def _enrich_status_row(row: dict[str, Any]) -> dict[str, Any]:
    rid = str(row.get("id") or "")
    from apps.backend.domain.agent_runtime.external_runtime import get_external_runtime

    runtime = get_external_runtime(rid)
    available = False
    reason = "adapter not registered"
    if runtime is not None:
        try:
            available, reason = runtime.available()
        except Exception as exc:
            available, reason = False, f"availability check failed: {exc}"
    out = dict(row)
    out["enabled"] = coding_runtime_enabled_effective(rid)
    out["available"] = bool(available)
    out["reason"] = str(reason or "")
    out["supports_resume"] = bool(getattr(runtime, "supports_resume", False)) if runtime else False
    out["supports_write"] = bool(getattr(runtime, "supports_write", False)) if runtime else False
    return out


def _catalog_payload() -> dict[str, Any]:
    runtimes = [_enrich_status_row(r) for r in list_coding_runtime_package_status()]
    preferred = preferred_coding_runtime_effective()
    return {
        "external_runtime_enabled": external_runtime_enabled_effective(),
        "preferred_id": preferred,
        "qwen_enabled": qwen_runtime_enabled_effective(),
        "dsh_enabled": dsh_runtime_enabled_effective(),
        "runtimes": runtimes,
    }


@router.get("")
async def admin_list_coding_runtimes(request: Request) -> dict[str, Any]:
    await require_site_admin(request)
    return _catalog_payload()


@router.get("/{runtime_id}/versions")
async def admin_list_coding_runtime_versions(request: Request, runtime_id: str) -> dict[str, Any]:
    """npm registry versions + dist-tags for a select (no free-text pins)."""
    await require_site_admin(request)
    rid = (runtime_id or "").strip()
    if rid not in _KNOWN:
        raise HTTPException(status_code=404, detail=f"Unknown coding runtime {runtime_id!r}.")
    import asyncio

    return await asyncio.to_thread(list_npm_package_versions, rid)


@router.post("/{runtime_id}/install")
async def admin_install_coding_runtime(
    request: Request,
    runtime_id: str,
    body: CodingRuntimeInstallBody = CodingRuntimeInstallBody(),
) -> dict[str, Any]:
    await require_site_admin(request)
    rid = (runtime_id or "").strip()
    if rid not in _KNOWN:
        raise HTTPException(status_code=404, detail=f"Unknown coding runtime {runtime_id!r}.")
    result = await _run_install(rid, version=body.version or "latest")
    return {"ok": bool(result.get("ok")), **result, "catalog": _catalog_payload()}


@router.post("/{runtime_id}/update")
async def admin_update_coding_runtime(request: Request, runtime_id: str) -> dict[str, Any]:
    await require_site_admin(request)
    rid = (runtime_id or "").strip()
    if rid not in _KNOWN:
        raise HTTPException(status_code=404, detail=f"Unknown coding runtime {runtime_id!r}.")
    result = await _run_update(rid)
    return {"ok": bool(result.get("ok")), **result, "catalog": _catalog_payload()}


@router.post("/{runtime_id}/uninstall")
async def admin_uninstall_coding_runtime(request: Request, runtime_id: str) -> dict[str, Any]:
    await require_site_admin(request)
    rid = (runtime_id or "").strip()
    if rid not in _KNOWN:
        raise HTTPException(status_code=404, detail=f"Unknown coding runtime {runtime_id!r}.")
    result = await _run_uninstall(rid)
    return {"ok": bool(result.get("ok")), **result, "catalog": _catalog_payload()}


@router.patch("")
async def admin_patch_coding_runtimes(
    request: Request,
    body: CodingRuntimesPatchBody,
) -> dict[str, Any]:
    await require_site_admin(request)
    patch: dict[str, Any] = {}
    if body.enabled_ids is not None:
        enabled = {str(x).strip() for x in body.enabled_ids if str(x).strip()}
        unknown = enabled - _KNOWN
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown runtime id(s): {', '.join(sorted(unknown))}",
            )
        patch["qwen_runtime_enabled"] = "qwen_code" in enabled
        patch["dsh_runtime_enabled"] = "deepseek_harness" in enabled
        patch["external_runtime_enabled"] = bool(enabled)
    if "preferred_id" in body.model_fields_set:
        pref = (body.preferred_id or "").strip()
        if pref and pref not in _KNOWN:
            raise HTTPException(status_code=400, detail=f"Unknown preferred runtime {pref!r}.")
        # Empty string clears to internal.
        patch["preferred_coding_runtime"] = pref or ""
        if pref:
            # Enabling preferred implies that runtime is on and master switch on.
            patch["external_runtime_enabled"] = True
            if pref == "qwen_code":
                patch["qwen_runtime_enabled"] = True
            elif pref == "deepseek_harness":
                patch["dsh_runtime_enabled"] = True
    if not patch:
        return _catalog_payload()
    apply_operator_settings_patch(OperatorSettingsPatch(**patch))
    invalidate_operator_settings_cache()
    return _catalog_payload()


async def _run_install(runtime_id: str, *, version: str) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(
        install_coding_runtime_package,
        runtime_id,
        version=version,
    )


async def _run_update(runtime_id: str) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(update_coding_runtime_package, runtime_id)


async def _run_uninstall(runtime_id: str) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(uninstall_coding_runtime_package, runtime_id)
