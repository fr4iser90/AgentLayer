"""HTTP API for per-user encrypted secrets (not for LLM chat — use curl / UI integration)."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from apps.backend.application.platform.use_cases.platform_controller_services import config
from apps.backend.domain.shared.http_identity import resolve_chat_identity
from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.application.platform.use_cases.platform_controller_services import (
    enforce_otp_register_rate_limit,
    require_https_or_loopback_for_otp_register,
)

router = APIRouter(prefix="/v1/user/secrets", tags=["user-secrets"])

_SERVICE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")


def _require_user_secrets_enabled() -> None:
    if not config.SECRETS_MASTER_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "AGENT_SECRETS_MASTER_KEY must be set on the server (operator only; "
                "encrypts stored secrets — end users never see or paste this)"
            ),
        )


def _norm_service_key(raw: str) -> str:
    k = (raw or "").strip().lower()
    if not _SERVICE_KEY_RE.fullmatch(k):
        raise HTTPException(
            status_code=400,
            detail="invalid service_key: use lowercase [a-z0-9._-], max 63 chars",
        )
    return k


class UserSecretBody(BaseModel):
    service_key: str = Field(..., min_length=1, max_length=64)
    secret: str = Field(..., min_length=1, max_length=65536)
    scope: str | None = Field(
        default=None,
        description="global (default) or workspace — workspace requires workspace_id",
    )
    workspace_id: str | None = Field(default=None, max_length=64)

    @field_validator("secret", mode="before")
    @classmethod
    def _coerce_secret_body(cls, v: Any) -> str:
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError("secret is empty")
            return s
        raise ValueError("secret must be a string or a JSON object")


class RegisterWithOtpBody(BaseModel):
    otp: str = Field(..., min_length=8, max_length=256)
    service_key: str = Field(..., min_length=1, max_length=64)
    secret: str = Field(..., min_length=1, max_length=65536)

    @field_validator("secret", mode="before")
    @classmethod
    def _coerce_secret(cls, v: Any) -> str:
        """Allow JSON object in request body (curl-friendly); store as canonical string."""
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError("secret is empty")
            return s
        raise ValueError(
            "secret must be a string or a JSON object, e.g. "
            '{"email":"you@gmail.com","app_password":"xxxx"} for gmail'
        )


@router.post("/register-with-otp")
def register_secret_with_otp(request: Request, body: RegisterWithOtpBody):
    """
    Store a secret using a one-time code from the ``register_secrets`` tool (chat).
    Body ``secret`` may be a **string** (JSON text) or a **JSON object** (e.g. gmail credentials).
    No Bearer token or user headers — the OTP binds to the chat user who minted it.
    """
    enforce_otp_register_rate_limit(request)
    require_https_or_loopback_for_otp_register(request)
    _require_user_secrets_enabled()
    sk = _norm_service_key(body.service_key)
    try:
        db.user_secret_register_with_otp(body.otp, sk, body.secret)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "service_key": sk, "stored": True}


@router.get("")
def list_user_secrets(request: Request, workspace_id: str | None = None):
    """List configured service keys for this user (no secret values)."""
    import uuid as _uuid

    _require_user_secrets_enabled()
    uid, _tid = resolve_chat_identity(request)
    global_keys = db.user_secret_list_service_keys(uid)
    workspace_keys: list[str] = []
    wid_out: str | None = None
    if workspace_id and str(workspace_id).strip():
        try:
            wid = _uuid.UUID(str(workspace_id).strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail="invalid workspace_id") from e
        workspace_keys = db.user_workspace_secret_list_service_keys(uid, wid)
        wid_out = str(wid)
    return {
        "ok": True,
        "services": sorted(set(global_keys) | set(workspace_keys)),
        "services_global": global_keys,
        "services_workspace": workspace_keys,
        "workspace_id": wid_out,
    }


@router.post("")
def upsert_user_secret(request: Request, body: UserSecretBody):
    """Store or replace an encrypted secret for this user (global or workspace)."""
    import uuid as _uuid

    _require_user_secrets_enabled()
    uid, _tid = resolve_chat_identity(request)
    sk = _norm_service_key(body.service_key)
    scope = (body.scope or "global").strip().lower()
    if scope in ("user",):
        scope = "global"
    if scope not in ("global", "workspace"):
        raise HTTPException(status_code=400, detail="scope must be global or workspace")
    try:
        if scope == "workspace":
            if not body.workspace_id or not str(body.workspace_id).strip():
                raise HTTPException(
                    status_code=400,
                    detail="workspace_id is required when scope=workspace",
                )
            wid = _uuid.UUID(str(body.workspace_id).strip())
            db.user_workspace_secret_upsert(uid, wid, sk, body.secret)
            from plugins.tools.workspace.lib.env_secret_bridge import (
                ensure_env_binding_for_secret,
            )

            bind_info = ensure_env_binding_for_secret(
                user_id=uid,
                workspace_id=wid,
                service_key=sk,
            )
            return {
                "ok": True,
                "service_key": sk,
                "stored": True,
                "scope": "workspace",
                "workspace_id": str(wid),
                "env_binding": bind_info,
            }
        db.user_secret_upsert(uid, sk, body.secret)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "service_key": sk, "stored": True, "scope": "global"}


@router.delete("/{service_key}")
def delete_user_secret(
    service_key: str,
    request: Request,
    workspace_id: str | None = None,
):
    """Remove a stored secret (global, or workspace when workspace_id is set)."""
    import uuid as _uuid

    _require_user_secrets_enabled()
    uid, _tid = resolve_chat_identity(request)
    sk = _norm_service_key(service_key)
    if workspace_id and str(workspace_id).strip():
        try:
            wid = _uuid.UUID(str(workspace_id).strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail="invalid workspace_id") from e
        if not db.user_workspace_secret_delete(uid, wid, sk):
            raise HTTPException(status_code=404, detail="no such workspace secret")
        return {"ok": True, "deleted": sk, "scope": "workspace", "workspace_id": str(wid)}
    if not db.user_secret_delete(uid, sk):
        raise HTTPException(status_code=404, detail="no such secret for this user")
    return {"ok": True, "deleted": sk, "scope": "global"}
