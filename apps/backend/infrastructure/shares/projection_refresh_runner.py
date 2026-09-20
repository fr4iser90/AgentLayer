"""Keep published share projections fresh off the read path (ADR 0014 step 7).

A projection past its TTL is never served: ``load_fresh`` republishes
instead. So without this worker the first friend to ask after the TTL
pays for the owner's source round-trip before they get an answer. This
moves that cost to a moment when nobody is waiting.

Nothing here is load-bearing for correctness. Every guarantee the share
model makes — nothing credential-shaped at rest, nothing served past the
bound, a revoked grant stops being readable immediately — holds with this
worker never running. What it buys is latency, which is why it starts as
optional, is gated on the friend system being enabled at all, and logs
rather than raises.

It also sweeps, and only became safe to once the retention grace existed.
Sweeping on ``expires_at <= now()`` deletes exactly the rows a failed
refresh produces — the stale fallback a grantee is answered from while
the owner's upstream is down — so a janitor wired to this heartbeat
would have removed a guarantee and looked like it worked. With the grace
in the predicate, the rows it collects are ones the read path has
already refused on its own.
"""

from __future__ import annotations

import logging
import threading

from apps.backend.domain.shares import projections
from apps.backend.infrastructure.settings import operator_settings

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None

# Poll often enough that a five-minute window is actually caught inside it,
# and cheap enough that an empty pass costs one indexed query.
_POLL_SEC = 90.0

# Rows expiring within this window get republished now, so the reader after
# the bound finds a fresh row instead of triggering the fetch themselves.
_WINDOW_SEC = 240

_MAX_BATCH = 20

# The sweep is housekeeping rather than freshness, so it rides every Nth
# pass instead of every one. Nothing waits on it, and rows it removes have
# already been refused at the read.
_SWEEP_EVERY = 8


def start_projection_refresh_worker() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_worker_loop, daemon=True, name="share-projection-refresh-worker"
    )
    _thread.start()


def stop_projection_refresh_worker() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=20)


def _worker_loop() -> None:
    logger.info("share projection refresh worker started")
    passes = 0
    while not _stop.is_set():
        if _stop.wait(timeout=_POLL_SEC):
            break
        try:
            if not operator_settings.friend_system_enabled():
                continue
            if not projections.projection_store_ready():
                continue
            passes += 1
            report = projections.refresh_due(
                limit=_MAX_BATCH, within_seconds=_WINDOW_SEC
            )
            if report.touched:
                logger.info(
                    "share projections refreshed=%s failed=%s skipped=%s",
                    report.refreshed,
                    report.failed,
                    report.skipped,
                )
            if passes % _SWEEP_EVERY == 0:
                swept = projections.sweep_expired()
                if swept:
                    logger.info(
                        "share projections swept out of retention=%s", swept
                    )
        except Exception:
            logger.exception("share projection refresh worker iteration failed")
    logger.info("share projection refresh worker stopped")
