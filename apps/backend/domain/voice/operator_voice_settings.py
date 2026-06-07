"""Operator voice settings — separate UPDATE (media pattern)."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.voice import voice_policy
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.operator_settings import _invalidate
from apps.backend.infrastructure.voice_catalog_providers import (
    invalidate_voice_provider_specs_cache,
    list_voice_stt_provider_specs,
    list_voice_tts_provider_specs,
    resolve_active_voice_stt_provider_id,
    resolve_active_voice_stt_spec,
    resolve_active_voice_tts_provider_id,
    resolve_active_voice_tts_spec,
    voice_role_configured,
)


def _provider_public_rows(specs: list) -> list[dict[str, str]]:
    return [
        {
            "provider_id": s.provider_id,
            "label": s.label,
            "source": s.source,
            "base_url": s.base_url,
            "role": s.role,
        }
        for s in specs
    ]


def voice_settings_public_fields() -> dict[str, Any]:
    op = voice_policy.operator_voice_row()
    stt_specs = list_voice_stt_provider_specs()
    tts_specs = list_voice_tts_provider_specs()
    stt_spec = resolve_active_voice_stt_spec()
    tts_spec = resolve_active_voice_tts_spec()
    stt_id = resolve_active_voice_stt_provider_id()
    tts_id = resolve_active_voice_tts_provider_id()
    db_stored = (str(op.get("voice_api_base_url") or "").strip() or None)
    env_stt = [s for s in stt_specs if s.source.startswith("env")]
    env_tts = [s for s in tts_specs if s.source.startswith("env")]
    base_source: str | None = (
        "env" if env_stt or env_tts else ("operator_settings" if db_stored else None)
    )

    return {
        "voice_enabled": bool(op.get("voice_enabled")),
        "voice_api_base_url": db_stored,
        "voice_api_base_source": base_source,
        "voice_api_key_configured": voice_role_configured("stt") or voice_role_configured("tts"),
        "voice_stt_provider_id": (str(op.get("voice_stt_provider_id") or "").strip() or None),
        "voice_stt_provider_id_effective": stt_id,
        "voice_stt_provider_id_source": "operator_settings" if op.get("voice_stt_provider_id") else None,
        "voice_tts_provider_id": (str(op.get("voice_tts_provider_id") or "").strip() or None),
        "voice_tts_provider_id_effective": tts_id,
        "voice_tts_provider_id_source": "operator_settings" if op.get("voice_tts_provider_id") else None,
        "voice_stt_api_base_effective": (stt_spec.base_url.rstrip("/") if stt_spec else None),
        "voice_tts_api_base_effective": (tts_spec.base_url.rstrip("/") if tts_spec else None),
        "voice_stt_providers": _provider_public_rows(stt_specs),
        "voice_tts_providers": _provider_public_rows(tts_specs),
        "voice_providers": _provider_public_rows(stt_specs + tts_specs),
        "voice_stt_model": voice_policy.voice_stt_model(),
        "voice_tts_model": voice_policy.voice_tts_model(),
        "voice_tts_voice": (str(op.get("voice_tts_voice") or "").strip() or "alloy"),
        "voice_max_seconds": int(op.get("voice_max_seconds") or 120),
        "voice_max_bytes": int(op.get("voice_max_bytes") or 10_485_760),
        "voice_bridge_telegram": bool(op.get("voice_bridge_telegram", True)),
        "voice_bridge_discord": bool(op.get("voice_bridge_discord", True)),
        "voice_realtime_enabled": bool(op.get("voice_realtime_enabled")),
        "voice_discord_vc_enabled": bool(op.get("voice_discord_vc_enabled")),
    }


def apply_voice_operator_patch(patch: dict[str, Any]) -> None:
    keys = (
        "voice_enabled",
        "voice_provider_id",
        "voice_stt_provider_id",
        "voice_tts_provider_id",
        "voice_api_base_url",
        "voice_api_key",
        "voice_stt_model",
        "voice_tts_model",
        "voice_tts_voice",
        "voice_max_seconds",
        "voice_max_bytes",
        "voice_bridge_telegram",
        "voice_bridge_discord",
        "voice_realtime_enabled",
        "voice_discord_vc_enabled",
    )
    if not any(k in patch for k in keys):
        return

    cur = voice_policy.operator_voice_row()
    out = dict(cur)

    if "voice_enabled" in patch:
        out["voice_enabled"] = bool(patch["voice_enabled"])
    if "voice_provider_id" in patch:
        v = patch["voice_provider_id"]
        out["voice_provider_id"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_stt_provider_id" in patch:
        v = patch["voice_stt_provider_id"]
        out["voice_stt_provider_id"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_tts_provider_id" in patch:
        v = patch["voice_tts_provider_id"]
        out["voice_tts_provider_id"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_api_base_url" in patch:
        v = patch["voice_api_base_url"]
        out["voice_api_base_url"] = None if v is None else (str(v).strip().rstrip("/") or None)
    if "voice_api_key" in patch:
        v = patch["voice_api_key"]
        if v is None:
            out["voice_api_key"] = None
        else:
            s = str(v).strip()
            out["voice_api_key"] = s or None
    if "voice_stt_model" in patch:
        v = patch["voice_stt_model"]
        out["voice_stt_model"] = None if v is None else (str(v).strip()[:128] or None)
    if "voice_tts_model" in patch:
        v = patch["voice_tts_model"]
        out["voice_tts_model"] = None if v is None else (str(v).strip()[:128] or None)
    if "voice_tts_voice" in patch:
        v = patch["voice_tts_voice"]
        out["voice_tts_voice"] = None if v is None else (str(v).strip()[:64] or None)
    if "voice_max_seconds" in patch:
        v = patch["voice_max_seconds"]
        if v is None:
            out["voice_max_seconds"] = None
        else:
            try:
                out["voice_max_seconds"] = max(5, min(int(v), 600))
            except (TypeError, ValueError):
                out["voice_max_seconds"] = 120
    if "voice_max_bytes" in patch:
        v = patch["voice_max_bytes"]
        if v is None:
            out["voice_max_bytes"] = None
        else:
            try:
                out["voice_max_bytes"] = max(64_000, min(int(v), 52_428_800))
            except (TypeError, ValueError):
                out["voice_max_bytes"] = 10_485_760
    if "voice_bridge_telegram" in patch:
        out["voice_bridge_telegram"] = bool(patch["voice_bridge_telegram"])
    if "voice_bridge_discord" in patch:
        out["voice_bridge_discord"] = bool(patch["voice_bridge_discord"])
    if "voice_realtime_enabled" in patch:
        out["voice_realtime_enabled"] = bool(patch["voice_realtime_enabled"])
    if "voice_discord_vc_enabled" in patch:
        out["voice_discord_vc_enabled"] = bool(patch["voice_discord_vc_enabled"])

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO operator_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
            cur.execute(
                """
                UPDATE operator_settings SET
                  voice_enabled = %s,
                  voice_provider_id = %s,
                  voice_stt_provider_id = %s,
                  voice_tts_provider_id = %s,
                  voice_api_base_url = %s,
                  voice_api_key = %s,
                  voice_stt_model = %s,
                  voice_tts_model = %s,
                  voice_tts_voice = %s,
                  voice_max_seconds = %s,
                  voice_max_bytes = %s,
                  voice_bridge_telegram = %s,
                  voice_bridge_discord = %s,
                  voice_realtime_enabled = %s,
                  voice_discord_vc_enabled = %s,
                  updated_at = now()
                WHERE id = 1
                """,
                (
                    bool(out.get("voice_enabled")),
                    out.get("voice_provider_id"),
                    out.get("voice_stt_provider_id"),
                    out.get("voice_tts_provider_id"),
                    out.get("voice_api_base_url"),
                    out.get("voice_api_key"),
                    out.get("voice_stt_model"),
                    out.get("voice_tts_model"),
                    out.get("voice_tts_voice"),
                    out.get("voice_max_seconds"),
                    out.get("voice_max_bytes"),
                    bool(out.get("voice_bridge_telegram", True)),
                    bool(out.get("voice_bridge_discord", True)),
                    bool(out.get("voice_realtime_enabled")),
                    bool(out.get("voice_discord_vc_enabled")),
                ),
            )
        conn.commit()
    _invalidate()
    invalidate_voice_provider_specs_cache()
