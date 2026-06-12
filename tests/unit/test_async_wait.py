"""Unit tests for generic deferred wait."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.domain.async_wait import parse_estimated_time_seconds, run_deferred_wait
from apps.backend.domain.security_scan.deferred import should_wait_for_scan


def test_parse_estimated_time_seconds_accepts_positive_int():
    assert parse_estimated_time_seconds({"estimated_time_seconds": 255}) == 255


def test_parse_estimated_time_seconds_null_when_missing_or_invalid():
    assert parse_estimated_time_seconds({}) is None
    assert parse_estimated_time_seconds({"estimated_time_seconds": 0}) is None
    assert parse_estimated_time_seconds({"estimated_time_seconds": "nope"}) is None


def test_should_wait_for_scan_when_estimate_present():
    assert should_wait_for_scan(
        {},
        None,
        st="pending",
        estimated_sec=120,
        scan_id="abc",
    )


def test_should_wait_for_scan_benchmark_without_estimate():
    ctx = {"benchmark_run_id": "bench-1"}
    assert should_wait_for_scan(
        {},
        ctx,
        st="pending",
        estimated_sec=None,
        scan_id="abc",
    )


def test_should_wait_for_scan_explicit_flag_without_estimate():
    assert should_wait_for_scan(
        {"wait_for_completion": True},
        None,
        st="running",
        estimated_sec=None,
        scan_id="abc",
    )


def test_should_wait_for_scan_skip_flag():
    assert not should_wait_for_scan(
        {"skip_scan_wait": True},
        {"benchmark_run_id": "bench-1"},
        st="pending",
        estimated_sec=120,
        scan_id="abc",
    )


def test_run_deferred_wait_polls_until_ready():
    seen: list[dict] = []
    ctx = {
        "deferred_wait_notify": seen.append,
    }
    responses = [
        ({"ok": True, "status": "running"}, "running"),
        ({"ok": True, "status": "ready"}, "ready"),
    ]

    def fake_poll():
        return responses.pop(0)

    with patch("apps.backend.domain.async_wait.time.sleep"), patch(
        "apps.backend.domain.async_wait.time.monotonic",
        side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
    ):
        out = run_deferred_wait(
            wait_id="scan-1",
            estimated_sec=5,
            context=ctx,
            initial_status="pending",
            poll_fn=fake_poll,
            terminal_ok=frozenset({"ready", "completed"}),
            terminal_fail=frozenset({"failed", "cancelled", "error"}),
            poll_interval_sec=1.0,
            wait_label="security_scan",
        )

    assert out["ok"] is True
    assert out["status"] == "ready"
    assert out["poll_count"] >= 1
    assert any(
        e.get("type") == "agent.deferred_wait" and e.get("phase") == "started" for e in seen
    )
    assert any(e.get("phase") == "ended" for e in seen)
