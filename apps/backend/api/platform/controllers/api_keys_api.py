"""HTTP API for per-user API keys — long-lived bearer credentials for headless clients (TUI, CLI, scripts).

A key authenticates the same calls as a JWT, on HTTP (``Authorization: Bearer``) and on
``/ws/v1/chat`` (header or ``?token=``). See ADR 0008.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import (
    bearer_is_interactive_session,
    create_api_key,
    get_current_user,
    list_api_keys,
    revoke_api_key,
)

router = APIRouter(prefix="/v1/user/api-keys", tags=["user-api-keys"])

_MAX_KEYS_PER_USER = 20
_MAX_TTL_DAYS = 365


def _require_interactive_session(request: Request) -> None:
    """Manage keys from a logged-in session only, so a leaked key cannot mint a successor."""
    auth = request.headers.get("authorization") or ""
    token = auth.removeprefix("Bearer ").strip()
    if not bearer_is_interactive_session(token):
        raise HTTPException(
            status_code=403,
            detail="API keys must be managed from a logged-in session, not with an API key",
        )


class ApiKeyCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    expires_in_days: int | None = Field(default=None, ge=1, le=_MAX_TTL_DAYS)


@router.get("")
async def api_key_list(request: Request) -> dict[str, Any]:
    """Metadata for the caller's keys. Secrets are hashed at rest and never returned."""
    user = await get_current_user(request)
    return {"ok": True, "api_keys": list_api_keys(user.id)}


@router.post("")
async def api_key_create(request: Request, body: ApiKeyCreateBody) -> dict[str, Any]:
    """Mint a key. The secret is shown exactly once — it cannot be recovered later."""
    user = await get_current_user(request)
    _require_interactive_session(request)
    from apps.backend.application.platform.use_cases.client_surface_policy import refuse_api_key_mint

    mint_refuse = refuse_api_key_mint()
    if mint_refuse:
        raise HTTPException(status_code=403, detail=mint_refuse)
    if len(list_api_keys(user.id)) >= _MAX_KEYS_PER_USER:
        raise HTTPException(
            status_code=409,
            detail=f"key limit reached ({_MAX_KEYS_PER_USER}) — revoke one first",
        )
    expires_at = (
        datetime.now(UTC) + timedelta(days=int(body.expires_in_days))
        if body.expires_in_days
        else None
    )
    token, meta = create_api_key(user.id, body.name.strip(), expires_at)
    return {
        "ok": True,
        "api_key": token,
        "note": "Store this now — it is not retrievable later.",
        "key": meta,
    }


@router.delete("/{key_id}")
async def api_key_revoke(request: Request, key_id: str) -> dict[str, Any]:
    """Revoke immediately; the next request with that key fails to authenticate."""
    user = await get_current_user(request)
    _require_interactive_session(request)
    try:
        kid = uuid.UUID(key_id.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="invalid key_id") from e
    if not revoke_api_key(user.id, kid):
        raise HTTPException(status_code=404, detail="key not found")
    return {"ok": True, "revoked": True, "key_id": str(kid)}
