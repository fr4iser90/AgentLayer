"""Validate and apply share grant policies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.backend.domain.shares.catalog import resource_catalog_entry

_DAYS_AHEAD_MIN = 1
_DAYS_AHEAD_MAX = 366


def _parse_expires_at(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_policy(
    resource_type: str,
    policy: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Return (clean_policy, error_message). Empty dict is valid."""
    if policy is None:
        return {}, None
    if not isinstance(policy, dict):
        return {}, "policy must be an object"

    entry = resource_catalog_entry(resource_type)
    allowed_fields = set(entry.get("policy_fields") or []) if entry else {"days_ahead", "expires_at"}

    clean: dict[str, Any] = {}
    for key, value in policy.items():
        k = str(key).strip()
        if k not in allowed_fields:
            return {}, f"policy field '{k}' is not allowed for resource '{resource_type}'"

        if k == "days_ahead":
            if value is None or value == "":
                continue
            try:
                days = int(value)
            except (TypeError, ValueError):
                return {}, "policy.days_ahead must be an integer"
            if days < _DAYS_AHEAD_MIN or days > _DAYS_AHEAD_MAX:
                return {}, f"policy.days_ahead must be between {_DAYS_AHEAD_MIN} and {_DAYS_AHEAD_MAX}"
            clean["days_ahead"] = days
        elif k == "expires_at":
            if value is None or value == "":
                continue
            dt = _parse_expires_at(value)
            if dt is None:
                return {}, "policy.expires_at must be ISO-8601 datetime"
            clean["expires_at"] = dt.isoformat().replace("+00:00", "Z")
        elif k == "permission":
            if value is None or value == "":
                continue
            perm = str(value).strip().lower()
            if perm not in ("view", "edit"):
                return {}, "policy.permission must be view or edit"
            clean["permission"] = perm
        elif k == "block_ids":
            if value is None:
                continue
            if not isinstance(value, list):
                return {}, "policy.block_ids must be an array of layout block ids"
            cleaned = [str(x).strip() for x in value if str(x).strip()]
            if not cleaned:
                continue
            clean["block_ids"] = cleaned[:32]
        elif k == "list_keys":
            if value is None:
                continue
            if not isinstance(value, list):
                return {}, "policy.list_keys must be an array of list keys"
            cleaned = [str(x).strip() for x in value if str(x).strip()]
            if not cleaned:
                continue
            clean["list_keys"] = cleaned[:32]
        else:
            clean[k] = value

    return clean, None


def grant_is_active(
    *,
    is_allowed: bool,
    revoked_at: Any,
    policy: dict[str, Any] | None,
    now: datetime | None = None,
) -> bool:
    if not is_allowed or revoked_at is not None:
        return False
    pol = policy if isinstance(policy, dict) else {}
    expires = _parse_expires_at(pol.get("expires_at"))
    if expires is not None:
        ref = now or datetime.now(UTC)
        if ref >= expires:
            return False
    return True


def effective_days_ahead(
    policy: dict[str, Any] | None,
    requested_days: int | None,
    *,
    default_requested: int = 7,
) -> int:
    requested = requested_days if requested_days is not None else default_requested
    try:
        requested = max(1, int(requested))
    except (TypeError, ValueError):
        requested = default_requested

    pol = policy if isinstance(policy, dict) else {}
    cap = pol.get("days_ahead")
    if cap is None:
        return requested
    try:
        cap_int = int(cap)
    except (TypeError, ValueError):
        return requested
    return min(requested, max(1, cap_int))
