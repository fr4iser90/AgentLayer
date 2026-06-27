from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request

from apps.backend.application.providers.use_cases.provider_admin_acl import (
    list_admin_llm_provider_rows,
    list_model_catalog_with_prefs,
    require_provider_admin,
    sync_model_catalog_prefs,
    tenant_exists,
    tenant_id_for_user,
    user_exists,
)
from apps.backend.api.providers.controllers.operator_common import *

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/v1/admin/model-catalog")
async def admin_get_model_catalog(request: Request):
    """Full model catalog plus admin visibility preferences."""
    await require_provider_admin(request)
    rows, agentlayer, prefs = await asyncio.to_thread(list_model_catalog_with_prefs)
    return {"object": "list", "data": rows, "agentlayer": agentlayer, "prefs": prefs}


@router.get("/v1/admin/llm-providers")
async def admin_get_llm_providers(request: Request):
    """Admin LLM provider catalog shared by LLM settings, chat defaults and benchmarks."""
    await require_provider_admin(request)

    return {"ok": True, "providers": await asyncio.to_thread(list_admin_llm_provider_rows)}


@router.put("/v1/admin/model-catalog/prefs")
async def admin_put_model_catalog_prefs(request: Request, body: ModelCatalogPrefsPutBody):
    """Upsert model catalog preferences such as chat visibility."""
    await require_provider_admin(request)
    raw = [p.model_dump() for p in body.prefs]
    try:
        await asyncio.to_thread(sync_model_catalog_prefs, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await admin_get_model_catalog(request)
@router.get("/v1/admin/model-access/global")
async def admin_get_global_model_access(request: Request):
    await require_provider_admin(request)
    return _model_access_payload_for_scope("global")


@router.put("/v1/admin/model-access/global")
async def admin_put_global_model_access(request: Request, body: ModelAccessPoliciesPutBody):
    await require_provider_admin(request)
    try:
        await asyncio.to_thread(_sync_model_access_payload, "global", body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _model_access_payload_for_scope("global")


@router.get("/v1/admin/model-access/tenants/{tenant_id}")
async def admin_get_tenant_model_access(request: Request, tenant_id: int):
    await require_provider_admin(request)
    if not tenant_exists(tenant_id):
        raise HTTPException(status_code=404, detail="tenant not found")
    return _model_access_payload_for_scope("tenant", tenant_id=tenant_id)


@router.put("/v1/admin/model-access/tenants/{tenant_id}")
async def admin_put_tenant_model_access(request: Request, tenant_id: int, body: ModelAccessPoliciesPutBody):
    await require_provider_admin(request)
    if not tenant_exists(tenant_id):
        raise HTTPException(status_code=404, detail="tenant not found")
    try:
        await asyncio.to_thread(_sync_model_access_payload, "tenant", body, tenant_id=tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _model_access_payload_for_scope("tenant", tenant_id=tenant_id)


@router.get("/v1/admin/model-access/users/{user_id}")
async def admin_get_user_model_access(request: Request, user_id: uuid.UUID):
    await require_provider_admin(request)
    if not user_exists(user_id):
        raise HTTPException(status_code=404, detail="user not found")
    return _model_access_payload_for_scope("user", tenant_id=tenant_id_for_user(user_id), user_id=user_id)


@router.put("/v1/admin/model-access/users/{user_id}")
async def admin_put_user_model_access(request: Request, user_id: uuid.UUID, body: ModelAccessPoliciesPutBody):
    await require_admin(request)
    if not user_exists(user_id):
        raise HTTPException(status_code=404, detail="user not found")
    tenant_id = tenant_id_for_user(user_id)
    try:
        await asyncio.to_thread(_sync_model_access_payload, "user", body, tenant_id=tenant_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _model_access_payload_for_scope("user", tenant_id=tenant_id, user_id=user_id)
