"""Unit tests for generic deferred wait."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.domain.agent_runtime.async_wait import parse_estimated_time_seconds, run_deferred_wait

# Scanner API payloads — estimated_time_seconds is always from SSC, never invented here.
_SSC_PENDING = {
    "status": "pending",
    "scan_id": "scan-abc",
    "estimated_time_seconds": 255,
}
_SSC_RUNNING_NO_ESTIMATE = {
    "status": "running",
    "scan_id": "scan-abc",
}


def _estimate_from_scanner(api_data: dict) -> int | None:
    return parse_estimated_time_seconds(api_data)


def test_parse_estimated_time_seconds_accepts_positive_int():
    assert _estimate_from_scanner(_SSC_PENDING) == 255


def test_parse_estimated_time_seconds_null_when_missing_or_invalid():
    assert parse_estimated_time_seconds({}) is None
    assert parse_estimated_time_seconds({"estimated_time_seconds": 0}) is None
    assert parse_estimated_time_seconds({"estimated_time_seconds": "nope"}) is None
    assert _estimate_from_scanner(_SSC_RUNNING_NO_ESTIMATE) is None


def test_run_deferred_wait_polls_until_ready():
    seen: list[dict] = []
    ctx = {
        "deferred_wait_notify": seen.append,
    }
    est = _estimate_from_scanner(_SSC_PENDING)
    responses = [
        ({"ok": True, "status": "running"}, "running"),
        ({"ok": True, "status": "ready"}, "ready"),
    ]

    def fake_poll():
        return responses.pop(0)

    with patch("apps.backend.domain.agent_runtime.async_wait.time.sleep"), patch(
        "apps.backend.domain.agent_runtime.async_wait.time.monotonic",
        side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
    ):
        out = run_deferred_wait(
            wait_id=_SSC_PENDING["scan_id"],
            estimated_sec=est,
            context=ctx,
            initial_status=_SSC_PENDING["status"],
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
