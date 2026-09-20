"""The projection contract behind the share adapter registry (ADR 0014 step 6).

A projection is a **narrowed, owner-published view** that a grantee's read
is served from instead of the live source. The value is not caching — it is
that the narrowing happens once, on the owner's side, and what was never
written into the projection cannot reach anyone through it.

Three things this module guarantees, none of which an adapter can guarantee
for itself:

**Nothing credential-shaped is ever stored.** ``store_projection`` runs the
same Principle 1 check the registry runs on the way out, on the way *in*.
A leak on a live read is one bad response; a leak here is a row that sits
in the database holding a bearer credential, readable by whatever bug
finds it next. Storing is the point where the guarantee has to be hardest.

**A projection is owner-owned, never grantee-keyed.** Every lookup takes
``owner_user_id``. There is no method here that takes a grantee, because a
grantee must not be able to name which projection they get. The grant is
checked by the adapter before it ever calls into this module.

**Nothing is served past its freshness bound.** ``load_fresh`` republishes
rather than returning a stale row, and only falls back to stale when the
republish itself failed — and it says so on the row, so "stale" is a
visible state rather than a silent one.

Storage is injected. The domain does not know about Postgres; see
``register_share_projection_store`` and the infrastructure service that
calls it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace as dataclass_replace
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from apps.backend.domain.shares.adapter import find_credential_keys
from apps.backend.domain.shares.catalog import canonical_resource_type

logger = logging.getLogger(__name__)


class ShareProjectionError(RuntimeError):
    """A projection violated the storage contract."""


class ShareProjectionPublishError(RuntimeError):
    """The adapter could not publish, for a reason the grantee should hear.

    Distinct from "nothing to show". An owner who granted a calendar but
    never configured one has a live grant and no data; reporting that as
    "has not shared" tells the grantee the opposite of what is true and
    sends them to ask for a grant they already have.
    """


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    """Timestamps arrive tz-aware from Postgres and naive from fakes."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


# How long a projection may outlive its freshness bound.
#
# The bound says how stale a view may be served as if it were current.
# This says how long the copy may exist at all once it is past that. The
# two together answer a tension inside this ADR: the stale row is what
# lets a friend still be answered during an upstream outage, and an
# indefinitely lingering copy of someone's data is the outcome the
# NOT NULL bound was written to prevent. A grace period keeps the first
# without silently surrendering the second.
#
# One flat value rather than a per-adapter declaration like the TTL. The
# sweeper runs across every adapter at once and cannot ask each row's
# adapter for its own number; a per-adapter grace would mean the sweeper
# has to take the maximum across the registry to avoid deleting a row
# another adapter may still serve. Not worth the coupling for a knob
# nobody has asked to turn per type.
STALE_GRACE_SECONDS = 3600


@dataclass(frozen=True)
class StoredProjection:
    """One published projection row, as read back from storage.

    ``stale`` is not a column. It is set only when a republish was needed
    and failed, so that a caller can tell "fresh" from "all we have"
    without comparing timestamps.
    """

    owner_user_id: uuid.UUID
    resource_type: str
    resource_identifier: str
    kind: str
    payload: dict[str, Any]
    generated_at: datetime | None
    expires_at: datetime | None
    stale: bool = False

    def is_fresh(self, *, now: datetime | None = None) -> bool:
        if self.stale:
            return False
        if self.expires_at is None:
            # No bound means no contract. Treat as expired rather than as
            # "never expires": an unbounded copy of someone's data is the
            # outcome this whole module exists to prevent.
            return False
        return _aware(self.expires_at) > (now or _utcnow())

    def is_retained(
        self, *, now: datetime | None = None, grace_seconds: int = STALE_GRACE_SECONDS
    ) -> bool:
        """Whether this row may still be held, let alone served.

        Past the bound plus the grace the row is not merely old, it is out
        of its retention. Checked on the read path on purpose: a bound
        that only a janitor enforces is a bound that depends on the
        janitor running, and "it gets cleaned up soon" is the exact
        guarantee this ADR was written because it kept not holding.
        """
        if self.expires_at is None:
            return False
        deadline = _aware(self.expires_at) + timedelta(seconds=max(0, grace_seconds))
        return deadline > (now or _utcnow())

    def as_dict(self) -> dict[str, Any]:
        """The projection envelope a grantee receives.

        ``kind`` and ``stale`` travel with the payload on purpose. A grantee
        who cannot see which narrowing they got cannot tell a free/busy view
        from a full event list, and an owner answering "what does my friend
        see of my calendar?" needs the same answer visible.
        """
        return {
            "projection_kind": self.kind,
            "generated_at": self.generated_at.isoformat()
            if self.generated_at
            else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "stale": self.stale,
            "data": self.payload,
        }


@dataclass(frozen=True)
class ProjectionOutcome:
    """What asking for a fresh projection produced.

    ``projection`` None with ``error`` None and a stale row is different
    from None with an error: the first means "we have nothing and cannot
    say why", the second means the owner's own source refused.
    """

    projection: StoredProjection | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.projection is not None


class ShareProjectionStore(Protocol):
    """Persistence for published projections.

    Keyed on (owner, resource_type, resource_identifier) with the type
    already canonicalised by the caller, so a projection published against
    ``google_calendar`` is found by a read that arrived as ``calendar``.
    """

    def projection_get(
        self, *, owner_user_id: uuid.UUID, resource_type: str, resource_identifier: str
    ) -> dict[str, Any] | None: ...

    def projection_upsert(
        self,
        *,
        owner_user_id: uuid.UUID,
        resource_type: str,
        resource_identifier: str,
        kind: str,
        payload: dict[str, Any],
        expires_at: datetime,
    ) -> None: ...

    def projection_delete(
        self, *, owner_user_id: uuid.UUID, resource_type: str, resource_identifier: str
    ) -> int: ...

    def projection_delete_expired(
        self, *, limit: int = 200, grace_seconds: int = 0
    ) -> int: ...

    def projection_list_due(
        self, *, limit: int, within_seconds: int
    ) -> list[dict[str, Any]]: ...

    def projection_list_for_owner(
        self, *, owner_user_id: uuid.UUID
    ) -> list[dict[str, Any]]: ...


_store: ShareProjectionStore | None = None


def register_share_projection_store(store: ShareProjectionStore) -> None:
    """Wire the persistence backend. Called once from infrastructure."""
    global _store
    _store = store


def projection_store_ready() -> bool:
    return _store is not None


def projection_store() -> ShareProjectionStore | None:
    """The wired store, for the maintenance pass that iterates over rows.

    Exposed rather than having ``projection_refresh`` reach for the module
    global directly, so there is one place that answers "is there a store"
    and a reader of either module can see where the answer comes from.
    """
    return _store


def projection_backed(adapter: Any) -> bool:
    """Whether this adapter publishes projections rather than reading live."""
    return bool(getattr(adapter, "supports_projection", False))


def projection_kinds_for(adapter: Any) -> tuple[str, ...]:
    kinds = tuple(getattr(adapter, "projection_kinds", ()) or ())
    return kinds


def default_projection_kind(adapter: Any) -> str | None:
    kinds = projection_kinds_for(adapter)
    if not kinds:
        return None
    declared = getattr(adapter, "default_projection_kind", None)
    return declared if declared in kinds else kinds[0]


def projection_ttl_seconds(adapter: Any) -> int:
    ttl = getattr(adapter, "projection_ttl_seconds", None)
    try:
        ttl_int = int(ttl) if ttl is not None else 900
    except (TypeError, ValueError):
        ttl_int = 900
    # Bounded both ways: a one-second TTL turns every read into a live
    # fetch, and a year-long one is a copy that never gets corrected.
    return max(60, min(ttl_int, 24 * 60 * 60))


def store_projection(
    adapter: Any,
    *,
    owner_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str,
    kind: str,
    payload: dict[str, Any],
) -> StoredProjection:
    """Validate and persist one published projection.

    Raises rather than storing anything credential-shaped. This is the
    load-bearing check: the adapter produced the payload, but the adapter
    is not the one deciding whether it is safe to keep.
    """
    if _store is None:
        raise ShareProjectionError("share projection store is not wired")
    if not isinstance(payload, dict):
        raise ShareProjectionError(
            f"{type(adapter).__name__} published a non-object projection"
        )

    canonical = canonical_resource_type(resource_type)
    if not canonical:
        raise ShareProjectionError(f"invalid resource_type {resource_type!r}")

    kinds = projection_kinds_for(adapter)
    if kinds and kind not in kinds:
        raise ShareProjectionError(
            f"{type(adapter).__name__} does not publish projection kind {kind!r}"
            f" (publishes: {', '.join(kinds)})"
        )

    leaked = find_credential_keys(payload)
    if leaked:
        raise ShareProjectionError(
            f"{type(adapter).__name__} projection for {canonical!r} carries "
            f"credential-shaped key(s): {', '.join(sorted(set(leaked)))} — "
            "refusing to store"
        )

    expires_at = _utcnow() + timedelta(seconds=projection_ttl_seconds(adapter))
    _store.projection_upsert(
        owner_user_id=owner_user_id,
        resource_type=canonical,
        resource_identifier=resource_identifier,
        kind=kind,
        payload=payload,
        expires_at=expires_at,
    )
    now = _utcnow()
    return StoredProjection(
        owner_user_id=owner_user_id,
        resource_type=canonical,
        resource_identifier=resource_identifier,
        kind=kind,
        payload=payload,
        generated_at=now,
        expires_at=expires_at,
    )


def row_to_stored(row: dict[str, Any]) -> StoredProjection:
    payload = row.get("payload")
    if isinstance(payload, str):
        import json

        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            payload = {}
    return StoredProjection(
        owner_user_id=row.get("owner_user_id"),
        resource_type=row.get("resource_type"),
        resource_identifier=row.get("resource_identifier"),
        kind=str(row.get("projection_kind") or ""),
        payload=payload if isinstance(payload, dict) else {},
        generated_at=row.get("generated_at"),
        expires_at=row.get("expires_at"),
    )


def load_projection(
    *, owner_user_id: uuid.UUID, resource_type: str, resource_identifier: str
) -> StoredProjection | None:
    if _store is None:
        return None
    canonical = canonical_resource_type(resource_type)
    if not canonical:
        return None
    row = _store.projection_get(
        owner_user_id=owner_user_id,
        resource_type=canonical,
        resource_identifier=resource_identifier,
    )
    return row_to_stored(row) if row else None


def load_fresh(
    adapter: Any,
    *,
    owner_user_id: uuid.UUID,
    resource_identifier: str,
    resource_type: str,
) -> ProjectionOutcome:
    """A usable projection, republishing through the adapter when needed.

    The grantee never names a kind. The kind comes from the stored row, so
    the shape stays whatever the owner chose; only a resource that has
    never been published falls back to the adapter's default.

    On a failed republish the stale row is returned with ``stale=True``
    rather than dropped. Serving a five-minute-old free/busy view beats
    failing a friend's question, but it is labelled — an answer that is
    quietly out of date is worse than one that says so. That fallback
    lasts only as long as the retention grace: past it the row stops
    being a very old answer and stops being an answer at all.

    Returns a ``ProjectionOutcome`` rather than a bare row so that a
    publish that failed for a reason worth telling the grantee — the owner
    has no calendar configured, say — survives the trip. Collapsing that
    into ``None`` makes a live grant look like no grant.
    """
    if not projection_backed(adapter):
        return ProjectionOutcome(None, "not_projection_backed")

    stored = load_projection(
        owner_user_id=owner_user_id,
        resource_type=resource_type,
        resource_identifier=resource_identifier,
    )
    if stored is not None and not stored.is_retained():
        # Out of retention, so this row is not available as a fallback and
        # is deleted on the way past. Enforced here rather than left to
        # the sweeper because the sweeper is a janitor: it makes the table
        # tidy eventually, and "eventually" is the kind of guarantee this
        # ADR exists because it kept not holding. A publish from here can
        # still succeed and put a fresh row back.
        drop_projection(
            owner_user_id=owner_user_id,
            resource_type=resource_type,
            resource_identifier=resource_identifier,
        )
        stored = None
    if stored is not None and stored.is_fresh():
        return ProjectionOutcome(stored)

    kind = stored.kind if stored and stored.kind else default_projection_kind(adapter)
    if not kind:
        return ProjectionOutcome(
            dataclass_replace(stored, stale=True) if stored else None, "no_projection_kind"
        )

    publish_error: str | None = None
    published: StoredProjection | None = None
    try:
        payload = adapter.publish_projection(
            owner_user_id=owner_user_id,
            identifier=resource_identifier,
            kind=kind,
        )
        if payload is not None:
            # Inside the guard on purpose. The credential check runs at the
            # door of the store, so a payload the store refuses has to be
            # caught here as well — otherwise a leak on the way in escapes
            # as an unhandled exception instead of falling back to the
            # last row that was known to be clean.
            published = store_projection(
                adapter,
                owner_user_id=owner_user_id,
                resource_type=resource_type,
                resource_identifier=resource_identifier,
                kind=kind,
                payload=payload,
            )
    except ShareProjectionPublishError as exc:
        publish_error = str(exc) or "publish_failed"
    except Exception:
        # Includes ShareProjectionError, i.e. the adapter tried to publish
        # something credential-shaped. Refusing to store it is the guard;
        # falling back to the stored row is not a bypass of that guard,
        # because every row in this store passed the same check on its way
        # in. The new payload stays refused, the old one is still safe.
        #
        # The message is deliberately generic on the way out: the exception
        # text names the offending key and, in a mis-written adapter, could
        # name the value too. The detail goes to the log, not to the
        # grantee.
        logger.exception("share projection publish failed for %s", resource_type)
        publish_error = "publish_refused"

    if published is not None:
        return ProjectionOutcome(published)
    if stored is not None:
        return ProjectionOutcome(dataclass_replace(stored, stale=True), publish_error)
    return ProjectionOutcome(None, publish_error or "publish_returned_nothing")


def drop_projection(
    *, owner_user_id: uuid.UUID, resource_type: str, resource_identifier: str
) -> int:
    if _store is None:
        return 0
    canonical = canonical_resource_type(resource_type)
    if not canonical:
        return 0
    return _store.projection_delete(
        owner_user_id=owner_user_id,
        resource_type=canonical,
        resource_identifier=resource_identifier,
    )
