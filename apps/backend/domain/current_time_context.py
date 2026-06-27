"""Inject authoritative server date/time into agent system context (per user/request)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from apps.backend.domain.user_persona import _append_system_block

logger = logging.getLogger(__name__)

USER_TIMEZONE_HEADER = "X-User-Timezone"


class CurrentTimeContextDependencies(Protocol):
    def user_timezone_persist(
        self,
        tenant_id: int,
        user_id: uuid.UUID,
        timezone_name: str,
    ) -> None: ...

    def user_agent_profile_get(self, user_id: uuid.UUID) -> dict[str, Any] | None: ...


_deps: CurrentTimeContextDependencies | None = None


def register_current_time_context_dependencies(deps: CurrentTimeContextDependencies) -> None:
    global _deps
    _deps = deps


def normalize_timezone_name(raw: str | None) -> str | None:
    name = (raw or "").strip()
    if not name or len(name) > 128:
        return None
    try:
        ZoneInfo(name)
    except Exception:
        return None
    return name


def _persist_request_timezone(
    user_id: Any,
    tenant_id: Any,
    timezone_name: str,
) -> None:
    if user_id is None or tenant_id is None:
        return
    try:
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        tid = int(tenant_id)
    except (ValueError, TypeError):
        return
    if _deps is None:
        return
    try:
        _deps.user_timezone_persist(tid, uid, timezone_name)
    except Exception:
        logger.debug("user_timezone_persist failed", exc_info=True)


def _profile_timezone(user_id: Any) -> str | None:
    if user_id is None:
        return None
    try:
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return None
    if _deps is None:
        return None
    try:
        prof = _deps.user_agent_profile_get(uid)
    except Exception:
        logger.debug("user_agent_profile_get failed for time context", exc_info=True)
        return None
    if not prof:
        return None
    return normalize_timezone_name(str(prof.get("timezone") or ""))


def resolve_user_timezone(
    user_id: Any,
    tenant_id: Any = None,
    *,
    request_timezone: str | None = None,
) -> str | None:
    """
    Per-user timezone — no silent UTC default.
    Browser header is persisted to user_agent_profile for scheduler/telegram.
    """
    req = normalize_timezone_name(request_timezone)
    if req:
        _persist_request_timezone(user_id, tenant_id, req)
        return req
    return _profile_timezone(user_id)


def build_current_time_context_snippet(*, timezone_name: str | None = None) -> str:
    if timezone_name:
        tz = ZoneInfo(timezone_name)
        now = datetime.now(tz)
        return (
            "Current date/time (authoritative — this user's timezone):\n"
            f"- Today: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})\n"
            f"- Local time: {now.strftime('%H:%M')} ({timezone_name})\n"
            f"- ISO: {now.isoformat()}\n"
            "- User dates are typically DD.MM.YYYY (German day.month.year)."
        )
    now_utc = datetime.now(timezone.utc)
    return (
        "Current date/time (calendar date only — this user's timezone is not stored yet):\n"
        f"- Calendar date (UTC): {now_utc.strftime('%Y-%m-%d')} ({now_utc.strftime('%A')})\n"
        f"- ISO (UTC): {now_utc.isoformat()}\n"
        "- Do not infer local wall-clock time; ask the user or wait until they use the web app "
        "(browser timezone is saved automatically on login/chat).\n"
        "- User dates are typically DD.MM.YYYY (German day.month.year)."
    )


def apply_current_time_context(
    messages: list[dict[str, Any]],
    user_id: Any = None,
    tenant_id: Any = None,
    *,
    request_timezone: str | None = None,
) -> list[dict[str, Any]]:
    """Append server now for this user; persist browser timezone when provided."""
    tz = resolve_user_timezone(
        user_id,
        tenant_id,
        request_timezone=request_timezone,
    )
    snippet = build_current_time_context_snippet(timezone_name=tz)
    return _append_system_block(messages, snippet)
