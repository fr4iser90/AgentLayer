"""
Duplex voice WebSocket: utterance in → STT → agent → TTS audio out.

Connect: ``GET /ws/v1/voice/realtime?token=<JWT_or_user_API_key>``

Client → server:
  - ``{"type":"ping"}``
  - ``{"type":"cancel"}`` — abort in-flight turn (barge-in)
  - ``{"type":"utterance","audio_b64":"...","mime":"audio/webm","chat_body":{...}}``
        ``chat_body`` = OpenAI-style chat request (``model``, ``messages``, optional ``conversation_id``).

Server → client:
  - ``voice.session``, ``voice.transcript``, ``voice.reply_text``, ``voice.audio``, ``voice.done``
  - ``voice.error``, ``voice.cancelled``
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.backend.api.chat.controllers.chat_websocket import _bearer_from_ws, _ws_connection_authorized
from apps.backend.domain.shared.http_identity import resolve_chat_identity_ws
from apps.backend.domain.voice import voice_policy
from apps.backend.domain.voice.realtime_turn import run_voice_realtime_turn
from apps.backend.application.identity.use_cases.request_auth import get_user_for_bearer_token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/v1/voice/realtime")
async def voice_realtime_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    if not _ws_connection_authorized(websocket):
        try:
            await websocket.send_json({"type": "voice.error", "detail": "unauthorized"})
        except Exception:
            pass
        await websocket.close(code=4401)
        return

    try:
        user_id, tenant_id = resolve_chat_identity_ws(websocket)
    except Exception as exc:
        detail = str(exc)
        try:
            await websocket.send_json({"type": "voice.error", "detail": detail})
        except Exception:
            pass
        await websocket.close(code=4401)
        return

    if not voice_policy.effective_voice_realtime(user_id=user_id):
        try:
            await websocket.send_json(
                {
                    "type": "voice.error",
                    "detail": "realtime voice disabled (operator or user settings)",
                }
            )
        except Exception:
            pass
        await websocket.close(code=4403)
        return

    cancel_event = asyncio.Event()
    turn_lock = asyncio.Lock()

    async def emit(ev: dict[str, Any]) -> None:
        try:
            await websocket.send_json(ev)
        except Exception:
            logger.debug("voice realtime emit failed", exc_info=True)

    await emit({"type": "voice.session", "ok": True})

    bearer = _bearer_from_ws(websocket)
    ws_user = get_user_for_bearer_token(bearer) if bearer else None
    bearer_role = ws_user.role.lower() if ws_user else None

    try:
        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            if not isinstance(msg, dict):
                await emit({"type": "voice.error", "detail": "JSON object expected"})
                continue

            typ = msg.get("type")
            if typ == "ping":
                await emit({"type": "pong"})
                continue
            if typ == "cancel":
                cancel_event.set()
                await emit({"type": "voice.cancelled"})
                continue
            if typ != "utterance":
                await emit({"type": "voice.error", "detail": "expected type=utterance"})
                continue

            raw_b64 = msg.get("audio_b64")
            if not isinstance(raw_b64, str) or not raw_b64.strip():
                await emit({"type": "voice.error", "detail": "audio_b64 required"})
                continue
            try:
                audio_bytes = base64.b64decode(raw_b64, validate=True)
            except Exception:
                await emit({"type": "voice.error", "detail": "invalid audio_b64"})
                continue

            mime = str(msg.get("mime") or "audio/webm").strip()
            chat_body = msg.get("chat_body")
            if chat_body is not None and not isinstance(chat_body, dict):
                await emit({"type": "voice.error", "detail": "chat_body must be object"})
                continue

            cancel_event.clear()
            async with turn_lock:
                await run_voice_realtime_turn(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    audio_bytes=audio_bytes,
                    mime=mime,
                    chat_body=chat_body,
                    emit=emit,
                    cancel_event=cancel_event,
                    bearer_user_role=bearer_role,
                )
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
