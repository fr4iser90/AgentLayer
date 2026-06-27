"""
Discord voice channel sessions: join VC, listen, STT → agent → TTS playback.

Requires optional deps: ``discord-ext-voice-recv``, ``PyNaCl``, and ``ffmpeg`` on PATH.
"""

from __future__ import annotations

import asyncio
import io
import logging
import tempfile
import time
import uuid
import wave
from dataclasses import dataclass, field
from typing import Any

import discord

from apps.backend.domain.voice import stt, tts, voice_policy
from apps.backend.infrastructure.bridge_agent_session import BRIDGE_DISCORD
from apps.backend.infrastructure.bridge_agent_turn import run_bridge_agent_turn
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

try:
    from discord.ext import voice_recv

    _VOICE_RECV = True
except ImportError:
    voice_recv = None  # type: ignore[assignment]
    _VOICE_RECV = False

_SAMPLE_RATE = 48_000
_CHANNELS = 2
_SAMPLE_WIDTH = 2
_SILENCE_SEC = 1.4
_MIN_PCM_BYTES = _SAMPLE_RATE * _CHANNELS * _SAMPLE_WIDTH // 4  # ~0.25s


@dataclass
class _VcSession:
    guild_id: int
    text_channel_id: int
    agent_user_id: uuid.UUID
    tenant_id: int
    cfg_model: str
    cfg_catalog: str
    discord_user_id: int
    pcm: bytearray = field(default_factory=bytearray)
    last_pcm_at: float = 0.0
    processing: bool = False
    voice_client: Any = None
    flush_task: asyncio.Task | None = None


_sessions: dict[int, _VcSession] = {}
_flush_tasks: dict[int, asyncio.Task] = {}


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(_SAMPLE_WIDTH)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def _voice_recv_available() -> bool:
    return _VOICE_RECV


async def handle_discord_voice_slash(
    message: discord.Message,
    *,
    user_id: uuid.UUID,
    tenant_id: int,
    prompt: str,
    cfg_model: str,
    cfg_catalog: str,
) -> str:
    if not voice_policy.effective_discord_vc(user_id=user_id):
        return (
            "Discord voice channel is disabled. Admin: enable **Voice → Discord VC**; "
            "user: Settings → Voice."
        )
    if not _voice_recv_available():
        return (
            "Discord VC is disabled in the default install. It needs optional "
            "`discord-ext-voice-recv`, PyNaCl, and ffmpeg on the server."
        )

    parts = (prompt or "").strip().split()
    sub = parts[1].lower() if len(parts) > 1 else "help"

    if sub in ("help", "?"):
        return (
            "**Voice channel (Discord)**\n"
            "- `/voice join` — bot joins your voice channel and listens\n"
            "- `/voice leave` — disconnect\n"
            "- `/voice status` — session info\n"
            "Speak in VC; after a short pause the agent replies in voice (+ optional text in this channel)."
        )

    guild = message.guild
    if guild is None:
        return "Voice channel commands work in servers only."

    gid = int(guild.id)

    if sub == "status":
        sess = _sessions.get(gid)
        if not sess:
            return "No active voice session in this server."
        vc = sess.voice_client
        connected = vc is not None and vc.is_connected()
        return (
            f"Voice session active (connected={connected}). "
            f"Linked AgentLayer user listens as Discord id `{sess.discord_user_id}`."
        )

    if sub == "leave":
        return await _leave_session(gid)

    if sub == "join":
        if gid in _sessions and _sessions[gid].voice_client and _sessions[gid].voice_client.is_connected():
            return "Already in a voice channel here. Use `/voice leave` first."

        member = message.author
        if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel is None:
            return "Join a voice channel first, then send `/voice join`."

        ch = member.voice.channel
        if not isinstance(ch, discord.VoiceChannel):
            return "Unsupported channel type."

        try:
            vc = await ch.connect(cls=voice_recv.VoiceRecvClient)
        except Exception as e:
            logger.exception("discord vc connect failed")
            return f"Could not join voice channel: {e!s:.300}"

        sess = _VcSession(
            guild_id=gid,
            text_channel_id=int(message.channel.id),
            agent_user_id=user_id,
            tenant_id=tenant_id,
            cfg_model=cfg_model,
            cfg_catalog=cfg_catalog,
            discord_user_id=int(member.id),
            voice_client=vc,
        )
        _sessions[gid] = sess

        def _on_pcm(user: discord.Member | discord.User | None, data: Any) -> None:
            if user is None:
                return
            if int(user.id) != sess.discord_user_id:
                return
            pcm = getattr(data, "pcm", None)
            if not pcm:
                return
            sess.pcm.extend(pcm)
            sess.last_pcm_at = time.monotonic()

        vc.listen(voice_recv.BasicSink(_on_pcm))
        _flush_tasks[gid] = asyncio.create_task(_flush_loop(sess, message.channel))
        return f"Joined **{ch.name}**. Speak — I'll reply after you pause."

    return "Unknown subcommand. Try `/voice help`."


async def _leave_session(gid: int) -> str:
    task = _flush_tasks.pop(gid, None)
    if task:
        task.cancel()
    sess = _sessions.pop(gid, None)
    if not sess or not sess.voice_client:
        return "Not connected to a voice channel."
    try:
        if hasattr(sess.voice_client, "stop_listening"):
            sess.voice_client.stop_listening()
        await sess.voice_client.disconnect(force=True)
    except Exception:
        logger.exception("discord vc leave failed guild=%s", gid)
    return "Left voice channel."


async def _flush_loop(sess: _VcSession, text_channel: discord.abc.Messageable) -> None:
    try:
        while sess.guild_id in _sessions:
            await asyncio.sleep(0.35)
            await _maybe_flush(sess, text_channel)
    except asyncio.CancelledError:
        raise


async def _maybe_flush(sess: _VcSession, text_channel: discord.abc.Messageable) -> None:
    if sess.processing:
        return
    if len(sess.pcm) < _MIN_PCM_BYTES:
        return
    if time.monotonic() - sess.last_pcm_at < _SILENCE_SEC:
        return
    sess.processing = True
    pcm = bytes(sess.pcm)
    sess.pcm.clear()
    try:
        await _process_utterance(sess, text_channel, pcm)
    finally:
        sess.processing = False


async def _process_utterance(
    sess: _VcSession,
    text_channel: discord.abc.Messageable,
    pcm: bytes,
) -> None:
    wav = _pcm_to_wav(pcm)
    lang = voice_policy.effective_stt_language(sess.agent_user_id)
    loop = asyncio.get_running_loop()
    try:
        stt_result = await loop.run_in_executor(
            None,
            lambda: stt.transcribe_audio(wav, mime="audio/wav", language=lang),
        )
    except ValueError as e:
        await text_channel.send(f"Could not transcribe: {e!s:.200}")
        return

    transcript = stt_result.transcript
    try:
        reply, _conv = await run_bridge_agent_turn(
            user_id=sess.agent_user_id,
            tenant_id=sess.tenant_id,
            prompt=transcript,
            model=sess.cfg_model,
            catalog_owned_by=sess.cfg_catalog,
            provider=BRIDGE_DISCORD,
            scope_chat_id=sess.text_channel_id,
            scope_thread_id=None,
        )
    except Exception as e:
        await text_channel.send(f"Agent error: {e!s:.300}")
        return

    from apps.backend.domain.voice.bridge_reply import should_send_text_reply

    if should_send_text_reply(sess.agent_user_id, "discord"):
        await text_channel.send(f"**You:** {transcript}\n**Agent:** {reply[:1800]}")

    vc = sess.voice_client
    if not vc or not vc.is_connected():
        return
    if not voice_policy.effective_voice_output(user_id=sess.agent_user_id, channel="discord"):
        return

    try:
        from apps.backend.domain.assistant_display_sanitize import sanitize_assistant_display_text
        from apps.backend.domain.voice.speech_prep import prepare_speech_text

        cleaned = sanitize_assistant_display_text(reply) or reply
        speech = prepare_speech_text(
            cleaned,
            language=voice_policy.effective_stt_language(sess.agent_user_id),
        )

        mp3, _mime = await loop.run_in_executor(
            None,
            lambda: tts.synthesize_speech(speech or cleaned, user_id=sess.agent_user_id),
        )
    except ValueError as e:
        await text_channel.send(f"TTS failed: {e!s:.200}")
        return

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3)
        path = tmp.name

    try:
        if vc.is_playing():
            vc.stop()
        source = discord.FFmpegPCMAudio(path)
        vc.play(source)
    except Exception as e:
        logger.exception("discord vc play failed")
        await text_channel.send(f"Could not play reply in VC: {e!s:.200}")
    finally:
        try:
            import os

            os.unlink(path)
        except OSError:
            pass
