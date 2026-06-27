"""
User persona (agent personalization) and KB note sharing.

Secrets remain on ``/v1/user/secrets`` (encrypted); do not put credentials in persona text.
"""

from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from psycopg.errors import UniqueViolation

from apps.backend.domain.shared.http_identity import resolve_chat_identity
from apps.backend.application.platform.use_cases.platform_controller_services import db

router = APIRouter(prefix="/v1/user", tags=["user-data"])


@router.get("/persona")
def get_user_persona(request: Request) -> dict:
    """Return saved persona or empty defaults."""
    uid, _tid = resolve_chat_identity(request)
    try:
        row = db.user_persona_get(uid)
    except Exception:
        return {
            "ok": True,
            "instructions": "",
            "inject_into_agent": False,
            "updated_at": None,
            "persona_storage": "unavailable",
        }
    if not row:
        return {
            "ok": True,
            "instructions": "",
            "inject_into_agent": False,
            "updated_at": None,
        }
    return {"ok": True, **row}


class PersonaUpdateBody(BaseModel):
    instructions: str = Field(default="", max_length=100_000)
    inject_into_agent: bool = False


@router.put("/persona")
def put_user_persona(request: Request, body: PersonaUpdateBody) -> dict:
    """
    Replace persona text. When ``inject_into_agent`` is true, instructions are
    merged into the system message for chat (same user identity only).
    """
    uid, tid = resolve_chat_identity(request)
    try:
        db.user_persona_upsert(
            tid,
            uid,
            instructions=body.instructions,
            inject_into_agent=body.inject_into_agent,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "persona storage unavailable (run DB migrations: "
                f"user_agent_persona missing?) — {e}"
            ),
        ) from e
    return {"ok": True, "stored": True}


class AgentProfilePatch(BaseModel):
    """
    Partial update: only sent fields are applied. Omitted fields keep DB values.
    Suggested enums (not enforced): tone casual|formal|neutral; verbosity short|medium|detailed;
    language_level simple|technical|expert; travel_mode public_transit|car|bike|walk|mixed;
    experience_level beginner|intermediate|advanced|expert;
    interaction_style assistant|coach|operator|companion.
    interests/hobbies: list of strings or {name, weight} objects. injection_preferences: include_* booleans.
    """

    display_name: str | None = Field(default=None, max_length=10_000)
    preferred_output_language: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=128)
    home_location: str | None = Field(default=None, max_length=10_000)
    work_location: str | None = Field(default=None, max_length=10_000)
    travel_mode: str | None = Field(default=None, max_length=128)
    travel_preferences: dict[str, Any] | None = None
    tone: str | None = Field(default=None, max_length=64)
    verbosity: str | None = Field(default=None, max_length=64)
    language_level: str | None = Field(default=None, max_length=64)
    interests: list[Any] | None = None
    hobbies: list[Any] | None = None
    job_title: str | None = Field(default=None, max_length=512)
    organization: str | None = Field(default=None, max_length=512)
    industry: str | None = Field(default=None, max_length=512)
    experience_level: str | None = Field(default=None, max_length=64)
    primary_tools: list[Any] | None = None
    proactive_mode: bool | None = None
    interaction_style: str | None = Field(default=None, max_length=64)
    inject_structured_profile: bool | None = None
    inject_dynamic_traits: bool | None = None
    dynamic_traits: dict[str, Any] | None = None
    injection_preferences: dict[str, Any] | None = None
    usage_patterns: dict[str, Any] | None = None


_NEST_MERGE_KEYS = frozenset(
    {
        "injection_preferences",
        "usage_patterns",
        "dynamic_traits",
        "travel_preferences",
    }
)


@router.get("/profile")
def get_user_profile(request: Request) -> dict:
    """Structured agent profile (GET merges defaults if no row)."""
    uid, _tid = resolve_chat_identity(request)
    try:
        row = db.user_agent_profile_get(uid)
    except Exception:
        out = copy.deepcopy(db.DEFAULT_AGENT_PROFILE)
        out["ok"] = True
        out["updated_at"] = None
        out["profile_storage"] = "unavailable"
        return out
    if not row:
        out = copy.deepcopy(db.DEFAULT_AGENT_PROFILE)
        out["ok"] = True
        out["updated_at"] = None
        return out
    return {"ok": True, **row}


@router.put("/profile")
def put_user_profile(request: Request, body: AgentProfilePatch) -> dict:
    """Patch structured profile fields."""
    uid, tid = resolve_chat_identity(request)
    patch = body.model_dump(exclude_unset=True)
    try:
        current = db.user_agent_profile_get(uid)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"profile storage unavailable (migrations?) — {e}",
        ) from e
    base: dict[str, Any] = copy.deepcopy(db.DEFAULT_AGENT_PROFILE)
    if current:
        for k, v in current.items():
            if k != "updated_at":
                base[k] = v
    for nk in _NEST_MERGE_KEYS:
        if nk in patch and isinstance(patch[nk], dict):
            cur = dict(base.get(nk) or {})
            cur.update(patch[nk])
            base[nk] = cur
            del patch[nk]
    base.update(patch)
    base.pop("updated_at", None)
    try:
        db.user_agent_profile_upsert(tid, uid, base)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "stored": True}


class KbShareCreateBody(BaseModel):
    grantee_email: str | None = None
    grantee_external_sub: str | None = None

    @model_validator(mode="after")
    def one_grantee(self) -> KbShareCreateBody:
        if not (self.grantee_email or "").strip() and not (
            self.grantee_external_sub or ""
        ).strip():
            raise ValueError("grantee_email or grantee_external_sub is required")
        return self


@router.post("/kb/notes/{note_id}/shares")
def create_kb_note_share(
    note_id: int, request: Request, body: KbShareCreateBody
) -> dict:
    """Owner only: grant read access to another user in the same tenant."""
    uid, tid = resolve_chat_identity(request)
    ge = (body.grantee_email or "").strip() or None
    gs = (body.grantee_external_sub or "").strip() or None
    grantee = db.user_resolve_in_tenant(tid, email=ge, external_sub=gs)
    if grantee is None:
        raise HTTPException(
            status_code=404, detail="grantee not found in this tenant"
        )
    try:
        sid = db.kb_note_share_create(note_id, uid, tid, grantee)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"sharing unavailable (migrations applied?) — {e}",
        ) from e
    return {"ok": True, "share_id": sid}


@router.get("/kb/notes/{note_id}/shares")
def list_kb_note_shares(note_id: int, request: Request) -> dict:
    """Owner only: list grants for this note."""
    uid, tid = resolve_chat_identity(request)
    if not db.kb_note_is_owner(note_id, uid, tid):
        raise HTTPException(
            status_code=404, detail="note not found or you are not the owner"
        )
    try:
        rows = db.kb_note_share_list(note_id, uid, tid)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "shares": rows}


@router.delete("/kb/shares/{share_id}")
def delete_kb_note_share(share_id: int, request: Request) -> dict:
    """Owner only: revoke a grant."""
    uid, tid = resolve_chat_identity(request)
    ok = db.kb_note_share_delete(share_id, uid, tid)
    if not ok:
        raise HTTPException(status_code=404, detail="share not found or not owner")
    return {"ok": True, "deleted": share_id}


class DiscordLinkBody(BaseModel):
    """Discord numeric user id for this AgentLayer user (same tenant must stay unique)."""

    discord_user_id: str = Field(default="", max_length=32)


@router.put("/discord")
def put_user_discord_link(request: Request, body: DiscordLinkBody) -> dict:
    """
    Link or unlink your Discord user id for bridge bots (stored on ``users.discord_user_id``).
    Empty string clears the link. Auth for API calls remains Bearer/JWT or API keys — this field
    is metadata so a bot with database access can map Discord → AgentLayer ``users.id``.
    """
    uid, tid = resolve_chat_identity(request)
    try:
        stored = db.user_discord_user_id_set(uid, tid, body.discord_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except UniqueViolation as e:
        raise HTTPException(
            status_code=409,
            detail="This Discord user id is already linked to another account in your tenant.",
        ) from e
    except Exception as e:
        cause = getattr(e, "__cause__", None)
        if isinstance(cause, UniqueViolation):
            raise HTTPException(
                status_code=409,
                detail="This Discord user id is already linked to another account in your tenant.",
            ) from e
        raise
    return {"ok": True, "discord_user_id": stored}


class TelegramLinkBody(BaseModel):
    """Telegram numeric user id for this AgentLayer user (unique per tenant)."""

    telegram_user_id: str = Field(default="", max_length=32)


@router.put("/telegram")
def put_user_telegram_link(request: Request, body: TelegramLinkBody) -> dict:
    """
    Link or unlink your Telegram user id for bridge bots (stored on ``users.telegram_user_id``).
    Empty string clears the link.
    """
    uid, tid = resolve_chat_identity(request)
    try:
        stored = db.user_telegram_user_id_set(uid, tid, body.telegram_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except UniqueViolation as e:
        raise HTTPException(
            status_code=409,
            detail="This Telegram user id is already linked to another account in your tenant.",
        ) from e
    except Exception as e:
        cause = getattr(e, "__cause__", None)
        if isinstance(cause, UniqueViolation):
            raise HTTPException(
                status_code=409,
                detail="This Telegram user id is already linked to another account in your tenant.",
            ) from e
        raise
    return {"ok": True, "telegram_user_id": stored}
