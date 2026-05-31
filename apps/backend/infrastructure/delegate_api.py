"""User Delegate (Stellvertreter) — global decision authority config."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.domain.delegate_config_schema import default_delegate_config, normalize_delegate_notes
from apps.backend.domain.http_identity import resolve_chat_identity
from apps.backend.infrastructure import user_delegate_store
from apps.backend.infrastructure import delegate_runs_store

router = APIRouter(prefix="/v1/user", tags=["user-delegate"])


def _row_to_response(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "ok": True,
            "config": default_delegate_config(),
            "notes": "",
            "updated_at": None,
        }
    return {
        "ok": True,
        "config": row.get("config") or default_delegate_config(),
        "notes": row.get("notes") or "",
        "updated_at": row.get("updated_at"),
    }


@router.get("/delegate")
def get_user_delegate(request: Request) -> dict[str, Any]:
    uid, _tid = resolve_chat_identity(request)
    try:
        row = user_delegate_store.get_user_delegate(user_id=uid)
    except Exception as e:
        return {
            "ok": True,
            "config": default_delegate_config(),
            "notes": "",
            "updated_at": None,
            "delegate_storage": "unavailable",
            "detail": str(e)[:200],
        }
    return _row_to_response(row)


class UserDelegateUpdateBody(BaseModel):
    config: dict[str, Any] = Field(default_factory=default_delegate_config)
    notes: str = Field(default="", max_length=2000)


@router.put("/delegate")
def put_user_delegate(request: Request, body: UserDelegateUpdateBody) -> dict[str, Any]:
    uid, tid = resolve_chat_identity(request)
    try:
        notes = normalize_delegate_notes(body.notes)
        row = user_delegate_store.upsert_user_delegate(
            tenant_id=int(tid),
            user_id=uid,
            config=body.config,
            notes=notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "delegate storage unavailable (run DB migrations: user_delegate missing?) — "
                f"{e}"
            ),
        ) from e
    return {"ok": True, "stored": True, **_row_to_response(row)}


@router.get("/delegate/runs")
def list_delegate_runs(request: Request, limit: int = 50) -> dict:
    uid, _tid = resolve_chat_identity(request)
    try:
        runs = delegate_runs_store.list_delegate_runs(user_id=uid, limit=limit)
    except Exception as e:
        return {"ok": True, "runs": [], "delegate_storage": "unavailable", "detail": str(e)[:200]}
    return {"ok": True, "runs": runs}
