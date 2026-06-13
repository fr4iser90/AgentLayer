"""Deliver notifications to Telegram and Discord (opt-in, capped)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.core.config import PUBLIC_BASE_URL
from apps.backend.infrastructure import notification_prefs_store
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure import operator_settings

logger = logging.getLogger(__name__)

_SCHEDULE_KINDS = frozenset({"scheduler_job_done", "scheduler_job_failed"})
_DASHBOARD_KINDS = frozenset({"dashboard_agent_update"})
_EXTERNAL_SEVERITIES = frozenset({"warning", "error", "action_required"})


def _full_link(link_path: str | None) -> str | None:
    p = (link_path or "").strip()
    if not p:
        return None
    base = (PUBLIC_BASE_URL or "").strip().rstrip("/")
    if base:
        if p.startswith("/"):
            return f"{base}{p}"
        return f"{base}/{p}"
    return p


def _format_message(notification: dict[str, Any]) -> str:
    title = str(notification.get("title") or "").strip()
    body = str(notification.get("body") or "").strip()
    link = _full_link(notification.get("link_path"))
    parts = [f"AgentLayer: {title}" if title else "AgentLayer"]
    if body:
        parts.append(body)
    if link:
        parts.append(link)
    return "\n".join(parts)[:4000]


def should_deliver_external(
    *,
    prefs: dict[str, Any],
    channel: str,
    notification: dict[str, Any],
) -> bool:
    """Return True if this notification should be sent on the given channel."""
    ch = channel.strip().lower()
    kind = str(notification.get("kind") or "")
    severity = str(notification.get("severity") or "info").lower()

    if ch == "telegram":
        if not prefs.get("telegram_enabled"):
            return False
        if kind in _SCHEDULE_KINDS and not prefs.get("telegram_schedules"):
            return False
        if kind in _DASHBOARD_KINDS and not prefs.get("telegram_dashboard"):
            return False
    elif ch == "discord":
        if not prefs.get("discord_enabled"):
            return False
        if kind in _SCHEDULE_KINDS and not prefs.get("discord_schedules"):
            return False
        if kind in _DASHBOARD_KINDS and not prefs.get("discord_dashboard"):
            return False
    else:
        return False

    if kind not in _SCHEDULE_KINDS and kind not in _DASHBOARD_KINDS:
        return False

    if prefs.get("external_failures_only"):
        if kind == "scheduler_job_failed":
            return True
        if severity in _EXTERNAL_SEVERITIES:
            return True
        return False

    return True


from plugins.tools.integrations.messaging.lib.outbound import (
    discord_send_dm,
    operator_discord_token,
    operator_telegram_token,
    telegram_send_text,
)


def deliver_external(*, user_id: uuid.UUID, notification: dict[str, Any]) -> None:
    """Best-effort Telegram/Discord delivery after in-app notification insert."""
    try:
        prefs = notification_prefs_store.get_prefs(user_id=user_id)
    except Exception:
        logger.exception("notification delivery: could not load prefs user=%s", user_id)
        return

    text = _format_message(notification)
    if not text.strip():
        return

    # Telegram
    if should_deliver_external(prefs=prefs, channel="telegram", notification=notification):
        if notification_prefs_store.outbound_cap_reached(user_id=user_id, channel="telegram"):
            logger.info("notification delivery: telegram daily cap user=%s", user_id)
        else:
            tok = operator_telegram_token()
            tg_uid = db.user_telegram_user_id_get(user_id)
            if tok and tg_uid:
                try:
                    telegram_send_text(token=tok, chat_id=int(str(tg_uid).strip()), text=text)
                    notification_prefs_store.outbound_increment(user_id=user_id, channel="telegram")
                    logger.info("notification delivery: telegram ok user=%s", user_id)
                except Exception:
                    logger.exception("notification delivery: telegram failed user=%s", user_id)

    # Discord
    if should_deliver_external(prefs=prefs, channel="discord", notification=notification):
        if notification_prefs_store.outbound_cap_reached(user_id=user_id, channel="discord"):
            logger.info("notification delivery: discord daily cap user=%s", user_id)
        else:
            tok = operator_discord_token()
            dc_uid = db.user_discord_user_id_get(user_id)
            if tok and dc_uid:
                try:
                    discord_send_dm(token=tok, recipient_id=dc_uid, text=text)
                    notification_prefs_store.outbound_increment(user_id=user_id, channel="discord")
                    logger.info("notification delivery: discord ok user=%s", user_id)
                except Exception:
                    logger.exception("notification delivery: discord failed user=%s", user_id)
