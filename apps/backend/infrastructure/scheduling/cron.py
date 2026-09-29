"""
Background cron scheduler for **scheduled jobs** (HANDLERS + RUN_EVERY_MINUTES in tool dirs).

Not the same as: LLM tools, ComfyUI graphs, or future user-defined step workflows.
"""

from __future__ import annotations

import asyncio
import time
import logging
from typing import Any

from apps.backend.domain.plugin_system.scheduled_job_registry import get_scheduled_job_registry
from apps.backend.infrastructure.platform.poll_loop import PollLoop

logger = logging.getLogger(__name__)

_jobs: list[dict[str, Any]] = []


def _collect_jobs() -> bool:
    """Take the job list once, on the scheduler thread.

    The registry is a lazy singleton filled while plugins load, so by the time
    this runs it will not change again — with no jobs there is nothing to poll
    for and the thread has no reason to exist.
    """
    global _jobs
    _jobs = get_scheduled_job_registry().jobs
    if not _jobs:
        logger.info("No cron jobs found, scheduler exiting")
        return False
    return True


def _run_due_jobs() -> None:
    now = time.time()

    for job in _jobs:
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


_worker = PollLoop(
    name="cron-scheduler",
    iteration=_run_due_jobs,
    poll_sec=10.0,
    join_sec=10.0,
    startup=_collect_jobs,
    # RUN_ON_STARTUP jobs are due the moment the process is up, not 10 seconds later.
    run_first_pass_immediately=True,
    failure_log="cron scheduler pass failed",
)


def start_cron_scheduler() -> None:
    """Start background cron scheduler thread."""
    _worker.start()


def stop_cron_scheduler() -> None:
    """Stop background cron scheduler thread."""
    _worker.stop()
