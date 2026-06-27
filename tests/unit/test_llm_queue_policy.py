"""Unit tests for LLM slot queue policy."""

from __future__ import annotations

import threading
import time
import uuid
from unittest.mock import patch

import pytest

from apps.backend.domain.shared.identity import (
    reset_benchmark_run_id,
    reset_identity,
    reset_llm_queue_source,
    set_benchmark_run_id,
    set_identity,
    set_llm_queue_source,
)
from apps.backend.infrastructure.agent_runtime.llm_concurrency import (
    acquire_llm_slot,
    invalidate_llm_concurrency_cache,
    release_llm_slot,
)
from apps.backend.infrastructure.agent_runtime.llm_queue_policy import (
    QueueConfig,
    load_queue_config,
    resolve_waiter_meta,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_llm_concurrency_cache()
    yield
    invalidate_llm_concurrency_cache()


def test_resolve_waiter_meta_benchmark_lower_than_user():
    uid = uuid.uuid4()
    bench = uuid.uuid4()
    id_tok = set_identity(1, uid)
    cfg = QueueConfig(
        policy="priority",
        user_priority=100,
        benchmark_priority=10,
        scheduler_priority=50,
    )
    try:
        with patch("apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config", return_value=cfg):
            user_meta = resolve_waiter_meta()
        assert user_meta.queue_class == "user"
        assert user_meta.priority == 100

        bench_tok = set_benchmark_run_id(bench)
        try:
            with patch("apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config", return_value=cfg):
                bench_meta = resolve_waiter_meta()
            assert bench_meta.queue_class == "benchmark"
            assert bench_meta.priority == 10
            assert bench_meta.priority < user_meta.priority
        finally:
            reset_benchmark_run_id(bench_tok)
    finally:
        reset_identity(id_tok)


def test_user_served_before_benchmark_when_both_waiting():
    uid = uuid.uuid4()
    bench_id = uuid.uuid4()
    cfg = QueueConfig(
        policy="priority",
        user_priority=100,
        benchmark_priority=10,
        scheduler_priority=50,
    )
    order: list[str] = []
    lock = threading.Lock()

    def wait_acquire(name: str, bench: uuid.UUID | None) -> None:
        id_tok = set_identity(1, uid)
        bench_tok = set_benchmark_run_id(bench) if bench is not None else None
        try:
            with patch(
                "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
                return_value=1,
            ), patch(
                "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
                return_value=cfg,
            ):
                acquire_llm_slot("prio_test")
                with lock:
                    order.append(name)
                release_llm_slot("prio_test")
        finally:
            if bench_tok is not None:
                reset_benchmark_run_id(bench_tok)
            reset_identity(id_tok)

    with patch(
        "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
        return_value=1,
    ), patch(
        "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
        return_value=cfg,
    ):
        acquire_llm_slot("prio_test")
        t_bench = threading.Thread(target=wait_acquire, args=("benchmark", bench_id))
        t_user = threading.Thread(target=wait_acquire, args=("user", None))
        t_bench.start()
        t_user.start()
        time.sleep(0.2)
        release_llm_slot("prio_test")
        t_user.join(timeout=5)
        t_bench.join(timeout=5)

    with lock:
        assert order[0] == "user"
        assert "benchmark" in order


def test_two_users_round_robin_within_priority_tier():
    uid_a = uuid.uuid4()
    uid_b = uuid.uuid4()
    cfg = QueueConfig(
        policy="priority",
        user_priority=100,
        benchmark_priority=10,
        scheduler_priority=50,
    )
    order: list[str] = []
    lock = threading.Lock()

    def wait_as(user_id: uuid.UUID, label: str) -> None:
        id_tok = set_identity(1, user_id)
        try:
            with patch(
                "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
                return_value=1,
            ), patch(
                "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
                return_value=cfg,
            ):
                acquire_llm_slot("rr_test")
                with lock:
                    order.append(label)
                release_llm_slot("rr_test")
        finally:
            reset_identity(id_tok)

    with patch(
        "apps.backend.infrastructure.agent_runtime.llm_concurrency.max_parallel_for_provider",
        return_value=1,
    ), patch(
        "apps.backend.infrastructure.agent_runtime.llm_queue_policy.load_queue_config",
        return_value=cfg,
    ):
        acquire_llm_slot("rr_test")
        t_a = threading.Thread(target=wait_as, args=(uid_a, "a"))
        t_b = threading.Thread(target=wait_as, args=(uid_b, "b"))
        t_a.start()
        t_b.start()
        time.sleep(0.2)
        release_llm_slot("rr_test")
        t_a.join(timeout=5)
        t_b.join(timeout=5)
        release_llm_slot("rr_test")

    with lock:
        assert len(order) == 2
        assert order[0] in ("a", "b")
        assert order[1] in ("a", "b")
        assert order[0] != order[1]


def test_load_queue_config_defaults_when_unknown_policy(monkeypatch):
    monkeypatch.setattr(
        "apps.backend.infrastructure.settings.operator_settings._cached_row",
        lambda: {"llm_queue_policy": "unknown"},
    )
    cfg = load_queue_config()
    assert cfg.policy == "priority"
