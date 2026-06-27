"""DB persistence for benchmark harness global defaults and per-model overrides."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db

_VALID_PRESETS = frozenset({"observability", "chat_parity"})


def _ser(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _normalize_preset(value: Any) -> str:
    preset = str(value or "observability").strip().lower()
    if preset not in _VALID_PRESETS:
        raise ValueError("harness_preset must be observability or chat_parity")
    return preset


def _public_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = _ser(dict(row))
    out["scope"] = "global" if not out.get("catalog_owned_by") and not out.get("model") else "model"
    return out


def default_global_config() -> dict[str, Any]:
    return {
        "harness_preset": "observability",
        "max_tool_rounds_override": None,
        "scenario_timeout_sec": None,
        "capture_timeline": None,
        "stream_llm": None,
        "notes": None,
    }


def get_global(tenant_id: int) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, catalog_owned_by, model, label,
                       harness_preset, max_tool_rounds_override, scenario_timeout_sec,
                       capture_timeline, stream_llm, notes, updated_at, updated_by
                FROM benchmark_harness_config
                WHERE tenant_id = %s
                  AND catalog_owned_by IS NULL
                  AND model IS NULL
                LIMIT 1
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
    if not row:
        return default_global_config()
    out = _public_row(dict(row)) or {}
    return {
        "harness_preset": out.get("harness_preset") or "observability",
        "max_tool_rounds_override": out.get("max_tool_rounds_override"),
        "scenario_timeout_sec": out.get("scenario_timeout_sec"),
        "capture_timeline": out.get("capture_timeline"),
        "stream_llm": out.get("stream_llm"),
        "notes": out.get("notes"),
        "updated_at": out.get("updated_at"),
        "updated_by": out.get("updated_by"),
    }


def set_global(
    tenant_id: int,
    *,
    harness_preset: str,
    max_tool_rounds_override: int | None = None,
    scenario_timeout_sec: float | None = None,
    capture_timeline: bool | None = None,
    stream_llm: bool | None = None,
    notes: str | None = None,
    user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    preset = _normalize_preset(harness_preset)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id FROM benchmark_harness_config
                WHERE tenant_id = %s
                  AND catalog_owned_by IS NULL
                  AND model IS NULL
                LIMIT 1
                """,
                (tenant_id,),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE benchmark_harness_config
                    SET harness_preset = %s,
                        max_tool_rounds_override = %s,
                        scenario_timeout_sec = %s,
                        capture_timeline = %s,
                        stream_llm = %s,
                        notes = %s,
                        updated_at = now(),
                        updated_by = %s
                    WHERE id = %s
                    """,
                    (
                        preset,
                        max_tool_rounds_override,
                        scenario_timeout_sec,
                        capture_timeline,
                        stream_llm,
                        notes,
                        user_id,
                        existing["id"],
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO benchmark_harness_config (
                      tenant_id, catalog_owned_by, model, harness_preset,
                      max_tool_rounds_override, scenario_timeout_sec,
                      capture_timeline, stream_llm, notes, updated_by
                    )
                    VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tenant_id,
                        preset,
                        max_tool_rounds_override,
                        scenario_timeout_sec,
                        capture_timeline,
                        stream_llm,
                        notes,
                        user_id,
                    ),
                )
    return get_global(tenant_id)


def list_overrides(tenant_id: int) -> list[dict[str, Any]]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, catalog_owned_by, model, label,
                       harness_preset, max_tool_rounds_override, scenario_timeout_sec,
                       capture_timeline, stream_llm, notes, updated_at, updated_by
                FROM benchmark_harness_config
                WHERE tenant_id = %s
                  AND (catalog_owned_by IS NOT NULL OR model IS NOT NULL)
                ORDER BY catalog_owned_by NULLS LAST, model NULLS LAST, label NULLS LAST
                """,
                (tenant_id,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_public_row(r) for r in rows if r]


def get_override(override_id: uuid.UUID, *, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, catalog_owned_by, model, label,
                       harness_preset, max_tool_rounds_override, scenario_timeout_sec,
                       capture_timeline, stream_llm, notes, updated_at, updated_by
                FROM benchmark_harness_config
                WHERE id = %s AND tenant_id = %s
                  AND (catalog_owned_by IS NOT NULL OR model IS NOT NULL)
                """,
                (override_id, tenant_id),
            )
            row = cur.fetchone()
    return _public_row(dict(row)) if row else None


def upsert_override(
    tenant_id: int,
    *,
    catalog_owned_by: str,
    model: str | None = None,
    label: str | None = None,
    harness_preset: str,
    max_tool_rounds_override: int | None = None,
    scenario_timeout_sec: float | None = None,
    capture_timeline: bool | None = None,
    stream_llm: bool | None = None,
    notes: str | None = None,
    user_id: uuid.UUID | None = None,
    override_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    catalog = str(catalog_owned_by or "").strip()
    if not catalog:
        raise ValueError("catalog_owned_by is required for model overrides")
    model_val = str(model).strip() if model else None
    if model_val == "":
        model_val = None
    preset = _normalize_preset(harness_preset)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if override_id is not None:
                cur.execute(
                    """
                    UPDATE benchmark_harness_config
                    SET catalog_owned_by = %s,
                        model = %s,
                        label = %s,
                        harness_preset = %s,
                        max_tool_rounds_override = %s,
                        scenario_timeout_sec = %s,
                        capture_timeline = %s,
                        stream_llm = %s,
                        notes = %s,
                        updated_at = now(),
                        updated_by = %s
                    WHERE id = %s AND tenant_id = %s
                      AND (catalog_owned_by IS NOT NULL OR model IS NOT NULL)
                    RETURNING id
                    """,
                    (
                        catalog,
                        model_val,
                        label,
                        preset,
                        max_tool_rounds_override,
                        scenario_timeout_sec,
                        capture_timeline,
                        stream_llm,
                        notes,
                        user_id,
                        override_id,
                        tenant_id,
                    ),
                )
                if not cur.fetchone():
                    raise LookupError("harness override not found")
            else:
                cur.execute(
                    """
                    SELECT id FROM benchmark_harness_config
                    WHERE tenant_id = %s
                      AND COALESCE(catalog_owned_by, '') = %s
                      AND COALESCE(model, '') = COALESCE(%s, '')
                    LIMIT 1
                    """,
                    (tenant_id, catalog, model_val),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """
                        UPDATE benchmark_harness_config
                        SET label = %s,
                            harness_preset = %s,
                            max_tool_rounds_override = %s,
                            scenario_timeout_sec = %s,
                            capture_timeline = %s,
                            stream_llm = %s,
                            notes = %s,
                            updated_at = now(),
                            updated_by = %s
                        WHERE id = %s
                        RETURNING id
                        """,
                        (
                            label,
                            preset,
                            max_tool_rounds_override,
                            scenario_timeout_sec,
                            capture_timeline,
                            stream_llm,
                            notes,
                            user_id,
                            existing["id"],
                        ),
                    )
                    override_id = uuid.UUID(str(cur.fetchone()["id"]))
                else:
                    cur.execute(
                        """
                        INSERT INTO benchmark_harness_config (
                          tenant_id, catalog_owned_by, model, label, harness_preset,
                          max_tool_rounds_override, scenario_timeout_sec,
                          capture_timeline, stream_llm, notes, updated_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            tenant_id,
                            catalog,
                            model_val,
                            label,
                            preset,
                            max_tool_rounds_override,
                            scenario_timeout_sec,
                            capture_timeline,
                            stream_llm,
                            notes,
                            user_id,
                        ),
                    )
                    override_id = uuid.UUID(str(cur.fetchone()["id"]))
    row = get_override(override_id, tenant_id=tenant_id)
    if not row:
        raise RuntimeError("failed to load harness override after upsert")
    return row


def delete_override(override_id: uuid.UUID, *, tenant_id: int) -> bool:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM benchmark_harness_config
                WHERE id = %s AND tenant_id = %s
                  AND (catalog_owned_by IS NOT NULL OR model IS NOT NULL)
                """,
                (override_id, tenant_id),
            )
            return cur.rowcount > 0
