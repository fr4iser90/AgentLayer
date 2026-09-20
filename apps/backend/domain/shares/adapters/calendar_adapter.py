"""Registry adapter for shared calendars (ADR 0014 step 4).

Two things this adapter is for:

* **The grant check lives inside it.** The generic read path cannot reach a
  friend's calendar without going through `resolve`, so the check is not
  optional (driver 4). Before this, the check lived in the tool, which is
  how four of seven types ended up with a grant that read as access.
* **The underlying read never returns the credential.** It delegates to
  ``fetch_shared_calendar``, which resolves the owner's ICS bearer URL,
  guards it and returns events only (Principle 1).

This is still **live delegation**. Step 7 replaces the injected reader with
a published availability projection ("share my availability"). When it
does, only ``CalendarShareDependencies.read_shared_calendar`` changes —
the adapter surface, the tool surface and the grant semantics stay as they
are.

Dependencies are injected rather than imported so the domain layer never
reaches into ``plugins``.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.backend.domain.shares.policy import effective_days_ahead

#: The grant layer resolves ``calendar`` as an alias of this, so querying the
#: canonical id finds rows written under either name.
_CALENDAR_RESOURCE = "google_calendar"
_DEFAULT_DAYS = 7


class CalendarShareDependencies(Protocol):
    def share_permission_get(
        self,
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        resource_type: str,
        resource_identifier: str,
    ) -> dict[str, Any] | None: ...

    def read_shared_calendar(
        self, owner_user_id: uuid.UUID, *, days_ahead: int
    ) -> dict[str, Any]: ...


_deps: CalendarShareDependencies | None = None


def register_calendar_adapter_dependencies(deps: CalendarShareDependencies) -> None:
    global _deps
    _deps = deps


class CalendarShareAdapter:
    #: ``calendar`` is the legacy alias the grant layer already resolves;
    #: declaring it here keeps it visible next to the type it means instead of
    #: drifting in a separate alias map (§1.5).
    resource_types: tuple[str, ...] = ("google_calendar", "calendar")

    #: What the calendar read actually acts on. ``block_ids`` is a dashboard
    #: concept and ``list_keys`` is read by nothing — accepting them here was
    #: the §1.9 consent bug, and registering this adapter closes it.
    policy_fields: frozenset[str] = frozenset({"days_ahead", "expires_at"})

    supports_list: bool = False

    def normalize_identifier(self, raw: str) -> str | None:
        # A calendar share is one-per-user; "primary" is the only identifier.
        # Anything else is accepted verbatim so an existing row with a custom
        # identifier keeps resolving rather than silently going unreadable.
        text = (raw or "").strip().lower()
        return text or "primary"

    def resolve(
        self,
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        identifier: str,
        request: dict[str, Any] | None = None,
    ) -> Any | None:
        if _deps is None:
            # Not wired. Deny rather than guess: a missing registration must
            # not become an unchecked read.
            return None

        grant = _deps.share_permission_get(
            owner_user_id=owner_user_id,
            grantee_user_id=grantee_user_id,
            resource_type=_CALENDAR_RESOURCE,
            resource_identifier=identifier,
        )
        if grant is None:
            return None

        requested = (request or {}).get("days")
        days = effective_days_ahead(
            grant.get("policy"),
            requested if requested is not None else None,
            default_requested=_DEFAULT_DAYS,
        )
        projection = _deps.read_shared_calendar(owner_user_id, days_ahead=days)
        if not isinstance(projection, dict):
            return None
        # Surface the cap the grant imposed, so the grantee can see how far
        # ahead they were allowed rather than inferring it from a truncation,
        # and carry the policy itself for the same reason the collection
        # adapter does: it is what the owner chose to share, not a secret.
        return {
            **projection,
            "days_effective": days,
            "share_policy": grant.get("policy") or {},
        }
