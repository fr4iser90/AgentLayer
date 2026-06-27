from __future__ import annotations

from fastapi import APIRouter

from apps.backend.api.providers.controllers.external_llm_api import router as external_llm_router
from apps.backend.api.providers.controllers.interfaces_api import router as interfaces_router
from apps.backend.api.providers.controllers.model_catalog_api import router as model_catalog_router
from apps.backend.api.providers.controllers.operator_settings_api import router as operator_settings_router
from apps.backend.api.providers.controllers.provider_endpoints_api import router as provider_endpoints_router

router = APIRouter()
for sub_router in (
    operator_settings_router,
    external_llm_router,
    model_catalog_router,
    provider_endpoints_router,
    interfaces_router,
):
    router.include_router(sub_router)
