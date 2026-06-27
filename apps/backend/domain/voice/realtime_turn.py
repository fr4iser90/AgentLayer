"""One voice realtime turn: STT → agent chat → TTS."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from typing import Any, Awaitable, Callable, Protocol

from apps.backend.domain.agent import chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.domain.voice import stt, tts, voice_policy

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


class VoiceRealtimeTurnDependencies(Protocol):
    def user_role(self, user_id: uuid.UUID) -> str: ...


_deps: VoiceRealtimeTurnDependencies | None = None


def register_voice_realtime_turn_dependencies(deps: VoiceRealtimeTurnDependencies) -> None:
    global _deps
    _deps = deps


def user_role(user_id: uuid.UUID) -> str:
    return _deps.user_role(user_id) if _deps is not None else ""


def _extract_reply(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        err = data.get("error") or data.get("detail")
        if err:
            return f"AgentLayer error: {err}"
        return "(empty reply)"
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return "(empty reply)"


def _append_user_transcript(body: dict[str, Any], transcript: str) -> dict[str, Any]:
    work = dict(body)
    messages = work.get("messages")
    if not isinstance(messages, list):
        messages = []
    messages = list(messages)
    messages.append({"role": "user", "content": transcript})
    work["messages"] = messages
    work["stream"] = False
    return work


async def run_voice_realtime_turn(
    *,
    user_id: uuid.UUID,
    tenant_id: int,
    audio_bytes: bytes,
    mime: str,
    chat_body: dict[str, Any] | None,
    emit: EmitFn,
    cancel_event: asyncio.Event | None = None,
    bearer_user_role: str | None = None,
) -> None:
    if cancel_event and cancel_event.is_set():
        await emit({"type": "voice.cancelled"})
        return

    lang = voice_policy.effective_stt_language(user_id)
    loop = asyncio.get_running_loop()
    try:
        stt_result = await loop.run_in_executor(
            None,
            lambda: stt.transcribe_audio(audio_bytes, mime=mime, language=lang),
        )
    except ValueError as e:
        await emit({"type": "voice.error", "detail": str(e)})
        return

    if cancel_event and cancel_event.is_set():
        await emit({"type": "voice.cancelled"})
        return

    transcript = stt_result.transcript
    await emit({"type": "voice.transcript", "text": transcript})

    body = chat_body if isinstance(chat_body, dict) else {}
    work = _append_user_transcript(body, transcript)
    if not work.get("model"):
        await emit({"type": "voice.error", "detail": "chat_body.model required"})
        return

    id_token = set_identity(tenant_id, user_id)
    try:
        if bearer_user_role is None:
            role = user_role(user_id).lower()
            bearer_user_role = role if role in ("user", "admin") else None
        result = await chat_completion(work, bearer_user_role=bearer_user_role)
        reply = _extract_reply(result if isinstance(result, dict) else {})
    except Exception as e:
        logger.exception("voice realtime chat_completion failed")
        await emit({"type": "voice.error", "detail": str(e)[:500]})
        return
    finally:
        reset_identity(id_token)

    if cancel_event and cancel_event.is_set():
        await emit({"type": "voice.cancelled"})
        return

    await emit({"type": "voice.reply_text", "text": reply})

    if not voice_policy.effective_voice_output(user_id=user_id, channel="web"):
        await emit({"type": "voice.done"})
        return

    from apps.backend.domain.assistant_display_sanitize import sanitize_assistant_display_text
    from apps.backend.domain.voice.speech_prep import prepare_speech_text

    display_reply = sanitize_assistant_display_text(reply)
    speech_text = prepare_speech_text(
        display_reply or reply,
        language=voice_policy.effective_stt_language(user_id),
    )
    if speech_text:
        await emit({"type": "voice.speech_text", "text": speech_text})

    try:
        audio_out, out_mime = await loop.run_in_executor(
            None,
            lambda: tts.synthesize_speech(speech_text or display_reply or reply, user_id=user_id),
        )
    except ValueError as e:
        await emit({"type": "voice.error", "detail": str(e)})
        return

    await emit(
        {
            "type": "voice.audio",
            "mime": out_mime,
            "audio_b64": base64.b64encode(audio_out).decode("ascii"),
        }
    )
    await emit({"type": "voice.done"})
