"""Deliver notifications to Telegram and Discord (opt-in, capped)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.infrastructure.platform.config import PUBLIC_BASE_URL
from apps.backend.infrastructure.notifications import notification_prefs_store
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings import operator_settings

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
    job_channel_override: bool = False,
) -> bool:
    """Return True if this notification should be sent on the given channel.

    ``job_channel_override``: the schedule job explicitly listed this channel, so
    skip the global ``*_schedules`` / ``external_failures_only`` prefs (account
    master enable + link + caps still apply).
    """
    ch = channel.strip().lower()
    kind = str(notification.get("kind") or "")
    severity = str(notification.get("severity") or "info").lower()

    if ch == "telegram":
        if not prefs.get("telegram_enabled"):
            return False
        if (
            not job_channel_override
            and kind in _SCHEDULE_KINDS
            and not prefs.get("telegram_schedules")
        ):
            return False
        if kind in _DASHBOARD_KINDS and not prefs.get("telegram_dashboard"):
            return False
    elif ch == "discord":
        if not prefs.get("discord_enabled"):
            return False
        if (
            not job_channel_override
            and kind in _SCHEDULE_KINDS
            and not prefs.get("discord_schedules")
        ):
            return False
        if kind in _DASHBOARD_KINDS and not prefs.get("discord_dashboard"):
            return False
    else:
        return False

    if kind not in _SCHEDULE_KINDS and kind not in _DASHBOARD_KINDS:
        return False

    if job_channel_override:
        return True

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


def deliver_external(
    *,
    user_id: uuid.UUID,
    notification: dict[str, Any],
    channels: frozenset[str] | None = None,
) -> None:
    """Best-effort Telegram/Discord delivery after in-app notification insert.

    When ``channels`` is set (per-job allowlist), only those external channels are
    considered and schedule prefs are treated as opted-in for this delivery.
    """
    try:
        prefs = notification_prefs_store.get_prefs(user_id=user_id)
    except Exception:
        logger.exception("notification delivery: could not load prefs user=%s", user_id)
        return

    text = _format_message(notification)
    if not text.strip():
        return

    job_override = channels is not None
    want_telegram = channels is None or "telegram" in channels
    want_discord = channels is None or "discord" in channels

    # Telegram
    if want_telegram and should_deliver_external(
        prefs=prefs,
        channel="telegram",
        notification=notification,
        job_channel_override=job_override,
    ):
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
    if want_discord and should_deliver_external(
        prefs=prefs,
        channel="discord",
        notification=notification,
        job_channel_override=job_override,
    ):
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
