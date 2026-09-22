"""Telegram audio intake: voice notes, audio uploads, and audio sent as documents.

Extracted from ``telegram_bridge`` so the three shapes share one turn pipeline
instead of three near-copies. Handlers are produced by :func:`make_audio_handlers`
because they close over the bridge config.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from apps.backend.domain.voice.bridge_reply import send_telegram_agent_reply
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.integrations.bridge_agent_session import BRIDGE_TELEGRAM
from apps.backend.infrastructure.integrations.bridge_agent_turn import run_bridge_agent_turn
from apps.backend.infrastructure.integrations.telegram_bridge_helpers import (
    audio_mime,
    select_audio_payload,
)

logger = logging.getLogger(__name__)


async def _download_telegram_file(
    context: ContextTypes.DEFAULT_TYPE, file_id: str
) -> bytes | None:
    try:
        tg_file = await context.bot.get_file(file_id)
        return bytes(await tg_file.download_as_bytearray())
    except Exception:
        logger.exception("telegram_bridge: file download failed (file_id=%s)", file_id)
        return None


async def _audio_gate(
    update: Any,
) -> tuple[Any, Any, str, Any, Any, dict[str, Any]] | None:
    """Resolve the sender and the voice gate for an audio-bearing message.

    Returns ``(msg, chat, author_id, user_id, tenant_id, thread_kw)``, or ``None``
    after the user has already been told why we stopped.
    """
    from apps.backend.domain.voice import voice_policy

    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or user.is_bot:
        return None
    author_id = str(user.id)
    linked = db.user_id_tenant_for_telegram_global(author_id)
    if linked is None:
        await msg.reply_text(
            "Your Telegram account is not linked in AgentLayer. "
            "Open the web app → Settings → Connections → save your numeric Telegram user id."
        )
        return None
    user_id, tenant_id = linked
    if not voice_policy.effective_voice_input(user_id=user_id, channel="telegram"):
        await msg.reply_text(
            "Voice input is disabled. Ask your admin to enable Voice, then "
            "Settings → Voice in the web app."
        )
        return None
    thread_kw: dict[str, Any] = {}
    if getattr(msg, "message_thread_id", None) is not None:
        thread_kw["message_thread_id"] = msg.message_thread_id
    return msg, msg.chat, author_id, user_id, tenant_id, thread_kw


async def _run_audio_turn(
    *,
    cfg: Any,
    msg: Any,
    context: ContextTypes.DEFAULT_TYPE,
    chat: Any,
    author_id: str,
    user_id: Any,
    tenant_id: Any,
    thread_kw: dict[str, Any],
    audio_bytes: bytes,
    mime: str,
    kind: str,
) -> None:
    """Transcribe one audio payload and answer it as a normal agent turn."""
    from apps.backend.domain.voice import stt, voice_policy

    lang = voice_policy.effective_stt_language(user_id)
    try:
        stt_result = stt.transcribe_audio(audio_bytes, mime=mime, language=lang)
    except ValueError as e:
        await msg.reply_text(f"Could not transcribe {kind}: {e!s:.400}", **thread_kw)
        return

    prompt = stt_result.transcript
    logger.info(
        "telegram_bridge: %s request (telegram_user_id=%s, agentlayer_user=%s, chars=%d, mime=%s)",
        kind,
        author_id,
        user_id,
        len(prompt),
        mime,
    )

    async def _typing_heartbeat() -> None:
        try:
            while True:
                await context.bot.send_chat_action(
                    chat_id=chat.id,
                    action=ChatAction.TYPING,
                    **thread_kw,
                )
                await asyncio.sleep(4.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("telegram_bridge: %s typing heartbeat failed", kind, exc_info=True)

    typing_task = asyncio.create_task(_typing_heartbeat())
    try:
        try:
            reply_text, _conv_id = await run_bridge_agent_turn(
                user_id=user_id,
                tenant_id=tenant_id,
                prompt=prompt,
                model=cfg.model,
                catalog_owned_by=cfg.catalog_owned_by,
                provider=BRIDGE_TELEGRAM,
                scope_chat_id=int(chat.id),
                scope_thread_id=getattr(msg, "message_thread_id", None),
            )
        except ValueError as e:
            await msg.reply_text(f"AgentLayer: {e!s:.1500}", **thread_kw)
            return
        except Exception as e:
            logger.exception("telegram_bridge: %s chat completion failed", kind)
            await msg.reply_text(f"Request failed: {e!s:.500}", **thread_kw)
            return
        await send_telegram_agent_reply(
            msg=msg,
            context=context,
            chat=chat,
            thread_kw=thread_kw,
            user_id=user_id,
            reply_text=reply_text,
        )
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


def make_audio_handlers(cfg: Any) -> tuple[Callable[..., Any], Callable[..., Any]]:
    """Build ``(on_voice, on_audio_file)`` bound to the bridge config."""

    async def on_voice(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        gated = await _audio_gate(update)
        if gated is None:
            return
        msg, chat, author_id, user_id, tenant_id, thread_kw = gated
        if not getattr(msg, "voice", None):
            return
        audio_bytes = await _download_telegram_file(context, msg.voice.file_id)
        if audio_bytes is None:
            await msg.reply_text("Could not download voice message.", **thread_kw)
            return
        # Telegram voice notes are always OGG/Opus regardless of the mime it reports.
        await _run_audio_turn(
            cfg=cfg,
            msg=msg,
            context=context,
            chat=chat,
            author_id=author_id,
            user_id=user_id,
            tenant_id=tenant_id,
            thread_kw=thread_kw,
            audio_bytes=audio_bytes,
            mime="audio/ogg",
            kind="voice",
        )

    async def on_audio_file(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Audio uploaded as a file rather than recorded as a voice note."""
        selected = select_audio_payload(getattr(update, "effective_message", None))
        if selected is None:
            return
        payload, mime = selected

        gated = await _audio_gate(update)
        if gated is None:
            return
        _msg, chat, author_id, user_id, tenant_id, thread_kw = gated

        audio_bytes = await _download_telegram_file(context, payload.file_id)
        if audio_bytes is None:
            await gated[0].reply_text("Could not download the audio file.", **thread_kw)
            return

        await _run_audio_turn(
            cfg=cfg,
            msg=gated[0],
            context=context,
            chat=chat,
            author_id=author_id,
            user_id=user_id,
            tenant_id=tenant_id,
            thread_kw=thread_kw,
            audio_bytes=audio_bytes,
            mime=mime or audio_mime(payload),
            kind="audio file",
        )

    return on_voice, on_audio_file
