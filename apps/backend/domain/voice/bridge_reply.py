"""Send bridge agent replies as text and/or synthesized voice."""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any

from apps.backend.domain.shared.bridge_formatting import (
    chunk_markdown,
    markdown_to_html,
    neutralize_discord_mentions,
)
from apps.backend.domain.voice import tts, voice_policy

logger = logging.getLogger(__name__)

# Telegram's hard cap is 4096; HTML escaping inflates the source, so we chunk the
# markdown first and shrink only if the rendered HTML would not fit.
_TELEGRAM_HARD_LIMIT = 4096
_TELEGRAM_PREFERRED_LIMIT = 3500
_DISCORD_LIMIT = 1900


def telegram_html_chunks(text: str, *, hard_limit: int = _TELEGRAM_HARD_LIMIT) -> list[str]:
    """Chunk markdown, then render each chunk as Telegram-safe HTML that fits the cap."""
    out: list[str] = []
    for source in chunk_markdown(text, limit=_TELEGRAM_PREFERRED_LIMIT):
        out.extend(_fit_html(source, hard_limit))
    return out


def _fit_html(source: str, hard_limit: int) -> list[str]:
    limit = max(32, min(len(source), _TELEGRAM_PREFERRED_LIMIT))
    while True:
        rendered = [markdown_to_html(part) for part in chunk_markdown(source, limit=limit)]
        if all(len(r) <= hard_limit for r in rendered):
            return rendered
        if limit <= 32:
            return rendered
        limit = max(32, limit // 2)


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
        from apps.backend.domain.agent_runtime.assistant_display import sanitize_assistant_display_text
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


_AUDIO_EXT_BY_MIME = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/flac": "flac",
}


def _audio_filename(mime: str) -> str:
    """Name the temp file after the bytes we actually got.

    The provider is asked for mp3 but Piper answers with WAV. A ``.mp3`` name over
    WAV bytes is what makes Telegram reject or silently fail to play the clip.
    """
    base = (mime or "").split(";")[0].strip().lower()
    return f"agent.{_AUDIO_EXT_BY_MIME.get(base, 'mp3')}"


async def send_telegram_agent_reply(
    *,
    msg: Any,
    context: Any,
    chat: Any,
    thread_kw: dict[str, Any],
    user_id: uuid.UUID,
    reply_text: str,
    chunk_text_fn: Any = None,
) -> None:
    from telegram.error import TelegramError
    from telegram import InputFile

    text = (reply_text or "").strip() or "(empty reply)"
    sent_voice = False
    if should_send_voice_reply(user_id, "telegram"):
        audio = await synthesize_for_bridge(user_id, text, channel="telegram")
        if audio:
            data, mime = audio
            try:
                await msg.reply_audio(
                    audio=InputFile(io.BytesIO(data), filename=_audio_filename(mime)),
                    **thread_kw,
                )
                sent_voice = True
            except TelegramError:
                logger.exception("telegram_bridge: reply_audio failed")

    if should_send_text_reply(user_id, "telegram") or not sent_voice:
        parts = telegram_html_chunks(text) if chunk_text_fn is None else chunk_text_fn(text)
        await msg.reply_text(parts[0], parse_mode="HTML", **thread_kw)
        for extra in parts[1:]:
            await context.bot.send_message(
                chat_id=chat.id, text=extra, parse_mode="HTML", **thread_kw
            )


async def send_discord_agent_reply(
    *,
    message: Any,
    user_id: uuid.UUID,
    reply_text: str,
    chunk_text_fn: Any = None,
) -> None:
    import discord

    text = neutralize_discord_mentions((reply_text or "").strip()) or "(empty reply)"
    sent_voice = False
    if should_send_voice_reply(user_id, "discord"):
        audio = await synthesize_for_bridge(user_id, text, channel="discord")
        if audio:
            data, mime = audio
            try:
                await message.channel.send(
                    file=discord.File(io.BytesIO(data), filename=_audio_filename(mime))
                )
                sent_voice = True
            except Exception:
                logger.exception("discord_bridge: audio reply failed")

    if should_send_text_reply(user_id, "discord") or not sent_voice:
        parts = (
            chunk_markdown(text, limit=_DISCORD_LIMIT)
            if chunk_text_fn is None
            else chunk_text_fn(text)
        )
        await message.reply(parts[0])
        for part in parts[1:]:
            await message.channel.send(part)
