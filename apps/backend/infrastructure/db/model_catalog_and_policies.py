"""Persistence helpers for model catalog preferences and model access policies."""
from __future__ import annotations

import re
import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db.db import pool

def external_llm_endpoints_list_all() -> list[dict[str, Any]]:
    """All external LLM endpoints (admin); includes ``api_key`` — do not expose to non-admin JSON."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, sort_order, enabled, label, base_url, api_key,
                       api_header_name,
                       model_default, model_vlm, model_agent, model_coding,
                       max_parallel,
                       created_at, updated_at
                FROM operator_external_llm_endpoints
                ORDER BY sort_order ASC, id ASC
                """
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
        out.append(d)
    return out


def external_llm_endpoints_enabled_ordered() -> list[dict[str, Any]]:
    """Enabled rows only, same order as :func:`external_llm_endpoints_list_all`."""
    return [r for r in external_llm_endpoints_list_all() if r.get("enabled")]


def model_catalog_prefs_list_all() -> list[dict[str, Any]]:
    """Admin model catalog preferences; missing rows mean visible defaults."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT provider_id, model_id, visible_in_chat, profile_tags, sort_order, updated_at
                FROM operator_model_catalog_prefs
                ORDER BY provider_id ASC, sort_order ASC, model_id ASC
                """
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["visible_in_chat"] = bool(d.get("visible_in_chat", True))
        d["sort_order"] = int(d.get("sort_order") or 0)
        tags = d.get("profile_tags")
        d["profile_tags"] = tags if isinstance(tags, list) else []
        v = d.get("updated_at")
        if v is not None and hasattr(v, "isoformat"):
            d["updated_at"] = v.isoformat()
        out.append(d)
    return out


def model_catalog_visible_index() -> dict[tuple[str, str], bool]:
    """Rows explicitly hidden from chat are ``False``; absent rows are visible by default."""
    out: dict[tuple[str, str], bool] = {}
    for r in model_catalog_prefs_list_all():
        provider_id = str(r.get("provider_id") or "").strip()
        model_id = str(r.get("model_id") or "").strip()
        if provider_id and model_id:
            out[(provider_id, model_id)] = bool(r.get("visible_in_chat", True))
    return out


def model_catalog_prefs_sync(rows: list[dict[str, Any]]) -> None:
    """
    Upsert admin model catalog preferences. Does not delete omitted rows; the UI can send
    only rows it touched, and stale prefs are harmless until the model id reappears.
    """
    with pool().connection() as conn:
        with conn.cursor() as cur:
            for raw in rows:
                provider_id = str(raw.get("provider_id") or "").strip().lower()
                model_id = str(raw.get("model_id") or "").strip()
                if not provider_id or not model_id:
                    continue
                if not re.match(r"^[a-z0-9_-]{1,64}\Z", provider_id):
                    raise ValueError(f"Invalid provider_id {provider_id!r}")
                visible = bool(raw.get("visible_in_chat", True))
                sort_order_raw = raw.get("sort_order")
                try:
                    sort_order = int(sort_order_raw if sort_order_raw is not None else 0)
                except (TypeError, ValueError):
                    sort_order = 0
                tags_raw = raw.get("profile_tags")
                tags = [
                    str(x).strip().lower()
                    for x in (tags_raw if isinstance(tags_raw, list) else [])
                    if str(x).strip().lower() in {"default", "vlm", "agent", "coding"}
                ]
                cur.execute(
                    """
                    INSERT INTO operator_model_catalog_prefs (
                      provider_id, model_id, visible_in_chat, profile_tags, sort_order, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (provider_id, model_id) DO UPDATE SET
                      visible_in_chat = EXCLUDED.visible_in_chat,
                      profile_tags = EXCLUDED.profile_tags,
                      sort_order = EXCLUDED.sort_order,
                      updated_at = now()
                    """,
                    (provider_id, model_id[:512], visible, Json(tags), sort_order),
                )
        conn.commit()


_POLICY_SCOPES = {"global", "tenant", "user"}
_ACCESS_STATES = {"inherit", "allow", "deny"}
_MODEL_PROFILES = {"default", "agent", "coding", "vlm", "embedding", "extractor", "stt", "tts"}
_PROVIDER_CAPABILITIES = {"chat", "embedding", "extractor", "stt", "tts", "voice_realtime"}


def _policy_target_where(scope: str, tenant_id: int | None, user_id: uuid.UUID | str | None) -> tuple[str, list[Any]]:
    s = str(scope or "").strip().lower()
    if s not in _POLICY_SCOPES:
        raise ValueError("invalid policy scope")
    if s == "global":
        return "scope = 'global' AND tenant_id IS NULL AND user_id IS NULL", []
    if s == "tenant":
        if tenant_id is None or int(tenant_id) < 1:
            raise ValueError("tenant_id required for tenant scope")
        return "scope = 'tenant' AND tenant_id = %s AND user_id IS NULL", [int(tenant_id)]
    if user_id is None:
        raise ValueError("user_id required for user scope")
    return "scope = 'user' AND user_id = %s", [uuid.UUID(str(user_id))]


def _policy_target_values(scope: str, tenant_id: int | None, user_id: uuid.UUID | str | None) -> tuple[str, int | None, uuid.UUID | None]:
    s = str(scope or "").strip().lower()
    if s == "global":
        return s, None, None
    if s == "tenant":
        if tenant_id is None or int(tenant_id) < 1:
            raise ValueError("tenant_id required for tenant scope")
        return s, int(tenant_id), None
    if s == "user":
        if user_id is None:
            raise ValueError("user_id required for user scope")
        return s, tenant_id if tenant_id is not None else None, uuid.UUID(str(user_id))
    raise ValueError("invalid policy scope")


def _normalize_provider_id(raw: Any) -> str:
    provider_id = str(raw or "").strip().lower()
    if not provider_id or not re.match(r"^[a-z0-9_-]{1,64}\Z", provider_id):
        raise ValueError(f"Invalid provider_id {provider_id!r}")
    return provider_id


def _normalize_access_state(raw: Any) -> str:
    state = str(raw or "inherit").strip().lower()
    if state not in _ACCESS_STATES:
        raise ValueError(f"Invalid access_state {state!r}")
    return state


def model_access_policies_list(scope: str, tenant_id: int | None = None, user_id: uuid.UUID | str | None = None) -> list[dict[str, Any]]:
    where, params = _policy_target_where(scope, tenant_id, user_id)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT scope, tenant_id, user_id, provider_id, model_id, access_state, sort_order, updated_at
                FROM model_access_policies
                WHERE {where}
                ORDER BY provider_id ASC, sort_order ASC, model_id ASC
                """,
                params,
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("user_id") is not None:
            d["user_id"] = str(d["user_id"])
        if d.get("tenant_id") is not None:
            d["tenant_id"] = int(d["tenant_id"])
        d["sort_order"] = int(d.get("sort_order") or 0)
        v = d.get("updated_at")
        if v is not None and hasattr(v, "isoformat"):
            d["updated_at"] = v.isoformat()
        out.append(d)
    return out


def model_access_policies_for_subject(tenant_id: int, user_id: uuid.UUID | str) -> list[dict[str, Any]]:
    uid = uuid.UUID(str(user_id))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT scope, tenant_id, user_id, provider_id, model_id, access_state, sort_order, updated_at
                FROM model_access_policies
                WHERE scope = 'global'
                   OR (scope = 'tenant' AND tenant_id = %s)
                   OR (scope = 'user' AND user_id = %s)
                ORDER BY
                  CASE scope WHEN 'global' THEN 0 WHEN 'tenant' THEN 1 ELSE 2 END,
                  provider_id ASC, sort_order ASC, model_id ASC
                """,
                (int(tenant_id), uid),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def model_access_policies_sync(
    scope: str,
    rows: list[dict[str, Any]],
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | str | None = None,
) -> None:
    target_scope, target_tenant, target_user = _policy_target_values(scope, tenant_id, user_id)
    where, params = _policy_target_where(target_scope, target_tenant, target_user)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM model_access_policies WHERE {where}", params)
            for idx, raw in enumerate(rows):
                provider_id = _normalize_provider_id(raw.get("provider_id"))
                model_id = str(raw.get("model_id") or "").strip()
                if not model_id:
                    continue
                state = _normalize_access_state(raw.get("access_state"))
                sort_order_raw = raw.get("sort_order")
                try:
                    sort_order = int(sort_order_raw if sort_order_raw is not None else idx)
                except (TypeError, ValueError):
                    sort_order = idx
                cur.execute(
                    """
                    INSERT INTO model_access_policies (
                      scope, tenant_id, user_id, provider_id, model_id, access_state, sort_order, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    """,
                    (target_scope, target_tenant, target_user, provider_id, model_id[:512], state, sort_order),
                )
        conn.commit()


def model_default_policies_list(scope: str, tenant_id: int | None = None, user_id: uuid.UUID | str | None = None) -> list[dict[str, Any]]:
    where, params = _policy_target_where(scope, tenant_id, user_id)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT scope, tenant_id, user_id, profile, provider_id, model_id, updated_at
                FROM model_default_policies
                WHERE {where}
                ORDER BY profile ASC
                """,
                params,
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("user_id") is not None:
            d["user_id"] = str(d["user_id"])
        if d.get("tenant_id") is not None:
            d["tenant_id"] = int(d["tenant_id"])
        v = d.get("updated_at")
        if v is not None and hasattr(v, "isoformat"):
            d["updated_at"] = v.isoformat()
        out.append(d)
    return out


def model_default_policies_for_subject(tenant_id: int, user_id: uuid.UUID | str) -> list[dict[str, Any]]:
    uid = uuid.UUID(str(user_id))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT scope, tenant_id, user_id, profile, provider_id, model_id, updated_at
                FROM model_default_policies
                WHERE scope = 'global'
                   OR (scope = 'tenant' AND tenant_id = %s)
                   OR (scope = 'user' AND user_id = %s)
                ORDER BY CASE scope WHEN 'global' THEN 0 WHEN 'tenant' THEN 1 ELSE 2 END
                """,
                (int(tenant_id), uid),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def model_default_policies_sync(
    scope: str,
    rows: list[dict[str, Any]],
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | str | None = None,
) -> None:
    target_scope, target_tenant, target_user = _policy_target_values(scope, tenant_id, user_id)
    where, params = _policy_target_where(target_scope, target_tenant, target_user)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM model_default_policies WHERE {where}", params)
            for raw in rows:
                profile = str(raw.get("profile") or "").strip().lower()
                if profile not in _MODEL_PROFILES:
                    raise ValueError(f"Invalid profile {profile!r}")
                provider_id = _normalize_provider_id(raw.get("provider_id"))
                model_id = str(raw.get("model_id") or "").strip()
                if not model_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO model_default_policies (
                      scope, tenant_id, user_id, profile, provider_id, model_id, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, now())
                    """,
                    (target_scope, target_tenant, target_user, profile, provider_id, model_id[:512]),
                )
        conn.commit()


def provider_capability_policies_list(scope: str, tenant_id: int | None = None, user_id: uuid.UUID | str | None = None) -> list[dict[str, Any]]:
    where, params = _policy_target_where(scope, tenant_id, user_id)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT scope, tenant_id, user_id, capability, provider_id, access_state, updated_at
                FROM provider_capability_policies
                WHERE {where}
                ORDER BY capability ASC, provider_id ASC
                """,
                params,
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("user_id") is not None:
            d["user_id"] = str(d["user_id"])
        if d.get("tenant_id") is not None:
            d["tenant_id"] = int(d["tenant_id"])
        v = d.get("updated_at")
        if v is not None and hasattr(v, "isoformat"):
            d["updated_at"] = v.isoformat()
        out.append(d)
    return out


def provider_capability_policies_for_subject(tenant_id: int, user_id: uuid.UUID | str) -> list[dict[str, Any]]:
    uid = uuid.UUID(str(user_id))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT scope, tenant_id, user_id, capability, provider_id, access_state, updated_at
                FROM provider_capability_policies
                WHERE scope = 'global'
                   OR (scope = 'tenant' AND tenant_id = %s)
                   OR (scope = 'user' AND user_id = %s)
                ORDER BY CASE scope WHEN 'global' THEN 0 WHEN 'tenant' THEN 1 ELSE 2 END
                """,
                (int(tenant_id), uid),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def provider_capability_policies_sync(
    scope: str,
    rows: list[dict[str, Any]],
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | str | None = None,
) -> None:
    target_scope, target_tenant, target_user = _policy_target_values(scope, tenant_id, user_id)
    where, params = _policy_target_where(target_scope, target_tenant, target_user)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM provider_capability_policies WHERE {where}", params)
            for raw in rows:
                capability = str(raw.get("capability") or "").strip().lower()
                if capability not in _PROVIDER_CAPABILITIES:
                    raise ValueError(f"Invalid capability {capability!r}")
                provider_id = _normalize_provider_id(raw.get("provider_id"))
                state = _normalize_access_state(raw.get("access_state"))
                cur.execute(
                    """
                    INSERT INTO provider_capability_policies (
                      scope, tenant_id, user_id, capability, provider_id, access_state, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, now())
                    """,
                    (target_scope, target_tenant, target_user, capability, provider_id, state),
                )
        conn.commit()


def external_llm_endpoint_by_id(endpoint_id: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, sort_order, enabled, label, base_url, api_key,
                       api_header_name,
                       model_default, model_vlm, model_agent, model_coding,
                       max_parallel,
                       created_at, updated_at
                FROM operator_external_llm_endpoints
                WHERE id = %s
                """,
                (int(endpoint_id),),
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
    return d


def _external_llm_key_stored(raw: str | None) -> str:
    """Persist placeholder for keyless OpenAI-compatible stacks (e.g. Ollama on LAN)."""
    k = str(raw or "").strip()
    return k if k else "-"


def external_llm_endpoints_sync(rows: list[dict[str, Any]]) -> None:
    """
    Replace endpoint set: update existing by ``id``, insert rows without ``id``,
    delete DB rows whose ``id`` is not listed. Empty ``api_key`` on update keeps the stored key.
    """
    incoming_ids: set[int] = set()
    for raw in rows:
        i = raw.get("id")
        if i is not None:
            incoming_ids.add(int(i))

    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM operator_external_llm_endpoints")
            existing = {int(r[0]) for r in cur.fetchall()}
            for eid in existing - incoming_ids:
                cur.execute(
                    "DELETE FROM operator_external_llm_endpoints WHERE id = %s",
                    (eid,),
                )

            for raw in rows:
                sid = raw.get("sort_order")
                sort_order = int(sid) if sid is not None else 0
                enabled = bool(raw.get("enabled", True))
                label = str(raw.get("label") or "")[:512]
                base_url = str(raw.get("base_url") or "").strip()
                key_in = raw.get("api_key")
                header_in = raw.get("api_header_name")
                md = raw.get("model_default")
                mv = raw.get("model_vlm")
                ma = raw.get("model_agent")
                mc = raw.get("model_coding")
                mp_raw = raw.get("max_parallel")
                try:
                    max_parallel = max(1, min(64, int(mp_raw if mp_raw is not None else 1)))
                except (TypeError, ValueError):
                    max_parallel = 1
                md_v = (str(md).strip() if md is not None else None) or None
                mv_v = (str(mv).strip() if mv is not None else None) or None
                ma_v = (str(ma).strip() if ma is not None else None) or None
                mc_v = (str(mc).strip() if mc is not None else None) or None

                rid = raw.get("id")
                if rid is None:
                    if not base_url:
                        raise ValueError("external_llm: base_url required for new endpoint")
                    nk = _external_llm_key_stored(str(key_in) if key_in is not None else "")
                    hn = (
                        str(header_in).strip()[:128]
                        if header_in is not None and str(header_in).strip()
                        else "Authorization"
                    )
                    cur.execute(
                        """
                        INSERT INTO operator_external_llm_endpoints (
                          sort_order, enabled, label, base_url, api_key, api_header_name,
                          model_default, model_vlm, model_agent, model_coding, max_parallel, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                        """,
                        (
                            sort_order,
                            enabled,
                            label,
                            base_url,
                            nk,
                            hn,
                            md_v,
                            mv_v,
                            ma_v,
                            mc_v,
                            max_parallel,
                        ),
                    )
                else:
                    eid = int(rid)
                    cur.execute(
                        "SELECT api_key, api_header_name FROM operator_external_llm_endpoints WHERE id = %s",
                        (eid,),
                    )
                    prev = cur.fetchone()
                    if not prev:
                        raise ValueError(f"external_llm: unknown id {eid}")
                    prev_key = str(prev[0] or "")
                    prev_header = str(prev[1] or "").strip() or "Authorization"
                    if key_in is None or (isinstance(key_in, str) and not key_in.strip()):
                        key_use = prev_key
                    else:
                        key_use = str(key_in).strip()
                    if header_in is None or (isinstance(header_in, str) and not str(header_in).strip()):
                        header_use = prev_header
                    else:
                        header_use = str(header_in).strip()[:128]
                    if not base_url:
                        raise ValueError("external_llm: base_url required")
                    key_use = _external_llm_key_stored(key_use)
                    cur.execute(
                        """
                        UPDATE operator_external_llm_endpoints SET
                          sort_order = %s,
                          enabled = %s,
                          label = %s,
                          base_url = %s,
                          api_key = %s,
                          api_header_name = %s,
                          model_default = %s,
                          model_vlm = %s,
                          model_agent = %s,
                          model_coding = %s,
                          max_parallel = %s,
                          updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            sort_order,
                            enabled,
                            label,
                            base_url,
                            key_use,
                            header_use,
                            md_v,
                            mv_v,
                            ma_v,
                            mc_v,
                            max_parallel,
                            eid,
                        ),
                    )
        conn.commit()
