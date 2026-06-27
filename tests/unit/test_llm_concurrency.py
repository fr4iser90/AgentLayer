"""Unit tests for per-provider LLM HTTP concurrency slots."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from apps.backend.infrastructure.agent_runtime.llm_concurrency import (
    acquire_llm_slot,
    bind_llm_wait_notifier,
    invalidate_llm_concurrency_cache,
    llm_slot,
    max_parallel_for_provider,
    release_llm_slot,
    reset_llm_wait_notifier,
)
from apps.backend.infrastructure.agent_runtime.llm_queue_policy import QueueConfig


@pytest.fixture(autouse=True)
def _clear_concurrency_cache():
    invalidate_llm_concurrency_cache()
    yield
    invalidate_llm_concurrency_cache()


def _fifo_cfg() -> QueueConfig:
    return QueueConfig(
        policy="fifo",
        user_priority=100,
        benchmark_priority=10,
        scheduler_priority=50,
    )


def test_max_parallel_clamps_to_64():
    with patch(
        "apps.backend.infrastructure.providers.model_catalog_providers.get_provider_spec",
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
        with patch(
            "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
            return_value=2,
        ), patch(
            "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
            return_value=_fifo_cfg(),
        ):
            with llm_slot("test_provider"):
                with lock:
                    active += 1
                    peak = max(peak, active)
                gate.wait(timeout=2)
                with lock:
                    active -= 1

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
    token = bind_llm_wait_notifier(seen.append)
    ctx = contextvars.copy_context()

    def worker() -> None:
        ctx.run(_worker_acquire)

    def _worker_acquire() -> None:
        with patch(
            "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
            return_value=1,
        ), patch(
            "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
            return_value=_fifo_cfg(),
        ):
            acquire_llm_slot("test_busy")

    try:
        with patch(
            "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
            return_value=1,
        ), patch(
            "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
            return_value=_fifo_cfg(),
        ):
            acquire_llm_slot("test_busy")
            t = threading.Thread(target=worker)
            t.start()
            t.join(timeout=3)
            assert seen
            assert seen[0]["type"] == "agent.llm_slot_wait"
            assert "queue_ahead" in seen[0]
            assert "queue_size" in seen[0]
            release_llm_slot("test_busy")
            t.join(timeout=2)
            release_llm_slot("test_busy")
    finally:
        reset_llm_wait_notifier(token)


def test_slot_wait_queue_reports_position():
    seen: list[dict] = []
    lock = threading.Lock()
    threads: list[threading.Thread] = []

    def worker() -> None:
        def _note(payload: dict) -> None:
            with lock:
                seen.append(payload)

        tok = bind_llm_wait_notifier(_note)
        try:
            with patch(
                "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
                return_value=1,
            ), patch(
                "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
                return_value=_fifo_cfg(),
            ):
                acquire_llm_slot("test_busy")
        finally:
            reset_llm_wait_notifier(tok)

    try:
        with patch(
            "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
            return_value=1,
        ), patch(
            "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
            return_value=_fifo_cfg(),
        ):
            acquire_llm_slot("test_busy")
            for _ in range(2):
                t = threading.Thread(target=worker)
                threads.append(t)
                t.start()
            deadline = time.time() + 3
            while time.time() < deadline:
                with lock:
                    if len(seen) >= 2:
                        break
                time.sleep(0.05)
            with lock:
                assert len(seen) >= 2
                sizes = {e.get("queue_size") for e in seen if e.get("queue_size")}
                assert any(s and s >= 2 for s in sizes)
            release_llm_slot("test_busy")
            for t in threads:
                t.join(timeout=2)
                release_llm_slot("test_busy")
    finally:
        pass
