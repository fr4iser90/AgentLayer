from __future__ import annotations

from fastapi import APIRouter, Request

from apps.backend.application.providers.use_cases.provider_admin_acl import (
    OperatorSettingsPatch,
    OperatorSettingsPayload,
    apply_operator_settings_patch,
    apply_operator_settings_update,
    operator_settings_public,
    require_provider_admin,
)
from apps.backend.api.providers.controllers.operator_common import *

router = APIRouter()

@router.get("/v1/admin/operator-settings")
async def get_operator_settings(request: Request):
    await require_provider_admin(request)
    return operator_settings_public()


@router.put("/v1/admin/operator-settings")
async def put_operator_settings(request: Request, body: OperatorSettingsPayload):
    await require_provider_admin(request)
    apply_operator_settings_update(body)
    return operator_settings_public()


@router.patch("/v1/admin/operator-settings")
async def patch_operator_settings(request: Request, body: OperatorSettingsPatch):
    await require_provider_admin(request)
    apply_operator_settings_patch(body)
    return operator_settings_public()
