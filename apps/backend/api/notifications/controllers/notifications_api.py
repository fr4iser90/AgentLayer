"""In-app notification inbox API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.agent_runtime.use_cases.notifications_controller_services import notification_prefs_store
from apps.backend.application.agent_runtime.use_cases.notifications_controller_services import notifications_store
from apps.backend.application.platform.use_cases.platform_controller_services import db

router = APIRouter(prefix="/v1/user/notifications", tags=["notifications"])


class NotificationPrefsBody(BaseModel):
    telegram_enabled: bool | None = None
    discord_enabled: bool | None = None
    telegram_schedules: bool | None = None
    telegram_dashboard: bool | None = None
    discord_schedules: bool | None = None
    discord_dashboard: bool | None = None
    external_failures_only: bool | None = None


class MarkDashboardSeenBody(BaseModel):
    dashboard_id: str = Field(min_length=1, max_length=64)
    block_ids: list[str] | None = Field(default=None, max_length=64)


@router.get("")
async def list_user_notifications(
    request: Request,
    limit: int = 50,
    unread_only: bool = False,
) -> dict:
    user = await get_current_user(request)
    items = notifications_store.list_notifications(
        user_id=user.id,
        limit=limit,
        unread_only=unread_only,
    )
    return {"ok": True, "notifications": items}


@router.get("/summary")
async def notification_summary(request: Request) -> dict:
    user = await get_current_user(request)
    return {
        "ok": True,
        "unread_count": notifications_store.unread_count(user_id=user.id),
        "dashboard_unread": notifications_store.unread_dashboard_summary(user_id=user.id),
    }


@router.patch("/{notification_id}/read")
async def mark_notification_read(request: Request, notification_id: uuid.UUID) -> dict:
    user = await get_current_user(request)
    ok = notifications_store.mark_read(user_id=user.id, notification_id=notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"ok": True}


@router.post("/read-all")
async def mark_all_notifications_read(request: Request) -> dict:
    user = await get_current_user(request)
    n = notifications_store.mark_all_read(user_id=user.id)
    return {"ok": True, "marked": n}


@router.post("/mark-dashboard-seen")
async def mark_dashboard_notifications_seen(
    request: Request,
    body: MarkDashboardSeenBody,
) -> dict:
    user = await get_current_user(request)
    n = notifications_store.mark_dashboard_seen(
        user_id=user.id,
        dashboard_id=body.dashboard_id,
        block_ids=body.block_ids,
    )
    return {"ok": True, "marked": n}


@router.get("/prefs")
async def get_notification_prefs(request: Request) -> dict:
    user = await get_current_user(request)
    prefs = notification_prefs_store.get_prefs(user_id=user.id)
    return {
        "ok": True,
        "prefs": prefs,
        "telegram_linked": bool(db.user_telegram_user_id_get(user.id)),
        "discord_linked": bool(db.user_discord_user_id_get(user.id)),
    }


@router.put("/prefs")
async def put_notification_prefs(request: Request, body: NotificationPrefsBody) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    patch = body.model_dump(exclude_unset=True)
    try:
        prefs = notification_prefs_store.upsert_prefs(
            tenant_id=tenant_id,
            user_id=user.id,
            patch=patch,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)[:200]) from e
    return {
        "ok": True,
        "prefs": prefs,
        "telegram_linked": bool(db.user_telegram_user_id_get(user.id)),
        "discord_linked": bool(db.user_discord_user_id_get(user.id)),
    }
