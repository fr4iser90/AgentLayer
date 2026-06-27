"""User notification channel preferences."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db

DEFAULT_PREFS: dict[str, bool] = {
    "telegram_enabled": False,
    "discord_enabled": False,
    "telegram_schedules": True,
    "telegram_dashboard": False,
    "discord_schedules": True,
    "discord_dashboard": False,
    "external_failures_only": True,
}

_MAX_OUTBOUND_PER_DAY = 20


def _row_to_public(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return dict(DEFAULT_PREFS)
    out = dict(DEFAULT_PREFS)
    for k in DEFAULT_PREFS:
        if k in row and row[k] is not None:
            out[k] = bool(row[k])
    return out


def get_prefs(*, user_id: uuid.UUID) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT telegram_enabled, discord_enabled,
                       telegram_schedules, telegram_dashboard,
                       discord_schedules, discord_dashboard,
                       external_failures_only, updated_at
                FROM user_notification_prefs
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
    prefs = _row_to_public(dict(row) if row else None)
    updated = row.get("updated_at") if row else None
    return {
        **prefs,
        "updated_at": updated.isoformat() if updated else None,
    }


def upsert_prefs(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    patch: dict[str, Any],
) -> dict[str, Any]:
    cur_vals = get_prefs(user_id=user_id)
    merged = {**cur_vals}
    for k in DEFAULT_PREFS:
        if k in patch and patch[k] is not None:
            merged[k] = bool(patch[k])

    if merged["telegram_enabled"] and not db.user_telegram_user_id_get(user_id):
        raise ValueError("telegram_enabled requires a linked Telegram account (Settings → Connections)")
    if merged["discord_enabled"] and not db.user_discord_user_id_get(user_id):
        raise ValueError("discord_enabled requires a linked Discord account (Settings → Connections)")

    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_notification_prefs (
                  user_id, tenant_id,
                  telegram_enabled, discord_enabled,
                  telegram_schedules, telegram_dashboard,
                  discord_schedules, discord_dashboard,
                  external_failures_only, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                  telegram_enabled = EXCLUDED.telegram_enabled,
                  discord_enabled = EXCLUDED.discord_enabled,
                  telegram_schedules = EXCLUDED.telegram_schedules,
                  telegram_dashboard = EXCLUDED.telegram_dashboard,
                  discord_schedules = EXCLUDED.discord_schedules,
                  discord_dashboard = EXCLUDED.discord_dashboard,
                  external_failures_only = EXCLUDED.external_failures_only,
                  updated_at = EXCLUDED.updated_at
                RETURNING telegram_enabled, discord_enabled,
                          telegram_schedules, telegram_dashboard,
                          discord_schedules, discord_dashboard,
                          external_failures_only, updated_at
                """,
                (
                    user_id,
                    tenant_id,
                    merged["telegram_enabled"],
                    merged["discord_enabled"],
                    merged["telegram_schedules"],
                    merged["telegram_dashboard"],
                    merged["discord_schedules"],
                    merged["discord_dashboard"],
                    merged["external_failures_only"],
                    now,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    prefs = _row_to_public(dict(row) if row else merged)
    updated = row.get("updated_at") if row else now
    return {**prefs, "updated_at": updated.isoformat() if updated else None}


def outbound_count_today(*, user_id: uuid.UUID, channel: str) -> int:
    ch = (channel or "").strip().lower()
    today = date.today()
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT outbound_count FROM notification_outbound_daily
                WHERE user_id = %s AND channel = %s AND day_utc = %s
                """,
                (user_id, ch, today),
            )
            row = cur.fetchone()
    return int(row[0]) if row else 0


def outbound_increment(*, user_id: uuid.UUID, channel: str) -> int:
    ch = (channel or "").strip().lower()
    today = date.today()
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notification_outbound_daily (user_id, channel, day_utc, outbound_count)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (user_id, channel, day_utc) DO UPDATE SET
                  outbound_count = notification_outbound_daily.outbound_count + 1
                RETURNING outbound_count
                """,
                (user_id, ch, today),
            )
            row = cur.fetchone()
        conn.commit()
    return int(row[0]) if row else 1


def outbound_cap_reached(*, user_id: uuid.UUID, channel: str) -> bool:
    return outbound_count_today(user_id=user_id, channel=channel) >= _MAX_OUTBOUND_PER_DAY
