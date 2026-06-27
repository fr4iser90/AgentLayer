from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings.operator_settings import (
    _bound_float,
    _cached_row,
    _discord_trigger_prefix_sql,
    _fetch_row,
    _invalidate,
    _rag_embedding_dim_from_row,
    _sync_single_provider_endpoint,
    _telegram_trigger_prefix_sql,
    fetch_operator_settings_row,
    resolved_agent_mode,
)
from apps.backend.infrastructure.settings.operator_settings_forms import (
    OperatorSettingsPatch,
    OperatorSettingsPayload,
)

def scheduler_jobs_worker_settings() -> tuple[bool, float]:
    """Persisted ``scheduler_jobs`` + ``project_runs`` worker: enabled, run timeout hint (30–900 s)."""
    r = fetch_operator_settings_row()
    w = bool(r.get("scheduler_jobs_worker_enabled", True))
    t = _bound_float(r.get("scheduler_jobs_ide_pidea_timeout_sec"), 300.0, 30.0, 900.0)
    return w, t


def interface_hints_public() -> dict[str, Any]:
    r = _fetch_row()
    am = r.get("agent_mode")
    am_s = am.strip().lower() if isinstance(am, str) else ""
    return {
        "discord_application_id": r.get("discord_application_id") or "",
        "telegram_application_id": r.get("telegram_application_id") or "",
        "agent_mode": am_s if am_s in ("sandbox", "host") else "",
        "agent_mode_effective": resolved_agent_mode(),
        "agent_mode_env": getattr(config, "AGENT_MODE", "sandbox"),
    }


class InterfaceHintsPayload(BaseModel):
    """Discord / Telegram application hints + agent execution class."""

    discord_application_id: str = Field(default="", max_length=128)
    telegram_application_id: str = Field(default="", max_length=128)
    agent_mode: str = Field(default="", max_length=16)


def apply_interface_hints(body: InterfaceHintsPayload) -> None:
    disc_v = body.discord_application_id.strip() or None
    tg_v = body.telegram_application_id.strip() or None
    raw_mode = body.agent_mode.strip().lower()
    mode_v: str | None = raw_mode if raw_mode in ("sandbox", "host") else None

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE operator_settings SET
                  optional_connection_key = NULL,
                  discord_application_id = %s,
                  telegram_application_id = %s,
                  agent_mode = %s,
                  updated_at = now()
                WHERE id = 1
                """,
                (disc_v, tg_v, mode_v),
            )
        conn.commit()
    _invalidate()


from apps.backend.infrastructure.settings.operator_settings_patch_writer import apply_operator_settings_patch
def apply_update(body: OperatorSettingsPayload) -> None:
    disc_v = body.discord_application_id.strip() or None
    notes_v = body.integration_notes.strip() or None

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO operator_settings (id, discord_application_id, integration_notes, updated_at)
                VALUES (1, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                  discord_application_id = EXCLUDED.discord_application_id,
                  integration_notes = EXCLUDED.integration_notes,
                  updated_at = now()
                """,
                (disc_v, notes_v),
            )
        conn.commit()
    _invalidate()
