"""Registry adapter for shared calendars (ADR 0014 steps 4 and 6).

Two things this adapter is for:

* **The grant check lives inside it.** The generic read path cannot reach a
  friend's calendar without going through ``resolve``, so the check is not
  optional (driver 4). Before this, the check lived in the tool, which is
  how four of seven types ended up with a grant that read as access.
* **What crosses is a published narrowing, not the live feed.** Step 4 made
  the read go through the adapter; step 6 made it read a projection the
  owner published, so the read no longer resolves the owner's ICS bearer
  URL at all. The credential is used only when the owner's side republishes.

Two shapes, chosen by the owner at publish time
---------------------------------------------
``events`` keeps titles, which is what a friend saw before projections
existed, so turning projections on changes nothing visible.
``availability`` keeps only busy windows — no title, no location, no event
id — and is the shape the ADR actually wants, because a title cannot leak
from a projection that never contained one.

The owner picks one per resource and every grantee of that resource sees
that same shape. A grantee cannot ask for a different one: ``resolve``
reads the kind that is stored, never a kind from the request.

Dependencies are injected rather than imported so the domain layer never
reaches into ``plugins``.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.backend.domain.shares.policy import effective_days_ahead
from apps.backend.domain.shares.projections import (
    ShareProjectionPublishError,
    load_fresh,
)

#: The grant layer resolves ``calendar`` as an alias of this, so querying the
#: canonical id finds rows written under either name.
_CALENDAR_RESOURCE = "google_calendar"
_DEFAULT_DAYS = 7

#: How far ahead a publish reaches, regardless of what any grant asks for.
#: The projection is one row per resource shared by all its grantees, so it
#: has to cover the widest window anyone might read; a grant narrower than
#: this is applied at read time, and a grant wider than this reads only as
#: far as the projection goes.
_PUBLISH_HORIZON_DAYS = 60

#: Fields an ``availability`` publish drops. Named explicitly rather than
#: whitelisting what survives, so adding a field to the live read does not
#: silently widen what the availability projection discloses.
_DISCLOSIVE_EVENT_FIELDS = ("summary", "location", "uid", "description", "attendees", "organizer")


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


def _strip_event(event: dict[str, Any]) -> dict[str, Any]:
    """One event reduced to when it is busy, and nothing else."""
    slot: dict[str, Any] = {}
    for key, value in event.items():
        if key in _DISCLOSIVE_EVENT_FIELDS:
            continue
        slot[key] = value
    start = slot.get("start")
    if slot.get("end") is None and start is not None:
        slot["end"] = start
    slot["busy"] = True
    return slot


def _narrow_for_kind(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    """Apply the owner's chosen disclosure to a freshly read feed."""
    events = payload.get("events")
    if not isinstance(events, list):
        events = []
    if kind == "availability":
        out = dict(payload)
        out["events"] = [_strip_event(e) for e in events if isinstance(e, dict)]
        return out
    return dict(payload)


def _events_within_days(payload: dict[str, Any], days: int) -> list[dict[str, Any]]:
    """Cut the published window down to what this grant allows.

    The projection is published wider than any single grant needs. Rather
    than republishing per grant, the read filters, so a grant of 7 days
    over a 60-day projection shows 7 days.
    """
    from datetime import datetime, timedelta, timezone

    events = payload.get("events")
    if not isinstance(events, list):
        return []
    cutoff = datetime.now(timezone.utc) + timedelta(days=days)
    kept: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        raw = event.get("start")
        if not raw:
            kept.append(event)
            continue
        try:
            start = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            kept.append(event)
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start <= cutoff:
            kept.append(event)
    return kept


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

    # --- projection contract (step 6) ---
    supports_projection: bool = True
    projection_kinds: tuple[str, ...] = ("events", "availability")
    #: ``events`` is the default so that switching on projections does not
    #: change what a friend sees. An owner who wants the narrower shape has
    #: to say so; that is the owner's call, not a side effect of shipping
    #: the machinery.
    default_projection_kind: str = "events"
    projection_ttl_seconds: int = 900

    def normalize_identifier(self, raw: str) -> str | None:
        # A calendar share is one-per-user; "primary" is the only identifier.
        # Anything else is accepted verbatim so an existing row with a custom
        # identifier keeps resolving rather than silently going unreadable.
        text = (raw or "").strip().lower()
        return text or "primary"

    def publish_projection(
        self, *, owner_user_id: uuid.UUID, identifier: str, kind: str
    ) -> dict[str, Any] | None:
        """Read the owner's own calendar and return the narrowed payload.

        Runs on the owner's behalf. This is the only place in the share path
        that touches the ICS credential, and it runs on the owner's side —
        the grantee's read goes to the stored row instead.
        """
        if _deps is None:
            return None
        payload = _deps.read_shared_calendar(
            owner_user_id, days_ahead=_PUBLISH_HORIZON_DAYS
        )
        if not isinstance(payload, dict):
            return None
        if not payload.get("ok"):
            # Raise rather than return None so the grantee hears *why* there
            # is nothing. "owner_has_no_calendar_configured" and "not
            # shared with you" are different facts, and collapsing them
            # sends the grantee to ask for a grant they already hold.
            raise ShareProjectionPublishError(
                str(payload.get("error") or "calendar_read_failed")
            )
        return _narrow_for_kind(payload, kind)

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

        outcome = load_fresh(
            self,
            owner_user_id=owner_user_id,
            resource_type=_CALENDAR_RESOURCE,
            resource_identifier=identifier,
        )
        if not outcome.ok:
            # A live grant with nothing behind it. Returning the reason as an
            # error payload keeps it distinct, up through the tool, from the
            # "no grant" refusal the caller already got for a stranger.
            if outcome.error:
                return {"error": outcome.error}
            return None
        stored = outcome.projection

        events = _events_within_days(stored.payload, days)
        # Surface the cap the grant imposed, so the grantee can see how far
        # ahead they were allowed rather than inferring it from a truncation,
        # and carry the policy itself for the same reason the collection
        # adapter does: it is what the owner chose to share, not a secret.
        # The projection envelope says which narrowing they are looking at
        # and whether it is stale, so neither is something they have to infer.
        return {
            **stored.payload,
            "events": events,
            "count": len(events),
            "days_effective": days,
            "share_policy": grant.get("policy") or {},
            "projection_kind": stored.kind,
            "projection_stale": stored.stale,
            "projection_generated_at": stored.generated_at.isoformat()
            if stored.generated_at
            else None,
        }
