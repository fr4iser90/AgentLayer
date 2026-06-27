"""DB persistence for agent config overrides, changelog, sessions, experiments, reviews."""

from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db


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


def list_overrides(tenant_id: int) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT knob_id, value_json, updated_at
                FROM agent_config_overrides
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    out: dict[str, Any] = {}
    for r in rows:
        kid = str(r.get("knob_id") or "")
        if kid:
            out[kid] = r.get("value_json")
    return out


def get_override(tenant_id: int, knob_id: str) -> Any | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT value_json FROM agent_config_overrides
                WHERE tenant_id = %s AND knob_id = %s
                """,
                (tenant_id, knob_id),
            )
            row = cur.fetchone()
    if not row:
        return None
    return row.get("value_json")


def set_override(
    tenant_id: int,
    knob_id: str,
    value: Any,
    *,
    user_id: uuid.UUID | None,
) -> None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_config_overrides (tenant_id, knob_id, value_json, updated_by)
                VALUES (%s, %s, %s::jsonb, %s)
                ON CONFLICT (tenant_id, knob_id) DO UPDATE SET
                  value_json = EXCLUDED.value_json,
                  updated_at = now(),
                  updated_by = EXCLUDED.updated_by
                """,
                (tenant_id, knob_id, json.dumps(value), user_id),
            )
        conn.commit()


def delete_override(tenant_id: int, knob_id: str) -> None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM agent_config_overrides WHERE tenant_id = %s AND knob_id = %s",
                (tenant_id, knob_id),
            )
        conn.commit()


def list_model_overrides(tenant_id: int) -> list[dict[str, Any]]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, catalog_owned_by, model, label, knobs_json, updated_at, updated_by
                FROM agent_config_model_overrides
                WHERE tenant_id = %s
                ORDER BY catalog_owned_by, model NULLS FIRST, updated_at DESC
                """,
                (tenant_id,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(r) for r in rows]


def get_model_override(override_id: uuid.UUID, *, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, catalog_owned_by, model, label, knobs_json, updated_at, updated_by
                FROM agent_config_model_overrides
                WHERE id = %s AND tenant_id = %s
                """,
                (override_id, tenant_id),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def find_model_override_row(
    tenant_id: int,
    *,
    catalog_owned_by: str,
    model: str | None,
) -> dict[str, Any] | None:
    catalog = str(catalog_owned_by or "").strip()
    if not catalog:
        return None
    model_key = str(model or "").strip()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, catalog_owned_by, model, label, knobs_json, updated_at, updated_by
                FROM agent_config_model_overrides
                WHERE tenant_id = %s AND catalog_owned_by = %s AND model = %s
                """,
                (tenant_id, catalog, model_key),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def upsert_model_override(
    tenant_id: int,
    *,
    catalog_owned_by: str,
    model: str | None,
    label: str | None,
    knobs: dict[str, Any],
    user_id: uuid.UUID | None,
    override_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    catalog = str(catalog_owned_by or "").strip()
    if not catalog:
        raise ValueError("catalog_owned_by required")
    model_key = str(model or "").strip()
    knobs_json = json.dumps(knobs if isinstance(knobs, dict) else {})
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if override_id is not None:
                cur.execute(
                    """
                    UPDATE agent_config_model_overrides
                    SET catalog_owned_by = %s,
                        model = %s,
                        label = %s,
                        knobs_json = %s::jsonb,
                        updated_at = now(),
                        updated_by = %s
                    WHERE id = %s AND tenant_id = %s
                    RETURNING id, tenant_id, catalog_owned_by, model, label, knobs_json, updated_at, updated_by
                    """,
                    (catalog, model_key, label, knobs_json, user_id, override_id, tenant_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO agent_config_model_overrides (
                      tenant_id, catalog_owned_by, model, label, knobs_json, updated_by
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (tenant_id, catalog_owned_by, model) DO UPDATE SET
                      label = COALESCE(EXCLUDED.label, agent_config_model_overrides.label),
                      knobs_json = EXCLUDED.knobs_json,
                      updated_at = now(),
                      updated_by = EXCLUDED.updated_by
                    RETURNING id, tenant_id, catalog_owned_by, model, label, knobs_json, updated_at, updated_by
                    """,
                    (tenant_id, catalog, model_key, label, knobs_json, user_id),
                )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("model override upsert failed")
    return _ser(dict(row))


def delete_model_override(override_id: uuid.UUID, *, tenant_id: int) -> bool:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM agent_config_model_overrides WHERE id = %s AND tenant_id = %s",
                (override_id, tenant_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def append_changelog(
    *,
    tenant_id: int,
    actor_type: str,
    actor_user_id: uuid.UUID | None,
    actor_agent_id: str | None,
    session_id: uuid.UUID | None,
    experiment_id: uuid.UUID | None,
    hypothesis: str | None,
    patches: list[dict[str, Any]],
    fingerprint_before: str | None,
    fingerprint_after: str | None,
) -> uuid.UUID:
    event_id = uuid.uuid4()
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_config_changelog (
                  id, tenant_id, actor_type, actor_user_id, actor_agent_id,
                  session_id, experiment_id, hypothesis, patches_json,
                  fingerprint_before, fingerprint_after
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    event_id,
                    tenant_id,
                    actor_type,
                    actor_user_id,
                    actor_agent_id,
                    session_id,
                    experiment_id,
                    hypothesis,
                    json.dumps(patches),
                    fingerprint_before,
                    fingerprint_after,
                ),
            )
        conn.commit()
    return event_id


def list_changelog(
    tenant_id: int,
    *,
    limit: int = 50,
    session_id: uuid.UUID | None = None,
    actor_type: str | None = None,
) -> list[dict[str, Any]]:
    lim = max(1, min(500, int(limit)))
    params: list[Any] = [tenant_id]
    where = "tenant_id = %s"
    if session_id is not None:
        where += " AND session_id = %s"
        params.append(session_id)
    if actor_type:
        where += " AND actor_type = %s"
        params.append(actor_type.strip())
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM agent_config_changelog
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(r) for r in rows]


def create_session(
    *,
    tenant_id: int,
    label: str,
    hypothesis: str | None,
    cohort_label: str,
    baseline_fingerprint: str | None,
) -> dict[str, Any]:
    sid = uuid.uuid4()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO agent_config_sessions (
                  id, tenant_id, label, hypothesis, cohort_label,
                  baseline_fingerprint, current_fingerprint
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (sid, tenant_id, label, hypothesis, cohort_label, baseline_fingerprint, baseline_fingerprint),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _ser(row)


def get_session(session_id: uuid.UUID, *, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM agent_config_sessions WHERE id = %s AND tenant_id = %s",
                (session_id, tenant_id),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def list_sessions(tenant_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(200, int(limit)))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM agent_config_sessions
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, lim),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(r) for r in rows]


def patch_session_metadata(
    session_id: uuid.UUID,
    *,
    tenant_id: int,
    label: str | None = None,
    hypothesis: str | None = None,
) -> dict[str, Any] | None:
    sets: list[str] = []
    params: list[Any] = []
    if label is not None:
        sets.append("label = %s")
        params.append(label)
    if hypothesis is not None:
        sets.append("hypothesis = %s")
        params.append(hypothesis)
    if not sets:
        return get_session(session_id, tenant_id=tenant_id)
    params.extend([session_id, tenant_id])
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                UPDATE agent_config_sessions SET {", ".join(sets)}
                WHERE id = %s AND tenant_id = %s
                RETURNING *
                """,
                tuple(params),
            )
            row = cur.fetchone()
        conn.commit()
    return _ser(dict(row)) if row else None


def close_session(session_id: uuid.UUID, *, tenant_id: int, current_fingerprint: str | None) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE agent_config_sessions
                SET status = 'closed', closed_at = now(), current_fingerprint = %s
                WHERE id = %s AND tenant_id = %s
                RETURNING *
                """,
                (current_fingerprint, session_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _ser(dict(row)) if row else None


def append_session_run(session_id: uuid.UUID, *, tenant_id: int, run_id: uuid.UUID) -> None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_config_sessions
                SET run_ids_json = run_ids_json || %s::jsonb,
                    current_fingerprint = COALESCE(current_fingerprint, %s)
                WHERE id = %s AND tenant_id = %s
                """,
                (json.dumps([str(run_id)]), None, session_id, tenant_id),
            )
        conn.commit()


def create_experiment(
    *,
    tenant_id: int,
    label: str,
    hypothesis: str | None,
    session_id: uuid.UUID | None,
    fingerprint_at_start: str | None,
    suite_preset: str | None,
    harness_preset: str | None,
    pending_patches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    eid = uuid.uuid4()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO benchmark_experiments (
                  id, tenant_id, label, hypothesis, session_id, fingerprint_at_start,
                  suite_preset, harness_preset, pending_patches_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING *
                """,
                (
                    eid,
                    tenant_id,
                    label,
                    hypothesis,
                    session_id,
                    fingerprint_at_start,
                    suite_preset,
                    harness_preset,
                    json.dumps(pending_patches or []),
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _ser(row)


def get_experiment(experiment_id: uuid.UUID, *, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM benchmark_experiments WHERE id = %s AND tenant_id = %s",
                (experiment_id, tenant_id),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def list_experiments(tenant_id: int, *, limit: int = 50, session_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    lim = max(1, min(200, int(limit)))
    params: list[Any] = [tenant_id]
    where = "tenant_id = %s"
    if session_id is not None:
        where += " AND session_id = %s"
        params.append(session_id)
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM benchmark_experiments
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(r) for r in rows]


def patch_experiment(
    experiment_id: uuid.UUID,
    *,
    tenant_id: int,
    label: str | None = None,
    hypothesis: str | None = None,
    status: str | None = None,
    pending_patches: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    sets: list[str] = []
    params: list[Any] = []
    if label is not None:
        sets.append("label = %s")
        params.append(label)
    if hypothesis is not None:
        sets.append("hypothesis = %s")
        params.append(hypothesis)
    if status is not None:
        sets.append("status = %s")
        params.append(status)
    if pending_patches is not None:
        sets.append("pending_patches_json = %s::jsonb")
        params.append(json.dumps(pending_patches))
    if not sets:
        return get_experiment(experiment_id, tenant_id=tenant_id)
    params.extend([experiment_id, tenant_id])
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                UPDATE benchmark_experiments SET {", ".join(sets)}
                WHERE id = %s AND tenant_id = %s
                RETURNING *
                """,
                tuple(params),
            )
            row = cur.fetchone()
        conn.commit()
    return _ser(dict(row)) if row else None


def append_experiment_run(experiment_id: uuid.UUID, *, tenant_id: int, run_id: uuid.UUID) -> None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_experiments
                SET run_ids_json = run_ids_json || %s::jsonb, status = 'running'
                WHERE id = %s AND tenant_id = %s
                """,
                (json.dumps([str(run_id)]), experiment_id, tenant_id),
            )
        conn.commit()


from apps.backend.infrastructure.agent_runtime.agent_config_review_store import (
    create_review,
    experiment_report,
    get_review,
    list_reviews,
)
