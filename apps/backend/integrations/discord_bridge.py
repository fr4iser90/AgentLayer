"""
In-process Discord gateway: runs in a daemon thread inside the same process as Uvicorn.

Configuration is read from ``operator_settings`` (Admin → Interfaces). Messages that match
the prefix are allowed only for Discord user ids linked in ``users.discord_user_id``; chat
then runs via :func:`apps.domain.agent.chat_completion` in-process (same identity as that user).

**Context:** Each Discord channel / DM / thread keeps a rolling conversation in Postgres
(``bridge_agent_sessions``), like Telegram. Send ``/clear`` / ``reset`` / ``neu`` after the
prefix to start over. The web UI already sends full ``messages[]`` per turn — no bridge table.
Restarts pick up DB changes on the next reconnect cycle after ``client.run`` ends.

**New bridges:** Same persistence pattern as below; guide: ``integrations/bridges/README.md``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import discord

from apps.backend.domain.agent import chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure.bridge_agent_session import (
    BRIDGE_DISCORD,
    MAX_CONTEXT_MESSAGES,
    bridge_agent_conversation_ensure,
    bridge_agent_session_reset,
    bridge_chat_completion_extras,
    bridge_try_slash_command,
    messages_for_bridge_completion,
)
from apps.backend.infrastructure.conversations_db import conversation_append_message
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None
_started = False
_logged_idle_reason: str | None = None


@dataclass
class _BridgeCfg:
    discord_token: str
    model: str
    catalog_owned_by: str
    prefix: str


def _chunk_text(text: str, limit: int = 1900) -> list[str]:
    t = (text or "").strip() or "(empty reply)"
    out: list[str] = []
    while t:
        out.append(t[:limit])
        t = t[limit:]
    return out


def _extract_reply(data: dict[str, Any]) -> str:
    err = data.get("error") or data.get("detail")
    if isinstance(err, dict):
        err = err.get("message") or str(err)
    if err and not data.get("choices"):
        return f"AgentLayer error: {err}"
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return f"Unexpected response: {data!r:.2000}"
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return f"(no text in response: {data!r:.1500})"


def _normalize_discord_bot_token(raw: str) -> str:
    """Strip quotes/whitespace; Discord bot tokens must not contain spaces or newlines."""
    s = (raw or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return "".join(s.split())


def _load_bridge_cfg_with_reason() -> tuple[_BridgeCfg | None, str]:
    """Blocking read of operator_settings (Discord token, prefix, model)."""
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT discord_bot_enabled, discord_bot_token,
                           discord_trigger_prefix, discord_chat_model
                    FROM operator_settings WHERE id = 1
                    """
                )
                row = cur.fetchone()
    except Exception:
        logger.exception("discord_bridge: could not read operator_settings (migrations applied?)")
        return None, "database error (see log above)"
    if not row:
        return None, "no operator_settings row for id=1"
    enabled, dtoken, trigger, cmodel = row
    if not enabled:
        return None, "discord_bot_enabled is false (Admin → Interfaces → Discord)"
    dt = _normalize_discord_bot_token(str(dtoken) if dtoken is not None else "")
    if not dt:
        return None, "discord_bot_token is empty (paste token in Admin → Interfaces → Discord)"
    if trigger is None:
        prefix = "!agent "
    else:
        prefix = str(trigger).strip()
    if prefix and not prefix.endswith(" "):
        prefix = prefix + " "
    model_raw = (str(cmodel).strip() if cmodel is not None else "") or ""
    try:
        from apps.backend.domain.catalog_chat_llm import catalog_llm_body_extras

        llm = catalog_llm_body_extras(model=model_raw or None, profile_key="agent")
    except ValueError as exc:
        return None, str(exc)
    return (
        _BridgeCfg(
            discord_token=dt,
            model=str(llm["model"]),
            catalog_owned_by=str(llm["agent_model_catalog_owned_by"]),
            prefix=prefix,
        ),
        "",
    )


def _load_bridge_cfg() -> _BridgeCfg | None:
    cfg, _ = _load_bridge_cfg_with_reason()
    return cfg


def _first_audio_attachment(message: discord.Message) -> discord.Attachment | None:
    for att in message.attachments:
        ct = (att.content_type or "").lower()
        name = (att.filename or "").lower()
        if ct.startswith("audio/") or name.endswith((".ogg", ".opus", ".mp3", ".m4a", ".wav", ".webm")):
            return att
    return None


async def _handle_discord_voice_message(
    cfg: _BridgeCfg, message: discord.Message, attachment: discord.Attachment
) -> None:
    from apps.backend.domain.voice import stt, voice_policy
    from apps.backend.domain.voice.bridge_reply import send_discord_agent_reply
    from apps.backend.infrastructure.bridge_agent_turn import run_bridge_agent_turn

    author_id = str(message.author.id)
    linked = db.user_id_tenant_for_discord_global(author_id)
    if linked is None:
        await message.reply(
            "Your Discord account is not linked in AgentLayer. "
            "Open the web app → **Settings → Connections** → save your numeric Discord user ID."
        )
        return
    user_id, tenant_id = linked
    if not voice_policy.effective_voice_input(user_id=user_id, channel="discord"):
        await message.reply(
            "Voice input is disabled. Enable Voice under Settings in the web app (admin must enable Voice globally)."
        )
        return

    try:
        audio_bytes = await attachment.read()
    except Exception as e:
        logger.exception("discord_bridge: audio attachment read failed")
        await message.reply(f"Could not read audio attachment: {e!s:.300}")
        return

    mime = (attachment.content_type or "audio/ogg").strip()
    lang = voice_policy.effective_stt_language(user_id)
    try:
        stt_result = stt.transcribe_audio(audio_bytes, mime=mime, language=lang)
    except ValueError as e:
        await message.reply(f"Could not transcribe audio: {e!s:.400}")
        return

    prompt = stt_result.transcript
    _ch_id = int(message.channel.id)
    logger.info(
        "discord_bridge: voice request (discord_user_id=%s, agentlayer_user=%s, chars=%d)",
        author_id,
        user_id,
        len(prompt),
    )
    async with message.channel.typing():
        try:
            reply_text, _conv_id = await run_bridge_agent_turn(
                user_id=user_id,
                tenant_id=tenant_id,
                prompt=prompt,
                model=cfg.model,
                catalog_owned_by=cfg.catalog_owned_by,
                provider=BRIDGE_DISCORD,
                scope_chat_id=_ch_id,
                scope_thread_id=None,
            )
        except ValueError as e:
            await message.reply(f"AgentLayer: {e!s:.1500}")
            return
        except Exception as e:
            logger.exception("discord_bridge: voice chat completion failed")
            await message.reply(f"Request failed: {e!s:.500}")
            return
    await send_discord_agent_reply(
        message=message,
        user_id=user_id,
        reply_text=reply_text,
        chunk_text_fn=_chunk_text,
    )


def _make_client(cfg: _BridgeCfg) -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    # One hint per Discord session (empty text in servers usually means Message Content Intent off).
    _empty_text_hint: dict[str, bool] = {"sent": False}

    class BridgeClient(discord.Client):
        async def on_ready(self) -> None:
            assert self.user is not None
            logger.info("discord_bridge: logged in to Discord as %s (%s)", self.user.name, self.user.id)

        async def on_message(self, message: discord.Message) -> None:
            if message.author.bot:
                return

            audio_att = _first_audio_attachment(message)
            if audio_att is not None:
                await _handle_discord_voice_message(cfg, message, audio_att)
                return

            if not (message.content or "").strip():
                if message.guild is not None and not _empty_text_hint["sent"]:
                    _empty_text_hint["sent"] = True
                    pfx = cfg.prefix.strip() if cfg.prefix else "(no prefix)"
                    logger.warning(
                        "discord_bridge: saw a server message with no text — if your %r commands never run, "
                        "enable **Message Content Intent** (Discord Developer Portal → Bot → Privileged Gateway Intents).",
                        pfx,
                    )
                return
            if cfg.prefix:
                if not message.content.startswith(cfg.prefix):
                    return
                prompt = message.content[len(cfg.prefix) :].strip()
            else:
                prompt = (message.content or "").strip()
            if not prompt:
                if cfg.prefix:
                    await message.reply(
                        f"Add your question after `{cfg.prefix.strip()}`, e.g. `{cfg.prefix.strip()}What is 2+2?`"
                    )
                return
            author_id = str(message.author.id)
            linked = db.user_id_tenant_for_discord_global(author_id)
            if linked is None:
                await message.reply(
                    "Your Discord account is not linked in AgentLayer (or the link is ambiguous). "
                    "Open the web app → **Settings → Connections** → save your numeric Discord user ID."
                )
                return
            user_id, tenant_id = linked
            _ch_id = int(message.channel.id)

            if prompt.strip().lower().startswith("/voice"):
                from apps.backend.integrations.discord_voice_session import handle_discord_voice_slash

                reply = await handle_discord_voice_slash(
                    message,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    prompt=prompt,
                    cfg_model=cfg.model,
                    cfg_catalog=cfg.catalog_owned_by,
                )
                await message.reply(reply)
                return

            clear_tokens = frozenset(
                {
                    "/clear",
                    "/reset",
                    "clear",
                    "reset",
                    "neu",
                    "neuer chat",
                    "/neu",
                }
            )
            if prompt.strip().lower() in clear_tokens:
                bridge_agent_conversation_ensure(
                    user_id,
                    tenant_id,
                    provider=BRIDGE_DISCORD,
                    scope_chat_id=_ch_id,
                    scope_thread_id=None,
                    model=cfg.model,
                )
                ok = bridge_agent_session_reset(
                    user_id,
                    provider=BRIDGE_DISCORD,
                    scope_chat_id=_ch_id,
                    scope_thread_id=None,
                )
                await message.reply(
                    "Konversationsverlauf geleert (Workspace-/Agent-Bindung bleibt)."
                    if ok
                    else "Es war kein gespeicherter Verlauf vorhanden."
                )
                return

            logger.info(
                "discord_bridge: chat request (discord_user_id=%s, agentlayer_user=%s, model=%s)",
                author_id,
                user_id,
                cfg.model,
            )
            # Rolling DB context for this Discord channel; new gateways: README in integrations/bridges/.
            conv_id = bridge_agent_conversation_ensure(
                user_id,
                tenant_id,
                provider=BRIDGE_DISCORD,
                scope_chat_id=_ch_id,
                scope_thread_id=None,
                model=cfg.model,
            )
            slash_reply = bridge_try_slash_command(
                prompt,
                user_id=user_id,
                provider=BRIDGE_DISCORD,
                scope_chat_id=_ch_id,
                scope_thread_id=None,
            )
            if slash_reply is not None:
                parts_sl = _chunk_text(slash_reply, limit=1900)
                await message.reply(parts_sl[0])
                for part_sl in parts_sl[1:]:
                    await message.channel.send(part_sl)
                return

            msg_list = messages_for_bridge_completion(
                user_id, conv_id, new_user_text=prompt
            )
            logger.debug(
                "discord_bridge: conversation_id=%s ctx_messages=%d (cap=%d)",
                conv_id,
                len(msg_list),
                MAX_CONTEXT_MESSAGES + 1,
            )
            work: dict[str, Any] = {
                "model": cfg.model,
                "agent_model_catalog_owned_by": cfg.catalog_owned_by,
                "messages": msg_list,
                "stream": False,
                "conversation_id": str(conv_id),
            }
            work.update(
                bridge_chat_completion_extras(
                    user_id,
                    provider=BRIDGE_DISCORD,
                    scope_chat_id=_ch_id,
                    scope_thread_id=None,
                )
            )
            role = db.user_role(user_id).lower()
            bearer_role = role if role in ("user", "admin") else None
            id_token = set_identity(tenant_id, user_id)
            text = ""
            async with message.channel.typing():
                try:
                    result = await chat_completion(work, bearer_user_role=bearer_role)
                    text = _extract_reply(result if isinstance(result, dict) else {})
                    if not conversation_append_message(
                        user_id, conv_id, role="user", content=prompt
                    ) or not conversation_append_message(
                        user_id, conv_id, role="assistant", content=text
                    ):
                        logger.warning(
                            "discord_bridge: failed to persist turn (conversation_id=%s)",
                            conv_id,
                        )
                except ValueError as e:
                    await message.reply(f"AgentLayer: {e!s:.1500}")
                    return
                except Exception as e:
                    logger.exception("discord_bridge: chat completion failed")
                    await message.reply(f"Request failed: {e!s:.500}")
                    return
                finally:
                    reset_identity(id_token)
            parts = _chunk_text(text)
            await message.reply(parts[0])
            for part in parts[1:]:
                await message.channel.send(part)

    return BridgeClient(intents=intents)


def _worker() -> None:
    global _logged_idle_reason
    while not _stop.is_set():
        cfg, idle_reason = _load_bridge_cfg_with_reason()
        if cfg is None:
            if idle_reason != _logged_idle_reason:
                logger.info(
                    "discord_bridge: not connecting to Discord — %s",
                    idle_reason,
                )
                _logged_idle_reason = idle_reason
            time.sleep(12)
            continue
        _logged_idle_reason = None
        logger.info(
            "discord_bridge: connecting to Discord (message prefix=%r, model=%s)",
            cfg.prefix,
            cfg.model,
        )
        try:
            client = _make_client(cfg)
            client.run(cfg.discord_token)
        except discord.LoginFailure:
            logger.warning(
                "discord_bridge: Discord rejected the bot token (401 / Improper token). "
                "In Developer Portal → your application → **Bot** → *Reset Token*, then paste the "
                "**bot token** (long string with dots), not the OAuth2 *Client Secret* and not the "
                "Application ID. Remove accidental spaces or quotes. Retrying in 120s."
            )
            # ✅ FIX: Immediately reload config NOW before sleeping, so user changes are picked up directly
            _load_bridge_cfg()
            time.sleep(120)
            continue
        except Exception:
            logger.exception("discord_bridge: Discord session crashed")
        time.sleep(4)


def start_background() -> None:
    global _started, _thread
    if _started:
        return
    _started = True
    _thread = threading.Thread(target=_worker, name="discord-bridge", daemon=True)
    _thread.start()
    logger.info("discord_bridge: background worker started")


def stop_background() -> None:
    _stop.set()
    logger.info("discord_bridge: stop requested (gateway may exit on next disconnect)")
