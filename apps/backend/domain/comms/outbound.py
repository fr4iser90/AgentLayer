"""Outbound Telegram/Discord messages via operator bots (shared with notifications)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from apps.backend.infrastructure import notification_prefs_store
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure import operator_settings

logger = logging.getLogger(__name__)


class OutboundDeliveryError(Exception):
    pass


def operator_telegram_token() -> str | None:
    row = operator_settings.fetch_operator_settings_row()
    if not row.get("telegram_bot_enabled"):
        return None
    tok = (row.get("telegram_bot_token") or "").strip()
    return tok or None


def operator_discord_token() -> str | None:
    row = operator_settings.fetch_operator_settings_row()
    if not row.get("discord_bot_enabled"):
        return None
    tok = (row.get("discord_bot_token") or "").strip()
    return tok or None


def telegram_send_text(*, token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, json={"chat_id": chat_id, "text": text[:4000]})
        r.raise_for_status()


def discord_send_dm(*, token: str, recipient_id: str, text: str) -> None:
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=45.0) as client:
        r = client.post(
            "https://discord.com/api/v10/users/@me/channels",
            headers=headers,
            json={"recipient_id": str(recipient_id).strip()},
        )
        r.raise_for_status()
        ch = r.json()
        channel_id = ch.get("id") if isinstance(ch, dict) else None
        if not channel_id:
            raise OutboundDeliveryError("discord DM channel create returned no id")
        msg = client.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers=headers,
            json={"content": text[:2000]},
        )
        msg.raise_for_status()


def send_telegram_to_user(
    *,
    sender_user_id: uuid.UUID,
    recipient_user_id: uuid.UUID,
    text: str,
    skip_cap: bool = False,
) -> dict[str, Any]:
    tok = operator_telegram_token()
    if not tok:
        raise OutboundDeliveryError(
            "Telegram bot not enabled — enable in Admin → Interfaces → Telegram"
        )
    tg_uid = db.user_telegram_user_id_get(recipient_user_id)
    if not tg_uid:
        raise OutboundDeliveryError(
            "Recipient has no linked Telegram user id (Settings → Connections)"
        )
    if not skip_cap and notification_prefs_store.outbound_cap_reached(
        user_id=sender_user_id, channel="telegram"
    ):
        raise OutboundDeliveryError("Daily Telegram outbound cap reached for sender")
    telegram_send_text(token=tok, chat_id=int(str(tg_uid).strip()), text=text)
    if not skip_cap:
        notification_prefs_store.outbound_increment(user_id=sender_user_id, channel="telegram")
    return {
        "ok": True,
        "channel": "telegram",
        "recipient_user_id": str(recipient_user_id),
        "telegram_user_id": str(tg_uid),
    }


def send_discord_to_user(
    *,
    sender_user_id: uuid.UUID,
    recipient_user_id: uuid.UUID,
    text: str,
    skip_cap: bool = False,
) -> dict[str, Any]:
    tok = operator_discord_token()
    if not tok:
        raise OutboundDeliveryError(
            "Discord bot not enabled — enable in Admin → Interfaces → Discord"
        )
    dc_uid = db.user_discord_user_id_get(recipient_user_id)
    if not dc_uid:
        raise OutboundDeliveryError(
            "Recipient has no linked Discord user id (Settings → Connections)"
        )
    if not skip_cap and notification_prefs_store.outbound_cap_reached(
        user_id=sender_user_id, channel="discord"
    ):
        raise OutboundDeliveryError("Daily Discord outbound cap reached for sender")
    discord_send_dm(token=tok, recipient_id=dc_uid, text=text)
    if not skip_cap:
        notification_prefs_store.outbound_increment(user_id=sender_user_id, channel="discord")
    return {
        "ok": True,
        "channel": "discord",
        "recipient_user_id": str(recipient_user_id),
        "discord_user_id": str(dc_uid),
    }
