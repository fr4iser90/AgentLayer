from __future__ import annotations

from fastapi import APIRouter, Request

from apps.backend.application.providers.use_cases.provider_admin_acl import (
    InterfaceHintsPayload,
    apply_interface_hints,
    interface_hints_public,
    require_provider_admin,
)
from apps.backend.api.providers.controllers.operator_common import *

router = APIRouter()

@router.get("/v1/admin/interfaces")
async def get_interface_hints(request: Request):
    await require_provider_admin(request)
    return interface_hints_public()


@router.put("/v1/admin/interfaces")
async def put_interface_hints(request: Request, body: InterfaceHintsPayload):
    await require_provider_admin(request)
    apply_interface_hints(body)
    return interface_hints_public()
