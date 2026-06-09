"""Unit tests for per-provider LLM HTTP concurrency slots."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from apps.backend.infrastructure.llm_concurrency import (
    acquire_llm_slot,
    bind_llm_wait_notifier,
    invalidate_llm_concurrency_cache,
    llm_slot,
    max_parallel_for_provider,
    release_llm_slot,
    reset_llm_wait_notifier,
)


@pytest.fixture(autouse=True)
def _clear_concurrency_cache():
    invalidate_llm_concurrency_cache()
    yield
    invalidate_llm_concurrency_cache()


def test_max_parallel_clamps_to_64():
    with patch(
        "apps.backend.infrastructure.model_catalog_providers.get_provider_spec",
        return_value=type("S", (), {"max_parallel": 999})(),
    ):
        assert max_parallel_for_provider("provider_1") == 64


def test_max_parallel_default_when_provider_unknown():
    assert max_parallel_for_provider(None) >= 1


def test_llm_slot_blocks_when_at_limit():
    active = 0
    peak = 0
    lock = threading.Lock()
    gate = threading.Event()

    def worker():
        nonlocal active, peak
        with llm_slot("test_provider"):
            with lock:
                active += 1
                peak = max(peak, active)
            gate.wait(timeout=2)
            with lock:
                active -= 1

    with patch(
        "apps.backend.infrastructure.llm_concurrency.max_parallel_for_provider",
        return_value=2,
    ):
        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        deadline = time.time() + 2
        while time.time() < deadline:
            with lock:
                if active >= 2:
                    break
            time.sleep(0.01)
        with lock:
            assert active == 2
            assert peak == 2
        gate.set()
        for t in threads:
            t.join(timeout=3)
        assert peak == 2


def test_slot_wait_notifier_fires_when_blocked():
    import contextvars

    seen: list[dict] = []
    sem = threading.BoundedSemaphore(1)
    sem.acquire()
    token = bind_llm_wait_notifier(seen.append)
    ctx = contextvars.copy_context()

    def worker() -> None:
        ctx.run(acquire_llm_slot, "test_busy")

    try:
        with patch(
            "apps.backend.infrastructure.llm_concurrency._semaphore_for",
            return_value=sem,
        ), patch(
            "apps.backend.infrastructure.llm_concurrency.max_parallel_for_provider",
            return_value=1,
        ):
            t = threading.Thread(target=worker)
            t.start()
            t.join(timeout=3)
            assert seen
            assert seen[0]["type"] == "agent.llm_slot_wait"
    finally:
        sem.release()
        reset_llm_wait_notifier(token)
        t.join(timeout=1)
        release_llm_slot("test_busy")
