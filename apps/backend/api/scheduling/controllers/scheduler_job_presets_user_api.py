"""User HTTP API: list schedule presets (templates).

The only presets endpoint. A site-admin twin used to read the same directory
beside it, so a delegated ``schedule.manage`` holder could manage schedules while
the template picker behind them answered 403.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.scheduling.use_cases.schedule_presets import read_schedule_presets
from apps.backend.application.scheduling.use_cases.scheduling_controller_services import (
    schedule_feature_permission_error,
)

router = APIRouter(prefix="/v1/user/scheduler-job-presets", tags=["scheduler-job-presets-user"])


@router.get("")
async def list_scheduler_job_presets(request: Request) -> dict[str, Any]:
    """Templates for a new schedule, gated like the schedule list itself."""
    user = await get_current_user(request)
    feat_err = schedule_feature_permission_error(user_id=user.id, user_role=user.role)
    if feat_err:
        raise HTTPException(status_code=403, detail=feat_err)
    return {"ok": True, "presets": read_schedule_presets()}

