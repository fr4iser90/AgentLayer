from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from apps.backend.application.providers.use_cases.provider_admin_acl import (
    chat_provider_model_rows,
    embedding_provider_model_rows,
    http_get_json,
    list_operator_provider_endpoints,
    provider_auth_headers,
    provider_configured_model_rows,
    provider_models_url,
    provider_spec_for_kind,
    require_provider_admin,
    sync_operator_provider_endpoints,
)
from apps.backend.api.providers.controllers.operator_common import *

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/v1/admin/provider-endpoints")
async def admin_get_operator_provider_endpoint_kinds(request: Request):
    """List backend-owned non-LLM provider endpoint kinds for Admin UI discovery."""
    await require_provider_admin(request)
    return {
        "kinds": list(_operator_provider_endpoint_metadata()),
        "model_default_profiles": list(_model_default_profile_metadata()),
    }


@router.get("/v1/admin/provider-endpoints/{kind}")
async def admin_get_operator_provider_endpoints(request: Request, kind: str):
    """List non-LLM provider endpoints (keys redacted), using LLM-style endpoint rows."""
    await require_provider_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    out: list[dict[str, Any]] = []
    for r in list_operator_provider_endpoints(kind_v):
        provider_id = _operator_endpoint_provider_id(kind_v, int(r["id"]))
        model_payload = await _operator_provider_models_payload(kind_v, provider_id)
        k = str(r.get("api_key") or "")
        out.append(
            {
                "id": r["id"],
                "kind": r["kind"],
                "provider_id": provider_id,
                "source": "db",
                "sort_order": r["sort_order"],
                "enabled": r["enabled"],
                "label": r.get("label") or "",
                "base_url": r.get("base_url") or "",
                "api_key_configured": bool(k.strip()),
                "api_key_last4": (k[-4:] if len(k) >= 4 else None),
                "api_header_name": (str(r.get("api_header_name") or "").strip() or "Authorization"),
                "model_default": r.get("model_default"),
                "max_parallel": int(r.get("max_parallel") or 1),
                "options_json": r.get("options_json") if isinstance(r.get("options_json"), dict) else {},
                "models": [str(row.get("id") or "").strip() for row in model_payload.get("data", []) if str(row.get("id") or "").strip()],
                "models_detail": model_payload.get("detail"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
        )
    return {"endpoints": out}
@router.get("/v1/admin/provider-endpoints/{kind}/env-providers")
async def admin_get_operator_env_providers(request: Request, kind: str):
    """Preview non-LLM numbered env providers for explicit DB import."""
    await require_provider_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    providers = _operator_env_provider_preview_rows(kind_v)
    return {
        "providers": providers,
        "count": len(providers),
        "cleanup_note": f"Remove imported {_operator_env_prefix(kind_v, 1).rsplit('_', 1)[0]}_N_* keys from .env/deployment env and restart to avoid duplicate providers.",
    }


def _provider_models_url(base_url: str) -> str:
    base = _operator_provider_base_url(base_url)
    low = base.lower()
    if low.endswith("/models"):
        return base
    if low.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _provider_auth_headers(api_key: str, api_header_name: str) -> dict[str, str]:
    key = (api_key or "").strip()
    if not key:
        return {}
    header = (api_header_name or "Authorization").strip() or "Authorization"
    if header.lower() == "authorization":
        return {"Authorization": key if key.lower().startswith("bearer ") else f"Bearer {key}"}
    return {header: key}


def _provider_configured_model_rows(spec: Any) -> list[dict[str, str]]:
    ids: list[str] = []
    for attr in ("model_default", "model", "model_stt", "model_tts"):
        value = str(getattr(spec, attr, "") or "").strip()
        if value and value not in ids:
            ids.append(value)
    return [{"id": model_id} for model_id in ids]


@router.get("/v1/admin/provider-endpoints/{kind}/models")
async def admin_operator_provider_models(request: Request, kind: str, provider_id: str | None = None):
    """List model ids for one non-LLM provider. Used by Admin dropdowns."""
    await require_provider_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    return await _operator_provider_models_payload(kind_v, provider_id)


async def _operator_provider_models_payload(kind_v: str, provider_id: str | None = None) -> dict[str, Any]:
    if kind_v == "chat":
        data = await asyncio.to_thread(chat_provider_model_rows, provider_id)
        return {"data": data}
    if kind_v == "embedding":
        data, detail = await asyncio.to_thread(embedding_provider_model_rows, provider_id)
        return {"data": data, "detail": detail}

    spec: Any = await asyncio.to_thread(provider_spec_for_kind, kind_v, provider_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Provider not found.")
    fallback_rows = provider_configured_model_rows(spec)
    url = provider_models_url(str(spec.base_url), _operator_provider_base_url)
    try:
        status, text, data = await asyncio.to_thread(
            http_get_json,
            url,
            headers=provider_auth_headers(str(spec.api_key or ""), str(spec.api_header_name or "Authorization")),
            timeout=12.0,
        )
    except Exception as e:
        return {"data": fallback_rows, "detail": f"Provider model list unavailable: {e}"}
    if status != 200 or not isinstance(data, dict):
        return {
            "data": fallback_rows,
            "detail": (text or "").strip() or f"Provider model list unavailable: HTTP {status}",
        }
    rows = []
    for item in data.get("data") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            rows.append({"id": item["id"].strip()})
    return {"data": rows}


@router.post("/v1/admin/provider-endpoints/{kind}/env-providers/import")
async def admin_import_operator_env_providers(
    request: Request,
    kind: str,
    body: EnvLlmProvidersImportBody = EnvLlmProvidersImportBody(),
):
    """Import selected non-LLM env providers into DB endpoints without modifying .env."""
    await require_provider_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    selected = {int(i) for i in body.provider_indexes or [] if int(i) >= 1}
    env_rows = [
        row
        for row in _operator_env_rows_for_kind(kind_v)
        if not selected or int(getattr(row, "index")) in selected
    ]
    existing = list_operator_provider_endpoints(kind_v)
    combined: list[dict[str, Any]] = []
    base_to_pos: dict[str, int] = {}
    for row in existing:
        clone = dict(row)
        combined.append(clone)
        key = _operator_provider_dedupe_key(row.get("base_url"))
        if key:
            base_to_pos.setdefault(key, len(combined) - 1)

    imported: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    for env_row in env_rows:
        base = _operator_provider_base_url(env_row.base_url)
        payload = {
            "sort_order": len(combined),
            "enabled": True,
            "label": getattr(env_row, "label"),
            "base_url": base,
            "api_key": getattr(env_row, "api_key", ""),
            "api_header_name": getattr(env_row, "api_header_name", None) or "Authorization",
            "model_default": _operator_env_model(kind_v, env_row),
            "max_parallel": int(getattr(env_row, "max_parallel", 1) or 1),
            "options_json": _operator_env_options(kind_v, env_row),
        }
        key = _operator_provider_dedupe_key(base)
        pos = base_to_pos.get(key)
        if pos is None:
            combined.append(payload)
            base_to_pos[key] = len(combined) - 1
            imported.append(
                {"index": getattr(env_row, "index"), "provider_id": getattr(env_row, "provider_id"), "base_url": base}
            )
        else:
            prev = combined[pos]
            combined[pos] = {**prev, **payload, "id": prev.get("id"), "sort_order": prev.get("sort_order", pos)}
            updated.append(
                {
                    "index": getattr(env_row, "index"),
                    "provider_id": getattr(env_row, "provider_id"),
                    "base_url": base,
                    "db_endpoint_id": _operator_provider_endpoint_public_id(prev),
                }
            )

    try:
        sync_operator_provider_endpoints(kind_v, combined)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _invalidate_non_llm_provider_caches(kind_v)
    return {
        "ok": True,
        "imported": imported,
        "updated": updated,
        "cleanup_keys": [
            key
            for row in env_rows
            for key in _operator_env_cleanup_keys(kind_v, int(getattr(row, "index")))
        ],
        "cleanup_note": f"Remove imported {_operator_env_prefix(kind_v, 1).rsplit('_', 1)[0]}_N_* keys from .env/deployment env and restart to avoid duplicate providers.",
        "endpoints": (await admin_get_operator_provider_endpoints(request, kind_v))["endpoints"],
        "env_providers": _operator_env_provider_preview_rows(kind_v),
    }


@router.put("/v1/admin/provider-endpoints/{kind}")
async def admin_put_operator_provider_endpoints(
    request: Request,
    kind: str,
    body: OperatorProviderEndpointsPutBody,
):
    """Replace/sync non-LLM provider endpoints for one kind."""
    await require_provider_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    raw = [e.model_dump() for e in body.endpoints]
    try:
        sync_operator_provider_endpoints(
            kind_v,
            raw,
            delete_missing=False,
            delete_ids=body.delete_endpoint_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _invalidate_non_llm_provider_caches(kind_v)
    return await admin_get_operator_provider_endpoints(request, kind_v)
