"""Voice STT/TTS HTTP API + user voice preferences."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from apps.backend.domain.http_identity import resolve_chat_identity
from apps.backend.domain.voice import stt, tts, voice_policy

router = APIRouter(tags=["voice"])


class VoicePrefsPatch(BaseModel):
    input_enabled: bool | None = None
    output_enabled: bool | None = None
    language: str | None = Field(default=None, max_length=16)
    voice_id: str | None = Field(default=None, max_length=64)
    mode_web: str | None = Field(default=None, max_length=32)
    mode_telegram: str | None = Field(default=None, max_length=32)
    mode_discord: str | None = Field(default=None, max_length=32)
    edit_transcript_before_send: bool | None = None


class TtsBody(BaseModel):
    text: str = Field(..., max_length=4096)


@router.get("/v1/voice/status")
def voice_status(request: Request) -> dict:
    uid, _tid = resolve_chat_identity(request)
    op = voice_policy.operator_voice_row()
    prefs = voice_policy.user_voice_prefs_get(uid)
    from apps.backend.infrastructure.voice_catalog_providers import (
        resolve_active_voice_stt_provider_id,
        resolve_active_voice_tts_provider_id,
        voice_role_configured,
    )

    stt_base, stt_key = voice_policy.voice_api_credentials()
    return {
        "ok": True,
        "operator_enabled": bool(op.get("voice_enabled")),
        "api_configured": voice_role_configured("stt") and voice_role_configured("tts"),
        "stt_configured": voice_role_configured("stt"),
        "tts_configured": voice_role_configured("tts"),
        "stt_provider_id": resolve_active_voice_stt_provider_id(),
        "tts_provider_id": resolve_active_voice_tts_provider_id(),
        "effective_enabled": voice_policy.effective_voice_enabled(user_id=uid),
        "input_web": voice_policy.effective_voice_input(user_id=uid, channel="web"),
        "output_web": voice_policy.effective_voice_output(user_id=uid, channel="web"),
        "realtime_web": voice_policy.effective_voice_realtime(user_id=uid),
        "discord_vc": voice_policy.effective_discord_vc(user_id=uid),
        "prefs": prefs,
        "limits": {
            "max_seconds": voice_policy.effective_voice_limits()[0],
            "max_bytes": voice_policy.effective_voice_limits()[1],
        },
        "api_base": stt_base,
        "stt_api_base": stt_base,
    }


@router.get("/v1/user/voice")
def get_user_voice_prefs(request: Request) -> dict:
    uid, _tid = resolve_chat_identity(request)
    try:
        prefs = voice_policy.user_voice_prefs_get(uid)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"voice prefs unavailable — {e}") from e
    return {
        "ok": True,
        "prefs": prefs,
        "effective_enabled": voice_policy.effective_voice_enabled(user_id=uid),
    }


@router.put("/v1/user/voice")
def put_user_voice_prefs(request: Request, body: VoicePrefsPatch) -> dict:
    uid, tid = resolve_chat_identity(request)
    patch = body.model_dump(exclude_unset=True)
    try:
        voice_policy.user_voice_prefs_upsert(tid, uid, patch)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "stored": True}


@router.post("/v1/voice/stt")
async def voice_stt(request: Request, file: UploadFile = File(...)) -> dict:
    uid, _tid = resolve_chat_identity(request)
    if not voice_policy.effective_voice_input(user_id=uid, channel="web"):
        raise HTTPException(status_code=403, detail="voice input disabled")

    raw = await file.read()
    mime = (file.content_type or "application/octet-stream").strip()
    lang = voice_policy.effective_stt_language(uid)
    try:
        result = stt.transcribe_audio(raw, mime=mime, language=lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"STT error — {e}") from e
    return {
        "ok": True,
        "transcript": result.transcript,
        "language": result.language or lang,
    }


@router.post("/v1/voice/tts")
def voice_tts_endpoint(request: Request, body: TtsBody) -> Response:
    uid, _tid = resolve_chat_identity(request)
    if not voice_policy.effective_voice_output(user_id=uid, channel="web"):
        raise HTTPException(status_code=403, detail="voice output disabled")
    try:
        audio, mime = tts.synthesize_speech(body.text, user_id=uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS error — {e}") from e
    return Response(content=audio, media_type=mime)
