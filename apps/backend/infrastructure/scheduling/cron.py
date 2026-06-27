"""
Background cron scheduler for **scheduled jobs** (HANDLERS + RUN_EVERY_MINUTES in tool dirs).

Not the same as: LLM tools, ComfyUI graphs, or future user-defined step workflows.
"""

from __future__ import annotations

import asyncio
import threading
import time
import logging
from typing import Any

from apps.backend.domain.plugin_system.scheduled_job_registry import get_scheduled_job_registry

logger = logging.getLogger(__name__)

_cron_thread: threading.Thread | None = None
_stop_event = threading.Event()


def start_cron_scheduler() -> None:
    """Start background cron scheduler thread."""
    global _cron_thread

    if _cron_thread is not None and _cron_thread.is_alive():
        return

    _stop_event.clear()
    _cron_thread = threading.Thread(target=_cron_worker, daemon=True, name="cron-scheduler")
    _cron_thread.start()


def stop_cron_scheduler() -> None:
    """Stop background cron scheduler thread."""
    _stop_event.set()
    if _cron_thread is not None:
        _cron_thread.join(timeout=10)


def _cron_worker() -> None:
    logger.info("Cron scheduler started")
    registry = get_scheduled_job_registry()
    cron_jobs = registry.jobs

    if not cron_jobs:
        logger.info("No cron jobs found, scheduler exiting")
        return

    while not _stop_event.is_set():
        now = time.time()

        for job in cron_jobs:
            name = job["name"]
            last_run = job["last_run"]
            interval = job["interval_seconds"]
            run_on_start = job["run_on_start"]

            # last_run == 0 means "never run". Interval check must not use 0 as epoch
            # (would be now - 0 ≈ huge → always run). Respect RUN_ON_STARTUP on first tick.
            if last_run == 0:
                if run_on_start:
                    logger.info("Executing cron job (RUN_ON_STARTUP): %s", name)
                else:
                    job["last_run"] = now
                    logger.info(
                        "Cron job %s: deferred first run (RUN_ON_STARTUP=false); "
                        "next run after %.0f min",
                        name,
                        interval / 60.0,
                    )
                    continue

                try:
                    result = job["handler"]({})
                    if asyncio.iscoroutine(result):
                        result = asyncio.run(result)
                    logger.debug(
                        "Cron job %s completed: %s", name, str(result)[:120]
                    )
                except Exception:
                    logger.exception("Cron job %s failed", name)

                job["last_run"] = now
                continue

            if now - last_run < interval:
                continue

            logger.info("Executing cron job: %s", name)

            try:
                result = job["handler"]({})
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                logger.debug(
                    "Cron job %s completed: %s", name, str(result)[:120]
                )
            except Exception:
                logger.exception("Cron job %s failed", name)

            job["last_run"] = now

        # Sleep 10 seconds between checks
        _stop_event.wait(timeout=10)

    logger.info("Cron scheduler stopped")