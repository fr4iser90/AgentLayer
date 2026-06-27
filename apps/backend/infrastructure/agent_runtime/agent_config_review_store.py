"""Review and report persistence for agent configuration experiments."""
from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db

def create_review(
    *,
    tenant_id: int,
    experiment_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    mode: str,
    reviewer_model: str | None,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    actor_type: str = "reviewer_job",
) -> dict[str, Any]:
    rid = uuid.uuid4()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO benchmark_reviews (
                  id, tenant_id, experiment_id, session_id, mode, reviewer_model,
                  input_json, output_json, actor_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                RETURNING *
                """,
                (
                    rid,
                    tenant_id,
                    experiment_id,
                    session_id,
                    mode,
                    reviewer_model,
                    json.dumps(input_payload),
                    json.dumps(output_payload),
                    actor_type,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _ser(row)


def get_review(review_id: uuid.UUID, *, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM benchmark_reviews WHERE id = %s AND tenant_id = %s",
                (review_id, tenant_id),
            )
            row = cur.fetchone()
    return _ser(dict(row)) if row else None


def list_reviews(tenant_id: int, *, limit: int = 50, experiment_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    lim = max(1, min(200, int(limit)))
    params: list[Any] = [tenant_id]
    where = "tenant_id = %s"
    if experiment_id is not None:
        where += " AND experiment_id = %s"
        params.append(experiment_id)
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM benchmark_reviews
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return [_ser(r) for r in rows]


def experiment_report(experiment_id: uuid.UUID, *, tenant_id: int) -> dict[str, Any] | None:
    exp = get_experiment(experiment_id, tenant_id=tenant_id)
    if not exp:
        return None
    run_ids = exp.get("run_ids_json") or []
    if not isinstance(run_ids, list):
        run_ids = []
    from apps.backend.infrastructure.benchmarks import benchmark_runs_store
    from apps.backend.infrastructure.benchmarks.benchmark_analysis import analyze_runs

    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tenant_id, limit=500)
    wanted = {str(r) for r in run_ids}
    filtered = [r for r in rows if str(r.get("id")) in wanted] if wanted else []
    analysis = analyze_runs(filtered, experiment_id=str(experiment_id))
    reviews = list_reviews(tenant_id, experiment_id=experiment_id, limit=20)
    return {"experiment": exp, "analysis": analysis, "reviews": reviews}
