"""Persistence helpers for operator provider endpoints."""
from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db.db import pool

_OPERATOR_PROVIDER_KINDS = frozenset({"chat", "embedding", "voice_stt", "voice_tts", "extractor"})


def _operator_provider_kind(kind: str) -> str:
    k = str(kind or "").strip().lower()
    if k not in _OPERATOR_PROVIDER_KINDS:
        raise ValueError(f"operator_provider: invalid kind {kind!r}")
    return k


def _column_exists(cur: Any, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
            FROM information_schema.columns
           WHERE table_name = %s AND column_name = %s
        )
        """,
        (table, column),
    )
    row = cur.fetchone()
    return bool(row[0] if row is not None and not isinstance(row, dict) else row.get("exists") if row else False)


def operator_provider_endpoints_list_all(kind: str | None = None) -> list[dict[str, Any]]:
    """All non-LLM provider endpoints; includes ``api_key`` — do not expose directly."""
    kind_v = _operator_provider_kind(kind) if kind is not None else None
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            max_parallel_expr = "max_parallel" if _column_exists(cur, "operator_provider_endpoints", "max_parallel") else "1 AS max_parallel"
            if kind_v is None:
                cur.execute(
                    f"""
                    SELECT id, kind, sort_order, enabled, label, base_url, api_key,
                           api_header_name, model_default, {max_parallel_expr}, options_json,
                           created_at, updated_at
                    FROM operator_provider_endpoints
                    ORDER BY kind ASC, sort_order ASC, id ASC
                    """
                )
            else:
                cur.execute(
                    f"""
                    SELECT id, kind, sort_order, enabled, label, base_url, api_key,
                           api_header_name, model_default, {max_parallel_expr}, options_json,
                           created_at, updated_at
                    FROM operator_provider_endpoints
                    WHERE kind = %s
                    ORDER BY sort_order ASC, id ASC
                    """,
                    (kind_v,),
                )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "updated_at"):
            v = d.get(k)
            if v is not None and hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        d["id"] = int(d["id"])
        d["sort_order"] = int(d["sort_order"])
        d["enabled"] = bool(d["enabled"])
        d["max_parallel"] = max(1, min(64, int(d.get("max_parallel") or 1)))
        if not isinstance(d.get("options_json"), dict):
            d["options_json"] = {}
        out.append(d)
    return out


def operator_provider_endpoint_by_id(kind: str, endpoint_id: int) -> dict[str, Any] | None:
    kind_v = _operator_provider_kind(kind)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            max_parallel_expr = "max_parallel" if _column_exists(cur, "operator_provider_endpoints", "max_parallel") else "1 AS max_parallel"
            cur.execute(
                f"""
                SELECT id, kind, sort_order, enabled, label, base_url, api_key,
                       api_header_name, model_default, {max_parallel_expr}, options_json,
                       created_at, updated_at
                FROM operator_provider_endpoints
                WHERE kind = %s AND id = %s
                """,
                (kind_v, int(endpoint_id)),
            )
            r = cur.fetchone()
        conn.commit()
    if not r:
        return None
    d = dict(r)
    d["id"] = int(d["id"])
    d["sort_order"] = int(d["sort_order"])
    d["enabled"] = bool(d["enabled"])
    d["max_parallel"] = max(1, min(64, int(d.get("max_parallel") or 1)))
    if not isinstance(d.get("options_json"), dict):
        d["options_json"] = {}
    return d


def operator_provider_endpoints_sync(
    kind: str,
    rows: list[dict[str, Any]],
    *,
    delete_missing: bool = True,
    delete_ids: list[int] | tuple[int, ...] | set[int] | None = None,
) -> None:
    """
    Sync endpoint rows for one provider kind.

    Updates existing by ``id`` and inserts rows without ``id``. When ``delete_missing``
    is true, rows whose ``id`` is omitted are deleted (legacy full-replace behavior).
    Otherwise only ids listed in ``delete_ids`` are deleted. Empty ``api_key`` on
    update keeps the stored key.
    """
    kind_v = _operator_provider_kind(kind)
    incoming_ids: set[int] = set()
    for raw in rows:
        i = raw.get("id")
        if i is not None:
            incoming_ids.add(int(i))

    with pool().connection() as conn:
        with conn.cursor() as cur:
            has_max_parallel = _column_exists(cur, "operator_provider_endpoints", "max_parallel")
            cur.execute("SELECT id FROM operator_provider_endpoints WHERE kind = %s", (kind_v,))
            existing = {int(r[0]) for r in cur.fetchall()}
            explicit_delete_ids = {int(i) for i in (delete_ids or []) if int(i) >= 1}
            ids_to_delete = (existing - incoming_ids) if delete_missing else (existing & explicit_delete_ids)
            for eid in ids_to_delete:
                cur.execute(
                    "DELETE FROM operator_provider_endpoints WHERE kind = %s AND id = %s",
                    (kind_v, eid),
                )

            for raw in rows:
                sid = raw.get("sort_order")
                sort_order = int(sid) if sid is not None else 0
                enabled = bool(raw.get("enabled", True))
                label = str(raw.get("label") or "")[:512]
                base_url = str(raw.get("base_url") or "").strip()
                key_in = raw.get("api_key")
                header_in = raw.get("api_header_name")
                model = raw.get("model_default")
                model_v = (str(model).strip() if model is not None else None) or None
                mp_raw = raw.get("max_parallel")
                try:
                    max_parallel = max(1, min(64, int(mp_raw if mp_raw is not None else 1)))
                except (TypeError, ValueError):
                    max_parallel = 1
                options = raw.get("options_json")
                options_v = options if isinstance(options, dict) else {}
                rid = raw.get("id")
                if rid is None:
                    if not base_url:
                        raise ValueError(f"operator_provider:{kind_v}: base_url required for new endpoint")
                    key_use = str(key_in or "").strip()
                    header_use = (
                        str(header_in).strip()[:128]
                        if header_in is not None and str(header_in).strip()
                        else "Authorization"
                    )
                    if has_max_parallel:
                        cur.execute(
                            """
                            INSERT INTO operator_provider_endpoints (
                              kind, sort_order, enabled, label, base_url, api_key,
                              api_header_name, model_default, max_parallel, options_json, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                            """,
                            (
                                kind_v,
                                sort_order,
                                enabled,
                                label,
                                base_url,
                                key_use,
                                header_use,
                                model_v,
                                max_parallel,
                                Json(options_v),
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO operator_provider_endpoints (
                              kind, sort_order, enabled, label, base_url, api_key,
                              api_header_name, model_default, options_json, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                            """,
                            (
                                kind_v,
                                sort_order,
                                enabled,
                                label,
                                base_url,
                                key_use,
                                header_use,
                                model_v,
                                Json(options_v),
                            ),
                        )
                else:
                    eid = int(rid)
                    cur.execute(
                        "SELECT api_key, api_header_name FROM operator_provider_endpoints WHERE kind = %s AND id = %s",
                        (kind_v, eid),
                    )
                    prev = cur.fetchone()
                    if not prev:
                        raise ValueError(f"operator_provider:{kind_v}: unknown id {eid}")
                    prev_key = str(prev[0] or "")
                    prev_header = str(prev[1] or "").strip() or "Authorization"
                    key_use = (
                        prev_key
                        if key_in is None or (isinstance(key_in, str) and not key_in.strip())
                        else str(key_in).strip()
                    )
                    header_use = (
                        prev_header
                        if header_in is None or (isinstance(header_in, str) and not str(header_in).strip())
                        else str(header_in).strip()[:128]
                    )
                    if not base_url:
                        raise ValueError(f"operator_provider:{kind_v}: base_url required")
                    if has_max_parallel:
                        cur.execute(
                            """
                            UPDATE operator_provider_endpoints SET
                              sort_order = %s,
                              enabled = %s,
                              label = %s,
                              base_url = %s,
                              api_key = %s,
                              api_header_name = %s,
                              model_default = %s,
                              max_parallel = %s,
                              options_json = %s,
                              updated_at = now()
                            WHERE kind = %s AND id = %s
                            """,
                            (
                                sort_order,
                                enabled,
                                label,
                                base_url,
                                key_use,
                                header_use,
                                model_v,
                                max_parallel,
                                Json(options_v),
                                kind_v,
                                eid,
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE operator_provider_endpoints SET
                              sort_order = %s,
                              enabled = %s,
                              label = %s,
                              base_url = %s,
                              api_key = %s,
                              api_header_name = %s,
                              model_default = %s,
                              options_json = %s,
                              updated_at = now()
                            WHERE kind = %s AND id = %s
                            """,
                            (
                                sort_order,
                                enabled,
                                label,
                                base_url,
                                key_use,
                                header_use,
                                model_v,
                                Json(options_v),
                                kind_v,
                                eid,
                            ),
                        )
        conn.commit()
