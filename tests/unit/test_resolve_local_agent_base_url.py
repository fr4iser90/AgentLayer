"""Unit tests for localhost Agent Layer URL resolution (Docker vs host dev)."""

from __future__ import annotations

import pytest

from tests.e2e.support.helpers import resolve_local_agent_base_url


def test_resolve_prefers_bench_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_BENCH_BASE_URL", "http://bench.example:9000")
    monkeypatch.setenv("AGENT_E2E_BASE_URL", "http://127.0.0.1:8088")
    assert resolve_local_agent_base_url() == "http://bench.example:9000"


def test_resolve_probes_before_stale_e2e_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_BENCH_BASE_URL", raising=False)
    monkeypatch.setenv("AGENT_E2E_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("AGENT_HTTP_PORT", "8088")

    calls: list[str] = []

    def fake_health(url: str, *, timeout: float = 1.5) -> bool:
        calls.append(url)
        return url == "http://127.0.0.1:8080"

    monkeypatch.setattr("tests.e2e.support.helpers._local_health_ok", fake_health)
    assert resolve_local_agent_base_url() == "http://127.0.0.1:8080"
    assert "http://127.0.0.1:8080" in calls


def test_resolve_falls_back_to_e2e_env_when_no_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_BENCH_BASE_URL", raising=False)
    monkeypatch.setenv("AGENT_E2E_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setattr("tests.e2e.support.helpers._local_health_ok", lambda *_a, **_k: False)
    assert resolve_local_agent_base_url() == "http://127.0.0.1:8088"
