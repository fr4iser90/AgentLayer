"""Tests for the cron scheduler thread (``infrastructure/scheduling/cron.py``).

Nothing here tests job arithmetic beyond what the thread depends on. What is
under test is the thread around the jobs: a job marked RUN_ON_STARTUP runs
when the server starts rather than one poll interval later, an instance with
no scheduled jobs leaves no thread behind, and a job that is not due is left
alone while the loop keeps turning.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from apps.backend.infrastructure.scheduling import cron

_WORKER_NAME = "cron-scheduler"


def _live() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == _WORKER_NAME and t.is_alive()]


class _Registry:
    def __init__(self, jobs: list[dict[str, Any]]) -> None:
        self.jobs = jobs


@pytest.fixture()
def cron_worker(monkeypatch):
    """Run the real thread against a registry of the test's own jobs."""
    for thread in _live():  # pragma: no cover - guards against a leaked worker
        thread.join(timeout=2)

    def with_jobs(jobs: list[dict[str, Any]], *, poll_sec: float) -> None:
        monkeypatch.setattr(cron, "get_scheduled_job_registry", lambda: _Registry(jobs))
        monkeypatch.setattr(cron._worker, "poll_sec", poll_sec)
        cron.start_cron_scheduler()

    yield with_jobs

    cron.stop_cron_scheduler()


def _job(handler, *, name: str = "job", interval: float = 3600.0, run_on_start: bool = False):
    return {
        "name": name,
        "handler": handler,
        "interval_seconds": interval,
        "run_on_start": run_on_start,
        "last_run": 0,
    }


def test_a_run_on_startup_job_runs_without_waiting_for_a_poll(cron_worker) -> None:
    ran = threading.Event()
    cron_worker([_job(lambda _payload: ran.set(), run_on_start=True)], poll_sec=600.0)
    assert ran.wait(5.0), "RUN_ON_STARTUP waited for the poll interval"


def test_a_job_that_defers_its_first_run_is_only_stamped(cron_worker) -> None:
    calls: list[int] = []
    job = _job(lambda _payload: calls.append(1), run_on_start=False, interval=3600.0)
    cron_worker([job], poll_sec=600.0)

    deadline = time.monotonic() + 5.0
    while job["last_run"] == 0 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert job["last_run"] != 0, "the deferred first run was never scheduled"
    assert calls == [], "a job with RUN_ON_STARTUP=false ran at boot anyway"


def test_a_job_comes_round_again_once_its_interval_has_passed(cron_worker) -> None:
    ran = threading.Event()
    cron_worker(
        [_job(lambda _payload: ran.set(), interval=0.05, run_on_start=True)],
        poll_sec=0.01,
    )
    assert ran.wait(5.0), "the job never ran"
    ran.clear()
    assert ran.wait(5.0), "the job ran once and never came round again"


def test_an_instance_with_no_jobs_leaves_no_thread_behind(cron_worker) -> None:
    cron_worker([], poll_sec=0.01)
    deadline = time.monotonic() + 5.0
    while _live() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert _live() == [], "the cron thread outlived having nothing to poll"
