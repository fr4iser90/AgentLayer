"""The background half of the projection subsystem.

``projections`` holds the contract: what may be stored, how fresh a row is,
what a reader gets. This module holds the part that runs when nobody is
reading — the pass that republishes rows before their bound arrives, and
the sweeper that finally drops rows that outlived their retention.

The split is not cosmetic. The contract module must not know that a worker
exists; a reader should not have to reason about batch sizing, upstream
poll rates, or which grants are still live. Those are all questions about
*when to spend a fetch*, which only matters in the background — on the
read path the answer is always "now, because someone is waiting".

Two things this module deliberately does not do:

**It does not delete what it cannot refresh.** A row whose adapter is gone,
or whose upstream is down, is left alone. The freshness bound and the
retention grace in ``projections`` remove rows through one mechanism; a
second delete path with its own idea of when owner data is expendable is
how you get a data-loss bug that looks like maintenance.

**It does not treat "unknown" as "none".** The live-grant lookup is
injected and may be unwired or failing. Only a *counted zero* skips a
row, because the failure mode of getting this wrong — a missing
registration silently stopping every projection from being refreshed, or
worse, being read as "nobody may see this" — is much worse than the waste
it was written to prevent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from apps.backend.domain.shares.projections import (
    STALE_GRACE_SECONDS,
    projection_backed,
    projection_store,
    projection_ttl_seconds,
    row_to_stored,
)

logger = logging.getLogger(__name__)


# "How many live grants still name this resource", supplied by
# infrastructure from wherever grants actually live. The projection domain
# has no business reading share_permissions itself, but it does need to
# know whether anything it is about to spend a fetch on can be read by
# anyone. That is a projection-policy question; it just cannot be answered
# from inside this module.
_grant_counter: Callable[[uuid.UUID, str, str], int] | None = None


def register_live_grant_counter(fn: Callable[[uuid.UUID, str, str], int]) -> None:
    """Wire the grant lookup the refresh pass consults."""
    global _grant_counter
    _grant_counter = fn


def live_grant_count(
    owner_user_id: uuid.UUID, resource_type: str, resource_identifier: str
) -> int | None:
    """Live grants naming this resource, or ``None`` if nobody can say.

    ``None`` is a real answer and the safe one. With the lookup unwired,
    or failing, treating unknown as zero would turn a missing registration
    into a mass drop of owner-published data — the one failure mode this
    subsystem has been careful not to have.
    """
    if _grant_counter is None:
        return None
    try:
        return int(_grant_counter(owner_user_id, resource_type, resource_identifier))
    except Exception:
        logger.exception(
            "live grant count lookup failed for %s/%s", resource_type, resource_identifier
        )
        return None


def sweep_expired(
    *, limit: int = 200, grace_seconds: int = STALE_GRACE_SECONDS
) -> int:
    """Delete projections past their bound plus the retention grace.

    A garbage collector, not a correctness mechanism: ``load_fresh``
    refuses an out-of-retention row itself, so sweeping only stops rows
    that nobody read from accumulating.

    The grace is part of the predicate rather than zero. Sweeping on
    ``expires_at <= now()`` would delete exactly the rows a failed
    refresh has just produced — the stale fallback that lets a friend
    still be answered while the owner's upstream is down — and a janitor
    that quietly removes a guarantee looks a lot like a janitor that
    worked.
    """
    store = projection_store()
    if store is None:
        return 0
    return store.projection_delete_expired(
        limit=limit, grace_seconds=max(0, int(grace_seconds))
    )


@dataclass(frozen=True)
class RefreshReport:
    """What one refresh pass did, so the log can say so usefully.

    ``failed`` counts rows that are still stale after trying. That is not
    an error state to escalate on — the owner's upstream may be down for
    an hour — but a pass that refreshed nothing and failed on everything
    is the shape that tells you something is wrong.
    """

    refreshed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def touched(self) -> int:
        return self.refreshed + self.failed + self.skipped


def refresh_due(*, limit: int = 20, within_seconds: int = 300) -> RefreshReport:
    """Republish projections that are expired, or close enough to matter.

    The window is the whole point. A row that expires in two minutes is
    worth refreshing *now*, because the alternative is that the next
    friend who asks sits through the owner's source round-trip before
    getting an answer. Refreshing only after expiry leaves exactly that
    reader paying, which is the cost this pass exists to remove.

    That is also why this publishes through the registry rather than
    calling ``load_fresh``: ``load_fresh`` short-circuits on a row that
    is still fresh, which is right for a reader and exactly wrong for a
    worker whose entire job is to act before the bound arrives.

    A row is republished at most once per half of its own freshness life,
    however wide the caller's window. Without that bound, a window wider
    than the TTL would leave every row due on every pass and turn a
    refresh into a continuous poll of the owner's upstream — the opposite
    of what a background worker should be.

    Rows whose adapter is gone are skipped, never deleted. Such a
    projection is already unservable, since nothing resolves its type, and
    wiping owner data because a registration step went missing turns a
    wiring bug into data loss. The freshness bound takes care of it.
    """
    store = projection_store()
    if store is None:
        return RefreshReport()

    # Imported here rather than at module scope: the registry imports this
    # module to reach the projection helpers, so the reverse edge has to be
    # lazy or the two cannot be loaded in either order.
    from apps.backend.domain.shares.registry import get_share_adapter, publish_projection

    try:
        window = max(60, min(int(within_seconds), 24 * 60 * 60))
    except (TypeError, ValueError):
        window = 300
    try:
        capped = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        capped = 20

    now = datetime.now(timezone.utc)
    refreshed = failed = skipped = 0
    for row in store.projection_list_due(limit=capped, within_seconds=window):
        stored = row_to_stored(row)
        adapter = get_share_adapter(stored.resource_type)
        if adapter is None or not projection_backed(adapter):
            skipped += 1
            continue

        if live_grant_count(
            stored.owner_user_id, stored.resource_type, stored.resource_identifier
        ) == 0:
            # Nobody holds a grant that can read this. Skipping the
            # refresh rather than deleting outright means the freshness
            # bound and the retention grace remove the row through the
            # machinery that already exists, instead of a second delete
            # path with its own idea of when owner data is expendable.
            # Only a counted zero skips: an unwired lookup returns None,
            # and unknown is not the same as none.
            skipped += 1
            continue

        expires = stored.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires is not None:
            remaining = (expires - now).total_seconds()
            if remaining > min(window, projection_ttl_seconds(adapter) / 2):
                skipped += 1
                continue

        try:
            # The stored kind is passed through explicitly. A worker that
            # fell back to the adapter default would silently widen a
            # free/busy projection to a titled-event list on a schedule,
            # with nobody having chosen it.
            outcome = publish_projection(
                resource_type=stored.resource_type,
                owner_user_id=stored.owner_user_id,
                identifier=stored.resource_identifier,
                kind=stored.kind or None,
            )
        except Exception:
            # Includes the store refusing a credential-shaped payload.
            # The previous row is untouched either way, which is the whole
            # reason the credential gate runs at the door of the store.
            logger.exception(
                "share projection refresh raised for %s/%s",
                stored.resource_type,
                stored.resource_identifier,
            )
            failed += 1
            continue

        if outcome.served:
            refreshed += 1
            continue

        failed += 1
        logger.info(
            "share projection still stale after refresh: %s/%s (%s)",
            stored.resource_type,
            stored.resource_identifier,
            outcome.refusal or "unknown",
        )

    return RefreshReport(refreshed=refreshed, failed=failed, skipped=skipped)
