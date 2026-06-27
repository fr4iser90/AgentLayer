from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from apps.backend.application.providers.use_cases.provider_admin_acl import (
    fetch_external_llm_models_payload,
    require_provider_admin,
    resolve_external_llm_credentials_for_catalog,
)
from apps.backend.api.providers.controllers.operator_common import *

router = APIRouter()
logger = logging.getLogger(__name__)
from apps.backend.api.providers.controllers.provider_endpoints_api import (
    admin_get_operator_provider_endpoints,
    admin_import_operator_env_providers,
    admin_put_operator_provider_endpoints,
)

@router.get("/v1/admin/external-llm/endpoints")
async def admin_get_external_llm_endpoints(request: Request):
    """Legacy path; chat providers are stored in operator_provider_endpoints."""
    await require_provider_admin(request)
    payload = await admin_get_operator_provider_endpoints(request, "chat")
    return {
        "endpoints": [
            {**row, "model_vlm": None, "model_agent": None, "model_coding": None}
            for row in payload.get("endpoints", [])
        ]
    }

@router.get("/v1/admin/external-llm/env-providers")
async def admin_get_external_llm_env_providers(request: Request):
    """Preview numbered LLM_PROVIDER_N_* env providers for explicit DB import."""
    await require_provider_admin(request)
    providers = _env_llm_provider_preview_rows()
    return {
        "providers": providers,
        "count": len(providers),
        "cleanup_note": "Remove imported LLM_PROVIDER_N_* keys from .env/deployment env and restart to avoid duplicate providers.",
    }


@router.post("/v1/admin/external-llm/env-providers/import")
async def admin_import_external_llm_env_providers(
    request: Request,
    body: EnvLlmProvidersImportBody = EnvLlmProvidersImportBody(),
):
    """Legacy path; import chat env providers into generic provider endpoints."""
    await require_provider_admin(request)
    return await admin_import_operator_env_providers(request, "chat", body)


@router.put("/v1/admin/external-llm/endpoints")
async def admin_put_external_llm_endpoints(request: Request, body: ExternalLlmEndpointsPutBody):
    """Legacy path; replace/sync chat endpoints in generic provider storage."""
    await require_provider_admin(request)
    generic = OperatorProviderEndpointsPutBody(
        endpoints=[
            OperatorProviderEndpointItem(
                id=e.id,
                sort_order=e.sort_order,
                enabled=e.enabled,
                label=e.label,
                base_url=e.base_url,
                api_key=e.api_key,
                api_header_name=e.api_header_name,
                model_default=e.model_default,
                max_parallel=e.max_parallel,
            )
            for e in body.endpoints
        ]
    )
    payload = await admin_put_operator_provider_endpoints(request, "chat", generic)
    return {
        "endpoints": [
            {**row, "model_vlm": None, "model_agent": None, "model_coding": None}
            for row in payload.get("endpoints", [])
        ]
    }
@router.post("/v1/admin/external-llm/models")
async def admin_external_llm_models(request: Request, body: ExternalLlmModelsBody = ExternalLlmModelsBody()):
    """
    List models from the configured external OpenAI-compatible API (``GET {base}/v1/models``).

    Uses non-empty ``base_url`` / ``api_key`` from the body when provided; otherwise the first
    enabled row in ``operator_external_llm_endpoints`` (or ``endpoint_id`` when set).
    """
    await require_provider_admin(request)
    try:
        bu, key = resolve_external_llm_credentials_for_catalog(
            body.base_url, body.api_key, endpoint_id=body.endpoint_id
        )
    except ValueError as e:
        tag = str(e)
        if tag == "missing_base_url":
            raise HTTPException(
                status_code=400,
                detail="Base URL fehlt (im Formular eintragen oder zuerst speichern).",
            ) from e
        if tag == "missing_api_key":
            raise HTTPException(
                status_code=400,
                detail="API-Key fehlt (einmalig eintragen oder zuerst speichern).",
            ) from e
        if tag == "unknown_endpoint":
            raise HTTPException(status_code=400, detail="Unbekannter endpoint_id.") from e
        if tag == "no_external_endpoint":
            raise HTTPException(
                status_code=400,
                detail="Kein externer LLM-Endpunkt konfiguriert (Admin → External LLM Endpoints).",
            ) from e
        raise
    return await fetch_external_llm_models_payload(bu, key)
