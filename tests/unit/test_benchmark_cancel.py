"""Benchmark run cancellation helpers."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.backend.infrastructure.benchmark_runner import (
    _cancel_check_for,
    _clear_cancel_flag,
    request_benchmark_cancel,
)


def test_request_benchmark_cancel_sets_flag() -> None:
    run_id = uuid.uuid4()
    row = {"status": "running", "tenant_id": 1}
    with patch(
        "apps.backend.infrastructure.benchmark_runner.benchmark_runs_store.get_run",
        return_value=row,
    ):
        assert request_benchmark_cancel(run_id) is True
    assert _cancel_check_for(run_id)() is True
    _clear_cancel_flag(run_id)
    assert _cancel_check_for(run_id)() is False


def test_request_benchmark_cancel_inactive_run() -> None:
    run_id = uuid.uuid4()
    with patch(
        "apps.backend.infrastructure.benchmark_runner.benchmark_runs_store.get_run",
        return_value={"status": "completed"},
    ):
        assert request_benchmark_cancel(run_id) is False
