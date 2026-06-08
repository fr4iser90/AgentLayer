"""Send bridge agent replies as text and/or synthesized voice."""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any

from apps.backend.domain.voice import tts, voice_policy

logger = logging.getLogger(__name__)


def telegram_reply_mode(user_id: uuid.UUID) -> str:
    return str(voice_policy.user_voice_prefs_get(user_id).get("mode_telegram") or "text_only")


def discord_reply_mode(user_id: uuid.UUID) -> str:
    return str(voice_policy.user_voice_prefs_get(user_id).get("mode_discord") or "text_only")


def should_send_voice_reply(user_id: uuid.UUID, channel: str) -> bool:
    return voice_policy.effective_voice_output(user_id=user_id, channel=channel)


def should_send_text_reply(user_id: uuid.UUID, channel: str) -> bool:
    mode = telegram_reply_mode(user_id) if channel == "telegram" else discord_reply_mode(user_id)
    if mode == "voice_reply":
        return False
    return True


async def synthesize_for_bridge(
    user_id: uuid.UUID, text: str, *, channel: str
) -> tuple[bytes, str] | None:
    if not should_send_voice_reply(user_id, channel):
        return None
    try:
        from apps.backend.domain.assistant_display_sanitize import sanitize_assistant_display_text
        from apps.backend.domain.voice.speech_prep import prepare_speech_text

        cleaned = sanitize_assistant_display_text(text) or text
        speech = prepare_speech_text(
            cleaned,
            language=voice_policy.effective_stt_language(user_id),
        )
        return tts.synthesize_speech(speech or cleaned, user_id=user_id)
    except Exception:
        logger.exception("bridge voice TTS failed for user=%s channel=%s", user_id, channel)
        return None


async def send_telegram_agent_reply(
    *,
    msg: Any,
    context: Any,
    chat: Any,
    thread_kw: dict[str, Any],
    user_id: uuid.UUID,
    reply_text: str,
    chunk_text_fn: Any,
) -> None:
    from telegram.error import TelegramError
    from telegram import InputFile

    text = (reply_text or "").strip() or "(empty reply)"
    sent_voice = False
    if should_send_voice_reply(user_id, "telegram"):
        audio = await synthesize_for_bridge(user_id, text, channel="telegram")
        if audio:
            data, _mime = audio
            try:
                await msg.reply_audio(
                    audio=InputFile(io.BytesIO(data), filename="agent.mp3"),
                    **thread_kw,
                )
                sent_voice = True
            except TelegramError:
                logger.exception("telegram_bridge: reply_audio failed")

    if should_send_text_reply(user_id, "telegram") or not sent_voice:
        parts = chunk_text_fn(text, limit=3500)
        await msg.reply_text(parts[0], **thread_kw)
        for extra in parts[1:]:
            await context.bot.send_message(chat_id=chat.id, text=extra, **thread_kw)


async def send_discord_agent_reply(
    *,
    message: Any,
    user_id: uuid.UUID,
    reply_text: str,
    chunk_text_fn: Any,
) -> None:
    import discord

    text = (reply_text or "").strip() or "(empty reply)"
    sent_voice = False
    if should_send_voice_reply(user_id, "discord"):
        audio = await synthesize_for_bridge(user_id, text, channel="discord")
        if audio:
            data, _mime = audio
            try:
                await message.channel.send(file=discord.File(io.BytesIO(data), filename="agent.mp3"))
                sent_voice = True
            except Exception:
                logger.exception("discord_bridge: audio reply failed")

    if should_send_text_reply(user_id, "discord") or not sent_voice:
        parts = chunk_text_fn(text, limit=1900)
        await message.reply(parts[0])
        for part in parts[1:]:
            await message.channel.send(part)
