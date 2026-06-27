"""HTTP API for generic dashboards (``/v1/dashboards``)."""
from __future__ import annotations

from fastapi import APIRouter

from apps.backend.api.dashboards.controllers.dashboard_core_api import router as core_router
from apps.backend.api.dashboards.controllers.dashboard_files_api import router as files_router
from apps.backend.api.dashboards.controllers.dashboard_install_api import router as install_router
from apps.backend.api.dashboards.controllers.dashboard_members_api import router as members_router

router = APIRouter(tags=["dashboards"])
router.include_router(install_router, prefix="/v1/dashboards")
router.include_router(files_router, prefix="/v1/dashboards")
router.include_router(members_router, prefix="/v1/dashboards")
router.include_router(core_router, prefix="/v1/dashboards")
