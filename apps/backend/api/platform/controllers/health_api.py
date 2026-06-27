from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.application.identity.use_cases.request_auth import (
    LoginRequest,
    create_access_token,
    create_refresh_token,
    create_user,
    get_current_user,
    get_user_by_email,
    get_user_by_id,
    get_user_for_bearer_token,
    list_all_users,
    require_admin,
    revoke_refresh_token,
    update_user_tenant,
    validate_refresh_token,
    verify_password,
)
from apps.backend.domain.shared.identity import reset_identity, set_identity
from apps.backend.domain.shared.http_identity import resolve_chat_identity
from apps.backend.application.platform.use_cases.platform_controller_services import http_500_detail
router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health")
def health():
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.commit()
    except Exception:
        logger.exception("database health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "down"},
        )
    return {"status": "ok", "database": "ok"}


def merge_model_catalog_rows(
    env_provider_rows: list[dict[str, Any]],
    llama_cpp_rows: list[dict[str, Any]],
    *more: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Re-export: dedupe by ``(owned_by, id)``; same id on different providers stays separate."""
    from apps.backend.application.platform.use_cases.platform_controller_services import merge_model_catalog_rows as _merge

    return _merge(env_provider_rows, llama_cpp_rows, *more)


@router.get("/v1/models")
async def models_proxy(request: Request):
    """
    OpenAI-style model list: all catalog providers (``provider_1``, ``provider_2``, external endpoints, …).

    One provider failing does not remove rows from others. ``agentlayer`` keys match row ``owned_by``.
    """
    user = await get_current_user(request)
    from apps.backend.application.platform.use_cases.platform_controller_services import fetch_full_model_catalog

    merged, agentlayer = await asyncio.to_thread(
        fetch_full_model_catalog,
        tenant_id=db.user_tenant_id(user.id),
        user_id=user.id,
    )
    return {"object": "list", "data": merged, "agentlayer": agentlayer}
