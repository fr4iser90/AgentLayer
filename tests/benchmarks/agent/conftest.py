"""Pytest fixtures for live agent benchmarks."""

from __future__ import annotations

import pytest

from tests.benchmarks.agent.harness import load_bench_env, require_server
from tests.benchmarks.agent.live_gate import skip_reason_if_not_live


@pytest.fixture(scope="session")
def bench_live() -> None:
    reason = skip_reason_if_not_live()
    if reason:
        pytest.skip(reason)
    load_bench_env()
    try:
        require_server()
    except RuntimeError as exc:
        pytest.skip(str(exc))
