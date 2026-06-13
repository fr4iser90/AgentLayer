"""
In-process Telegram gateway: daemon thread inside the same process as Uvicorn.

Configuration from ``operator_settings`` (Admin → Interfaces). Text messages matching the
prefix are handled only for Telegram user ids linked in ``users.telegram_user_id``; chat runs
via :func:`apps.domain.agent.chat_completion` in-process. Same identity semantics as Discord.

**Context:** Each Telegram chat (and forum thread, if any) keeps a rolling conversation in
Postgres (``bridge_agent_sessions`` → ``chat_messages``), same pattern as Discord — unlike the
web UI, which sends full ``messages[]`` from the client on each turn.

**New bridges:** Copy the ``bridge_agent_conversation_ensure`` → ``messages_for_bridge_completion``
→ ``chat_completion`` → ``conversation_append_message`` flow; see ``integrations/bridges/README.md``.

**Groups:** With BotFather ``/setprivacy`` → *Disable*, the bot sees all messages (like Discord
channels). Otherwise only commands and mentions are delivered to the bot.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from apps.backend.domain.agent import chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure.conversations_db import conversation_append_message
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.bridge_agent_session import (
    BRIDGE_TELEGRAM,
    MAX_CONTEXT_MESSAGES,
    bridge_agent_conversation_ensure,
    bridge_agent_session_reset,
    bridge_chat_completion_extras,
    bridge_try_slash_command,
    messages_for_bridge_completion,
)

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None
_started = False
_logged_idle_reason: str | None = None


@dataclass
class _BridgeCfg:
    token: str
    model: str
    catalog_owned_by: str
    prefix: str


def _chunk_text(text: str, limit: int = 4000) -> list[str]:
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


def _normalize_bot_token(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return "".join(s.split())


def _load_bridge_cfg_with_reason() -> tuple[_BridgeCfg | None, str]:
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT telegram_bot_enabled, telegram_bot_token,
                           telegram_trigger_prefix, telegram_chat_model
                    FROM operator_settings WHERE id = 1
                    """
                )
                row = cur.fetchone()
    except Exception:
        logger.exception("telegram_bridge: could not read operator_settings (migrations applied?)")
        return None, "database error (see log above)"
    if not row:
        return None, "no operator_settings row for id=1"
    enabled, ttoken, trigger, cmodel = row
    if not enabled:
        return None, "telegram_bot_enabled is false (Admin → Interfaces → Telegram)"
    tok = _normalize_bot_token(str(ttoken) if ttoken is not None else "")
    if not tok:
        return None, "telegram_bot_token is empty (paste token in Admin → Interfaces → Telegram)"
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
            token=tok,
            model=str(llm["model"]),
            catalog_owned_by=str(llm["agent_model_catalog_owned_by"]),
            prefix=prefix,
        ),
        "",
    )


async def _run_polling_session(cfg: _BridgeCfg) -> None:
    from telegram.constants import ChatAction
    from telegram.error import TelegramError
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    async def cmd_start(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if msg:
            await msg.reply_text(
                "AgentLayer: link your numeric Telegram user id in the web app "
                "(Settings → Connections), then send text with the configured prefix "
                "(or any message if prefix is empty). "
                "Context is kept across messages; `/clear` clears chat history (workspace binding stays). "
                "Send voice notes when Voice is enabled (Settings → Voice). "
                "Use `/workspace list` / `/workspace bind <uuid>` for repo tools; `/agent` to pick an agent."
            )

    async def on_text(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        user = update.effective_user
        if not msg or not user or user.is_bot or not (msg.text or "").strip():
            return
        chat = msg.chat
        text = (msg.text or "").strip()
        if cfg.prefix:
            if not text.startswith(cfg.prefix):
                return
            prompt = text[len(cfg.prefix) :].strip()
        else:
            prompt = text
        if not prompt:
            if cfg.prefix:
                await msg.reply_text(
                    f"Add your question after `{cfg.prefix.strip()}`, e.g. `{cfg.prefix.strip()}What is 2+2?`"
                )
            return
        author_id = str(user.id)
        linked = db.user_id_tenant_for_telegram_global(author_id)
        if linked is None:
            await msg.reply_text(
                "Your Telegram account is not linked in AgentLayer (or the link is ambiguous). "
                "Open the web app → Settings → Connections → save your numeric Telegram user id."
            )
            return
        user_id, tenant_id = linked
        thread_kw: dict[str, Any] = {}
        if getattr(msg, "message_thread_id", None) is not None:
            thread_kw["message_thread_id"] = msg.message_thread_id

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
                provider=BRIDGE_TELEGRAM,
                scope_chat_id=int(chat.id),
                scope_thread_id=getattr(msg, "message_thread_id", None),
                model=cfg.model,
            )
            ok = bridge_agent_session_reset(
                user_id,
                provider=BRIDGE_TELEGRAM,
                scope_chat_id=int(chat.id),
                scope_thread_id=getattr(msg, "message_thread_id", None),
            )
            await msg.reply_text(
                "Konversationsverlauf für diesen Chat geleert (Workspace-/Agent-Bindung bleibt)."
                if ok
                else "Es war kein gespeicherter Verlauf vorhanden.",
                **thread_kw,
            )
            return

        logger.info(
            "telegram_bridge: chat request (telegram_user_id=%s, agentlayer_user=%s, model=%s)",
            author_id,
            user_id,
            cfg.model,
        )
        # Rolling DB context for this Telegram chat; new gateways: same call with provider="your_id".
        conv_id = bridge_agent_conversation_ensure(
            user_id,
            tenant_id,
            provider=BRIDGE_TELEGRAM,
            scope_chat_id=int(chat.id),
            scope_thread_id=getattr(msg, "message_thread_id", None),
            model=cfg.model,
        )
        slash_reply = bridge_try_slash_command(
            prompt,
            user_id=user_id,
            provider=BRIDGE_TELEGRAM,
            scope_chat_id=int(chat.id),
            scope_thread_id=getattr(msg, "message_thread_id", None),
        )
        if slash_reply is not None:
            parts_sl = _chunk_text(slash_reply, limit=3500)
            await msg.reply_text(parts_sl[0], **thread_kw)
            for extra_sl in parts_sl[1:]:
                await context.bot.send_message(chat_id=chat.id, text=extra_sl, **thread_kw)
            return

        msg_list = messages_for_bridge_completion(
            user_id, conv_id, new_user_text=prompt
        )
        logger.debug(
            "telegram_bridge: conversation_id=%s ctx_messages=%d (cap=%d)",
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
                provider=BRIDGE_TELEGRAM,
                scope_chat_id=int(chat.id),
                scope_thread_id=getattr(msg, "message_thread_id", None),
            )
        )
        role = db.user_role(user_id).lower()
        bearer_role = role if role in ("user", "admin") else None
        id_token = set_identity(tenant_id, user_id)

        async def _typing_heartbeat() -> None:
            """Telegram typing expires after ~5s; refresh like Discord's sustained typing."""
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
                logger.debug("telegram_bridge: typing heartbeat failed", exc_info=True)

        typing_task = asyncio.create_task(_typing_heartbeat())
        try:
            try:
                result = await chat_completion(work, bearer_user_role=bearer_role)
                reply_text = _extract_reply(result if isinstance(result, dict) else {})
                if not conversation_append_message(
                    user_id, conv_id, role="user", content=prompt
                ) or not conversation_append_message(
                    user_id, conv_id, role="assistant", content=reply_text
                ):
                    logger.warning(
                        "telegram_bridge: failed to persist turn (conversation_id=%s)",
                        conv_id,
                    )
            except ValueError as e:
                try:
                    await msg.reply_text(f"AgentLayer: {e!s:.1500}", **thread_kw)
                except TelegramError as te:
                    logger.exception("telegram_bridge: reply after ValueError failed: %s", te)
                return
            except Exception as e:
                logger.exception("telegram_bridge: chat completion failed")
                try:
                    await msg.reply_text(f"Request failed: {e!s:.500}", **thread_kw)
                except TelegramError as te:
                    logger.exception("telegram_bridge: reply after chat error failed: %s", te)
                return
            parts = _chunk_text(reply_text)
            try:
                await msg.reply_text(parts[0], **thread_kw)
                for part in parts[1:]:
                    await context.bot.send_message(chat_id=chat.id, text=part, **thread_kw)
                logger.info(
                    "telegram_bridge: sent reply (%d chunk(s), ~%d chars)",
                    len(parts),
                    sum(len(p) for p in parts),
                )
            except TelegramError as e:
                logger.exception(
                    "telegram_bridge: Telegram rejected outgoing message (reply or chunk): %s",
                    e,
                )
                try:
                    await msg.reply_text(
                        f"AgentLayer: could not send the reply via Telegram ({e!s:.200})",
                        **thread_kw,
                    )
                except TelegramError:
                    logger.exception("telegram_bridge: could not send error fallback to user")
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
            reset_identity(id_token)

    application = (
        Application.builder()
        .token(cfg.token)
        .concurrent_updates(True)
        .build()
    )
    async def on_photo(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        user = update.effective_user
        if not msg or not user or user.is_bot or not msg.photo:
            return
        author_id = str(user.id)
        linked = db.user_id_tenant_for_telegram_global(author_id)
        if linked is None:
            await msg.reply_text(
                "Telegram ist nicht verknüpft. Web-App → Einstellungen → Verbindungen → Telegram-User-ID speichern."
            )
            return
        user_id, tenant_id = linked
        thread_kw: dict[str, Any] = {}
        if getattr(msg, "message_thread_id", None) is not None:
            thread_kw["message_thread_id"] = msg.message_thread_id

        from plugins.tools.integrations.messaging.lib.telegram_dashboard_upload import (
            list_telegram_upload_targets,
            upload_image_bytes,
        )

        targets = list_telegram_upload_targets(user_id)
        if not targets:
            await msg.reply_text(
                "📷 Kein bearbeitbares Dashboard mit Foto-Album gefunden. "
                "Du brauchst Bearbeitungs-Recht (z. B. friends.shares mit permission=edit).",
                **thread_kw,
            )
            return

        caption = (msg.caption or "").strip()
        target: dict[str, Any] | None = None
        if len(targets) == 1:
            target = targets[0]
        else:
            for cand in targets:
                if cand.get("dashboard_id") and str(cand["dashboard_id"]) in caption:
                    target = cand
                    break
            if target is None:
                lines = "\n".join(
                    f"• {t.get('title') or 'Dashboard'} — `{t.get('dashboard_id')}`"
                    for t in targets[:6]
                )
                await msg.reply_text(
                    "Mehrere Upload-Ziele aktiv. Optional Dashboard-ID in die Bildunterschrift setzen:\n"
                    f"{lines}",
                    **thread_kw,
                )
                return

        try:
            photo = msg.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            raw = await tg_file.download_as_bytearray()
            image_bytes = bytes(raw)
            result = upload_image_bytes(
                uploader_user_id=user_id,
                tenant_id=tenant_id,
                dashboard_id=uuid.UUID(str(target["dashboard_id"])),
                image_bytes=image_bytes,
                original_name="telegram.jpg",
                album_index=int(target.get("album_index") or 0),
                caption=caption,
            )
            await msg.reply_text(
                f"✅ Foto hochgeladen ({result.get('photos_count')} im Album).",
                **thread_kw,
            )
        except Exception as e:
            logger.exception("telegram_bridge: photo upload failed user=%s", user_id)
            await msg.reply_text(f"Upload fehlgeschlagen: {e!s:.400}", **thread_kw)

    async def on_voice(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        user = update.effective_user
        if not msg or not user or user.is_bot or not msg.voice:
            return
        author_id = str(user.id)
        linked = db.user_id_tenant_for_telegram_global(author_id)
        if linked is None:
            await msg.reply_text(
                "Your Telegram account is not linked in AgentLayer. "
                "Open the web app → Settings → Connections → save your numeric Telegram user id."
            )
            return
        user_id, tenant_id = linked
        from apps.backend.domain.voice import stt, voice_policy
        from apps.backend.domain.voice.bridge_reply import send_telegram_agent_reply
        from apps.backend.infrastructure.bridge_agent_turn import run_bridge_agent_turn

        if not voice_policy.effective_voice_input(user_id=user_id, channel="telegram"):
            await msg.reply_text(
                "Voice input is disabled. Ask your admin to enable Voice, then "
                "Settings → Voice in the web app."
            )
            return

        thread_kw: dict[str, Any] = {}
        if getattr(msg, "message_thread_id", None) is not None:
            thread_kw["message_thread_id"] = msg.message_thread_id
        chat = msg.chat

        try:
            tg_file = await context.bot.get_file(msg.voice.file_id)
            raw = await tg_file.download_as_bytearray()
            audio_bytes = bytes(raw)
        except Exception as e:
            logger.exception("telegram_bridge: voice download failed")
            await msg.reply_text(f"Could not download voice message: {e!s:.300}", **thread_kw)
            return

        lang = voice_policy.effective_stt_language(user_id)
        try:
            stt_result = stt.transcribe_audio(audio_bytes, mime="audio/ogg", language=lang)
        except ValueError as e:
            await msg.reply_text(f"Could not transcribe voice: {e!s:.400}", **thread_kw)
            return

        prompt = stt_result.transcript
        logger.info(
            "telegram_bridge: voice request (telegram_user_id=%s, agentlayer_user=%s, chars=%d)",
            author_id,
            user_id,
            len(prompt),
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
                logger.debug("telegram_bridge: voice typing heartbeat failed", exc_info=True)

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
                logger.exception("telegram_bridge: voice chat completion failed")
                await msg.reply_text(f"Request failed: {e!s:.500}", **thread_kw)
                return
            await send_telegram_agent_reply(
                msg=msg,
                context=context,
                chat=chat,
                thread_kw=thread_kw,
                user_id=user_id,
                reply_text=reply_text,
                chunk_text_fn=_chunk_text,
            )
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.VOICE, on_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    async def _ptb_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        err = context.error
        logger.exception("telegram_bridge: PTB error handler", exc_info=err)

    application.add_error_handler(_ptb_error_handler)

    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        allowed_updates=["message"],
        drop_pending_updates=True,
    )
    try:
        while not _stop.is_set():
            await asyncio.sleep(0.4)
    finally:
        try:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
        except Exception:
            logger.debug("telegram_bridge: shutdown", exc_info=True)


def _async_worker_session(cfg: _BridgeCfg) -> None:
    from telegram.error import InvalidToken

    try:
        asyncio.run(_run_polling_session(cfg))
    except InvalidToken:
        logger.warning(
            "telegram_bridge: Telegram rejected the bot token (401 / invalid). "
            "Paste the token from @BotFather (format `123456:ABC...`). Retrying in 120s."
        )
        # ✅ FIX: Immediately reload config NOW before sleeping, so user changes are picked up directly
        _load_bridge_cfg_with_reason()
        time.sleep(120)
    except Exception:
        logger.exception("telegram_bridge: session crashed")
        time.sleep(4)


def _worker() -> None:
    global _logged_idle_reason
    while not _stop.is_set():
        cfg, idle_reason = _load_bridge_cfg_with_reason()
        if cfg is None:
            if idle_reason != _logged_idle_reason:
                logger.info(
                    "telegram_bridge: not connecting to Telegram — %s",
                    idle_reason,
                )
                _logged_idle_reason = idle_reason
            time.sleep(12)
            continue
        _logged_idle_reason = None
        logger.info(
            "telegram_bridge: connecting to Telegram (message prefix=%r, model=%s)",
            cfg.prefix,
            cfg.model,
        )
        _async_worker_session(cfg)


def start_background() -> None:
    global _started, _thread
    if _started:
        return
    _started = True
    _thread = threading.Thread(target=_worker, name="telegram-bridge", daemon=True)
    _thread.start()
    logger.info("telegram_bridge: background worker started")


def stop_background() -> None:
    _stop.set()
    logger.info("telegram_bridge: stop requested (polling may exit on next wake)")
