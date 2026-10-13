"""Tests for the one poll loop every background worker now shares.

The workers' own logic is tested where it lives; these tests are about the
thread around it, because every worker depends on the same four things:
starting twice does not double the work, stop interrupts a long wait instead
of waiting for it, a pass that raises does not end the worker, and a worker
can see that it was asked to stop while it is still inside a pass.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from apps.backend.infrastructure.platform.poll_loop import PollLoop

_TIMEOUT = 5.0


def _live(name: str) -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == name and t.is_alive()]


@pytest.fixture()
def make_loop() -> Iterator[Callable[..., PollLoop]]:
    started: list[PollLoop] = []

    def _make(**kwargs: Any) -> PollLoop:
        loop = PollLoop(**kwargs)
        started.append(loop)
        return loop

    yield _make
    for loop in started:
        loop.stop()
        assert _live(loop.name) == [], f"{loop.name} outlived its stop"


def test_starting_twice_leaves_one_worker_running(make_loop) -> None:
    name = "test-poll-loop-single"
    first_pass = threading.Event()

    def pass_once() -> None:
        first_pass.set()

    loop = make_loop(name=name, poll_sec=0.01, iteration=pass_once)
    loop.start()
    assert first_pass.wait(_TIMEOUT), "the loop never ran a pass"
    loop.start()
    assert len(_live(name)) == 1


def test_stop_interrupts_a_wait_that_is_not_due(make_loop) -> None:
    name = "test-poll-loop-stop-waiting"
    ran = threading.Event()

    def pass_once() -> None:
        ran.set()

    loop = make_loop(
        name=name,
        poll_sec=600.0,
        join_sec=2.0,
        iteration=pass_once,
        run_first_pass_immediately=True,
    )
    loop.start()
    assert ran.wait(_TIMEOUT), "the first pass never ran"

    began = time.monotonic()
    loop.stop()
    assert _live(name) == [], "the worker was still alive after stop returned"
    assert time.monotonic() - began < 2.0, "stop waited for the poll interval"


def test_a_pass_that_raises_does_not_end_the_worker(make_loop) -> None:
    name = "test-poll-loop-raises"
    attempts: list[int] = []
    third = threading.Event()

    def pass_once() -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("database went away mid-pass")
        third.set()

    loop = make_loop(name=name, poll_sec=0.01, iteration=pass_once)
    loop.start()
    assert third.wait(_TIMEOUT), "a raising pass ended the worker"
    assert len(attempts) >= 3


def test_a_worker_can_see_the_stop_while_it_is_still_working(make_loop) -> None:
    name = "test-poll-loop-mid-pass"
    entered = threading.Event()
    asked: list[bool] = []

    loop: PollLoop | None = None

    def batch() -> None:
        assert loop is not None
        asked.append(loop.stopping())
        entered.set()
        while not loop.stopping():
            time.sleep(0.005)
        asked.append(loop.stopping())

    loop = make_loop(name=name, poll_sec=0.01, join_sec=2.0, iteration=batch)
    loop.start()
    assert entered.wait(_TIMEOUT), "the worker never entered a pass"
    loop.stop()

    # First the worker was not stopping, then it was, and it left the pass
    # there instead of running on to the next thing it had queued.
    assert asked == [False, True]


def test_startup_can_end_the_thread_before_any_pass(make_loop) -> None:
    name = "test-poll-loop-nothing-to-do"
    passes: list[int] = []
    closed = threading.Event()

    def nothing_to_poll() -> bool:
        return False

    def close() -> None:
        closed.set()

    loop = make_loop(
        name=name,
        poll_sec=0.01,
        join_sec=2.0,
        iteration=lambda: passes.append(1),
        startup=nothing_to_poll,
        shutdown=close,
    )
    loop.start()
    assert closed.wait(_TIMEOUT), "shutdown did not run when startup declined"
    assert passes == []
    assert _live(name) == []


def test_a_worker_that_must_act_now_does_not_wait_first(make_loop) -> None:
    name = "test-poll-loop-immediate"
    ran = threading.Event()

    loop = make_loop(
        name=name,
        poll_sec=600.0,
        join_sec=2.0,
        iteration=lambda: ran.set(),
        run_first_pass_immediately=True,
    )
    loop.start()
    assert ran.wait(_TIMEOUT), "the first pass waited for the poll interval"


def test_a_worker_that_waits_first_holds_its_first_pass(make_loop) -> None:
    name = "test-poll-loop-waits-first"
    ran = threading.Event()

    make_loop(
        name=name,
        poll_sec=600.0,
        join_sec=2.0,
        iteration=lambda: ran.set(),
    ).start()
    assert not ran.wait(0.3), "the first pass ran before the poll interval"
