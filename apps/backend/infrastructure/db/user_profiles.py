from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db.db import pool

def user_persona_get(user_id: uuid.UUID) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT instructions, inject_into_agent, updated_at
                FROM user_agent_persona
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return {
        "instructions": row["instructions"] or "",
        "inject_into_agent": bool(row["inject_into_agent"]),
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def user_persona_upsert(
    tenant_id: int,
    user_id: uuid.UUID,
    *,
    instructions: str,
    inject_into_agent: bool,
) -> None:
    text = (instructions or "").strip()
    if len(text) > 100_000:
        raise ValueError("instructions too long (max 100000 characters)")
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_agent_persona (user_id, tenant_id, instructions, inject_into_agent)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                  instructions = EXCLUDED.instructions,
                  inject_into_agent = EXCLUDED.inject_into_agent,
                  updated_at = now()
                """,
                (user_id, tenant_id, text, inject_into_agent),
            )
        conn.commit()


DEFAULT_AGENT_PROFILE: dict[str, Any] = {
    "display_name": "",
    "preferred_output_language": "",
    "locale": "",
    "timezone": "",
    "home_location": "",
    "work_location": "",
    "travel_mode": "",
    "travel_preferences": {},
    "tone": "",
    "verbosity": "",
    "language_level": "",
    "interests": [],
    "hobbies": [],
    "job_title": "",
    "organization": "",
    "industry": "",
    "experience_level": "",
    "primary_tools": [],
    "proactive_mode": False,
    "interaction_style": "",
    "inject_structured_profile": True,
    "inject_dynamic_traits": False,
    "dynamic_traits": {},
    "profile_version": 0,
    "profile_hash": "",
    "injection_preferences": {},
    "usage_patterns": {},
}

# Fields that define profile content for profile_hash (cache / diff).
_PROFILE_HASH_FIELDS: tuple[str, ...] = (
    "display_name",
    "preferred_output_language",
    "locale",
    "timezone",
    "home_location",
    "work_location",
    "travel_mode",
    "travel_preferences",
    "tone",
    "verbosity",
    "language_level",
    "interests",
    "hobbies",
    "job_title",
    "organization",
    "industry",
    "experience_level",
    "primary_tools",
    "proactive_mode",
    "interaction_style",
    "inject_structured_profile",
    "inject_dynamic_traits",
    "dynamic_traits",
    "injection_preferences",
    "usage_patterns",
)


def _compute_profile_hash(d: dict[str, Any]) -> str:
    payload = {k: d[k] for k in _PROFILE_HASH_FIELDS}
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _norm_json_array(val: Any) -> list[Any]:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            p = json.loads(val)
            return p if isinstance(p, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _norm_json_object(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val.strip():
        try:
            p = json.loads(val)
            return p if isinstance(p, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _norm_weighted_tags(val: Any) -> list[dict[str, Any]]:
    """Interests/hobbies: strings or ``[{ \"name\": \"…\", \"weight\": 0.0–1.0 }]``."""
    out: list[dict[str, Any]] = []
    items: list[Any]
    if isinstance(val, list):
        items = val
    else:
        items = _norm_json_array(val)
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "weight": 1.0})
        elif isinstance(item, dict):
            n = str(item.get("name") or "").strip()
            if not n:
                continue
            try:
                w = float(item.get("weight", 1.0))
            except (TypeError, ValueError):
                w = 1.0
            w = max(0.0, min(1.0, w))
            out.append({"name": n, "weight": w})
    return out[:200]


def _row_to_agent_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": row.get("display_name") or "",
        "preferred_output_language": row.get("preferred_output_language") or "",
        "locale": row.get("locale") or "",
        "timezone": row.get("timezone") or "",
        "home_location": row.get("home_location") or "",
        "work_location": row.get("work_location") or "",
        "travel_mode": row.get("travel_mode") or "",
        "travel_preferences": _norm_json_object(row.get("travel_preferences")),
        "tone": row.get("tone") or "",
        "verbosity": row.get("verbosity") or "",
        "language_level": row.get("language_level") or "",
        "interests": _norm_weighted_tags(row.get("interests")),
        "hobbies": _norm_weighted_tags(row.get("hobbies")),
        "job_title": row.get("job_title") or "",
        "organization": row.get("organization") or "",
        "industry": row.get("industry") or "",
        "experience_level": row.get("experience_level") or "",
        "primary_tools": _norm_json_array(row.get("primary_tools")),
        "proactive_mode": bool(row.get("proactive_mode")),
        "interaction_style": row.get("interaction_style") or "",
        "inject_structured_profile": bool(row.get("inject_structured_profile", True)),
        "inject_dynamic_traits": bool(row.get("inject_dynamic_traits")),
        "dynamic_traits": _norm_json_object(row.get("dynamic_traits")),
        "profile_version": int(row.get("profile_version") or 0),
        "profile_hash": str(row.get("profile_hash") or ""),
        "injection_preferences": _norm_json_object(row.get("injection_preferences")),
        "usage_patterns": _norm_json_object(row.get("usage_patterns")),
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def user_timezone_persist(
    tenant_id: int,
    user_id: uuid.UUID,
    timezone_name: str,
) -> None:
    """Save IANA timezone from browser/client — used by chat and background jobs for this user."""
    tz = (timezone_name or "").strip()
    if not tz or len(tz) > 128:
        return
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_agent_profile (user_id, tenant_id, timezone)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                  timezone = EXCLUDED.timezone,
                  updated_at = now()
                WHERE user_agent_profile.timezone IS DISTINCT FROM EXCLUDED.timezone
                """,
                (user_id, tenant_id, tz),
            )
        conn.commit()


def user_agent_profile_get(user_id: uuid.UUID) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  display_name, preferred_output_language, locale, timezone,
                  home_location, work_location, travel_mode, travel_preferences,
                  tone, verbosity, language_level,
                  interests, hobbies,
                  job_title, organization, industry, experience_level, primary_tools,
                  proactive_mode, interaction_style,
                  inject_structured_profile, inject_dynamic_traits, dynamic_traits,
                  profile_version, profile_hash, injection_preferences, usage_patterns,
                  updated_at
                FROM user_agent_profile
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return _row_to_agent_profile(row)


def user_agent_profile_upsert(
    tenant_id: int,
    user_id: uuid.UUID,
    data: dict[str, Any],
) -> None:
    """Replace structured profile for user (complete row). Bumps profile_version; sets profile_hash."""
    d = {**DEFAULT_AGENT_PROFILE, **data}
    d.pop("profile_version", None)
    d.pop("profile_hash", None)
    d["travel_preferences"] = _norm_json_object(d.get("travel_preferences"))
    d["interests"] = _norm_weighted_tags(d.get("interests"))
    d["hobbies"] = _norm_weighted_tags(d.get("hobbies"))
    d["primary_tools"] = _norm_json_array(d.get("primary_tools"))
    d["dynamic_traits"] = _norm_json_object(d.get("dynamic_traits"))
    d["injection_preferences"] = _norm_json_object(d.get("injection_preferences"))
    d["usage_patterns"] = _norm_json_object(d.get("usage_patterns"))
    d["proactive_mode"] = bool(d.get("proactive_mode"))
    d["inject_structured_profile"] = bool(d.get("inject_structured_profile", True))
    d["inject_dynamic_traits"] = bool(d.get("inject_dynamic_traits"))
    for arr_name in ("interests", "hobbies", "primary_tools"):
        if len(d[arr_name]) > 200:
            raise ValueError(f"{arr_name}: at most 200 entries")
    if len(json.dumps(d["travel_preferences"])) > 16_000:
        raise ValueError("travel_preferences JSON too large")
    if len(json.dumps(d["dynamic_traits"])) > 16_000:
        raise ValueError("dynamic_traits JSON too large")
    if len(json.dumps(d["injection_preferences"])) > 16_000:
        raise ValueError("injection_preferences JSON too large")
    if len(json.dumps(d["usage_patterns"])) > 16_000:
        raise ValueError("usage_patterns JSON too large")
    for k in (
        "display_name",
        "preferred_output_language",
        "locale",
        "timezone",
        "home_location",
        "work_location",
        "travel_mode",
        "tone",
        "verbosity",
        "language_level",
        "job_title",
        "organization",
        "industry",
        "experience_level",
        "interaction_style",
    ):
        s = str(d.get(k) or "")
        if len(s) > 10_000:
            raise ValueError(f"{k} too long (max 10000 characters)")
    phash = _compute_profile_hash(d)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT profile_version FROM user_agent_profile WHERE user_id = %s",
                (user_id,),
            )
            prev = cur.fetchone()
            old_v = int(prev[0]) if prev else 0
            new_v = old_v + 1
            cur.execute(
                """
                INSERT INTO user_agent_profile (
                  user_id, tenant_id,
                  display_name, preferred_output_language, locale, timezone,
                  home_location, work_location, travel_mode, travel_preferences,
                  tone, verbosity, language_level,
                  interests, hobbies,
                  job_title, organization, industry, experience_level, primary_tools,
                  proactive_mode, interaction_style,
                  inject_structured_profile, inject_dynamic_traits, dynamic_traits,
                  profile_version, profile_hash, injection_preferences, usage_patterns
                )
                VALUES (
                  %s, %s,
                  %s, %s, %s, %s,
                  %s, %s, %s, %s,
                  %s, %s, %s,
                  %s, %s,
                  %s, %s, %s, %s, %s,
                  %s, %s,
                  %s, %s, %s,
                  %s, %s, %s, %s
                )
                ON CONFLICT (user_id) DO UPDATE SET
                  tenant_id = EXCLUDED.tenant_id,
                  display_name = EXCLUDED.display_name,
                  preferred_output_language = EXCLUDED.preferred_output_language,
                  locale = EXCLUDED.locale,
                  timezone = EXCLUDED.timezone,
                  home_location = EXCLUDED.home_location,
                  work_location = EXCLUDED.work_location,
                  travel_mode = EXCLUDED.travel_mode,
                  travel_preferences = EXCLUDED.travel_preferences,
                  tone = EXCLUDED.tone,
                  verbosity = EXCLUDED.verbosity,
                  language_level = EXCLUDED.language_level,
                  interests = EXCLUDED.interests,
                  hobbies = EXCLUDED.hobbies,
                  job_title = EXCLUDED.job_title,
                  organization = EXCLUDED.organization,
                  industry = EXCLUDED.industry,
                  experience_level = EXCLUDED.experience_level,
                  primary_tools = EXCLUDED.primary_tools,
                  proactive_mode = EXCLUDED.proactive_mode,
                  interaction_style = EXCLUDED.interaction_style,
                  inject_structured_profile = EXCLUDED.inject_structured_profile,
                  inject_dynamic_traits = EXCLUDED.inject_dynamic_traits,
                  dynamic_traits = EXCLUDED.dynamic_traits,
                  profile_version = EXCLUDED.profile_version,
                  profile_hash = EXCLUDED.profile_hash,
                  injection_preferences = EXCLUDED.injection_preferences,
                  usage_patterns = EXCLUDED.usage_patterns,
                  updated_at = now()
                """,
                (
                    user_id,
                    tenant_id,
                    d["display_name"],
                    d["preferred_output_language"],
                    d["locale"],
                    d["timezone"],
                    d["home_location"],
                    d["work_location"],
                    d["travel_mode"],
                    Json(d["travel_preferences"]),
                    d["tone"],
                    d["verbosity"],
                    d["language_level"],
                    Json(d["interests"]),
                    Json(d["hobbies"]),
                    d["job_title"],
                    d["organization"],
                    d["industry"],
                    d["experience_level"],
                    Json(d["primary_tools"]),
                    d["proactive_mode"],
                    d["interaction_style"],
                    d["inject_structured_profile"],
                    d["inject_dynamic_traits"],
                    Json(d["dynamic_traits"]),
                    new_v,
                    phash,
                    Json(d["injection_preferences"]),
                    Json(d["usage_patterns"]),
                ),
            )
        conn.commit()


def user_resolve_in_tenant(
    tenant_id: int,
    *,
    email: str | None = None,
    external_sub: str | None = None,
) -> uuid.UUID | None:
    em = (email or "").strip()
    sub = (external_sub or "").strip()
    if not em and not sub:
        return None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            if em:
                cur.execute(
                    """
                    SELECT id FROM users
                    WHERE tenant_id = %s AND email IS NOT NULL
                      AND lower(trim(email)) = lower(trim(%s))
                    """,
                    (tenant_id, em),
                )
            else:
                cur.execute(
                    "SELECT id FROM users WHERE tenant_id = %s AND external_sub = %s",
                    (tenant_id, sub),
                )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


