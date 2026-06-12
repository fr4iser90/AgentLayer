"""Unit tests for SimpleSecCheck scan wait helper."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.domain.security_scan.wait import (
    parse_estimated_time_seconds,
    should_wait_for_scan,
    wait_for_scan_completion,
)


def test_parse_estimated_time_seconds_accepts_positive_int():
    assert parse_estimated_time_seconds({"estimated_time_seconds": 255}) == 255


def test_parse_estimated_time_seconds_null_when_missing_or_invalid():
    assert parse_estimated_time_seconds({}) is None
    assert parse_estimated_time_seconds({"estimated_time_seconds": 0}) is None
    assert parse_estimated_time_seconds({"estimated_time_seconds": "nope"}) is None


def test_should_wait_for_scan_benchmark_auto_when_estimate():
    ctx = {"benchmark_run_id": "bench-1"}
    assert should_wait_for_scan(
        {},
        ctx,
        st="pending",
        estimated_sec=120,
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


def test_should_wait_for_scan_skip_flag_in_benchmark():
    ctx = {"benchmark_run_id": "bench-1"}
    assert not should_wait_for_scan(
        {"skip_scan_wait": True},
        ctx,
        st="pending",
        estimated_sec=120,
        scan_id="abc",
    )


def test_wait_for_scan_completion_polls_until_ready():
    seen: list[dict] = []
    ctx = {
        "scan_wait_notify": seen.append,
    }
    responses = [
        (200, {"status": "running", "estimated_time_seconds": 10}, "running"),
        (200, {"status": "ready", "estimated_time_seconds": None}, "ready"),
    ]

    def fake_fetch(scan_id: str):
        return responses.pop(0)

    with patch(
        "apps.backend.domain.security_scan.wait.fetch_scan_status",
        side_effect=fake_fetch,
    ), patch("apps.backend.domain.security_scan.wait.time.sleep"), patch(
        "apps.backend.domain.security_scan.wait.time.monotonic",
        side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
    ):
        out = wait_for_scan_completion(
            "scan-1",
            estimated_sec=5,
            context=ctx,
            initial_status="pending",
            poll_interval_sec=1.0,
        )

    assert out["ok"] is True
    assert out["status"] == "ready"
    assert out["poll_count"] >= 1
    assert any(e.get("type") == "agent.scan_wait" and e.get("phase") == "started" for e in seen)
    assert any(e.get("phase") == "ended" for e in seen)
