"""Voice STT/TTS HTTP API + user voice preferences."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from apps.backend.domain.shared.http_identity import resolve_chat_identity
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
    uid, tid = resolve_chat_identity(request)
    op = voice_policy.operator_voice_row()
    prefs = voice_policy.user_voice_prefs_get(uid)
    from apps.backend.application.voice.use_cases.voice_controller_services import (
        resolve_active_voice_stt_provider_id,
        resolve_active_voice_tts_provider_id,
        voice_role_configured,
    )
    from apps.backend.application.voice.use_cases.voice_controller_services import is_provider_capability_allowed

    stt_base, stt_key = voice_policy.voice_api_credentials()
    stt_provider_id = resolve_active_voice_stt_provider_id()
    tts_provider_id = resolve_active_voice_tts_provider_id()
    stt_allowed = (
        bool(stt_provider_id)
        and is_provider_capability_allowed("stt", stt_provider_id or "", tenant_id=tid, user_id=uid)
    )
    tts_allowed = (
        bool(tts_provider_id)
        and is_provider_capability_allowed("tts", tts_provider_id or "", tenant_id=tid, user_id=uid)
    )
    return {
        "ok": True,
        "operator_enabled": bool(op.get("voice_enabled")),
        "api_configured": voice_role_configured("stt") and voice_role_configured("tts"),
        "stt_configured": voice_role_configured("stt") and stt_allowed,
        "tts_configured": voice_role_configured("tts") and tts_allowed,
        "stt_provider_id": stt_provider_id,
        "tts_provider_id": tts_provider_id,
        "effective_enabled": voice_policy.effective_voice_enabled(user_id=uid) and stt_allowed and tts_allowed,
        "input_web": voice_policy.effective_voice_input(user_id=uid, channel="web") and stt_allowed,
        "output_web": voice_policy.effective_voice_output(user_id=uid, channel="web") and tts_allowed,
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
    uid, tid = resolve_chat_identity(request)
    if not voice_policy.effective_voice_input(user_id=uid, channel="web"):
        raise HTTPException(status_code=403, detail="voice input disabled")
    from apps.backend.application.voice.use_cases.voice_controller_services import is_provider_capability_allowed
    from apps.backend.application.voice.use_cases.voice_controller_services import resolve_active_voice_stt_provider_id

    provider_id = resolve_active_voice_stt_provider_id()
    if not provider_id or not is_provider_capability_allowed("stt", provider_id, tenant_id=tid, user_id=uid):
        raise HTTPException(status_code=403, detail="voice input disabled for this user")

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
    uid, tid = resolve_chat_identity(request)
    if not voice_policy.effective_voice_output(user_id=uid, channel="web"):
        raise HTTPException(status_code=403, detail="voice output disabled")
    from apps.backend.application.voice.use_cases.voice_controller_services import is_provider_capability_allowed
    from apps.backend.application.voice.use_cases.voice_controller_services import resolve_active_voice_tts_provider_id

    provider_id = resolve_active_voice_tts_provider_id()
    if not provider_id or not is_provider_capability_allowed("tts", provider_id, tenant_id=tid, user_id=uid):
        raise HTTPException(status_code=403, detail="voice output disabled for this user")
    try:
        from apps.backend.domain.voice.speech_prep import prepare_speech_text

        speech = prepare_speech_text(
            body.text,
            language=voice_policy.effective_stt_language(uid),
        )
        audio, mime = tts.synthesize_speech(speech or body.text, user_id=uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS error — {e}") from e
    return Response(content=audio, media_type=mime)
