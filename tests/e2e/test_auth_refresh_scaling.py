"""
E2E: prove login-page slowness from O(n) bcrypt in validate_refresh_token.

Each test uses HTTP only against a running Agent Layer (docker :8088).
Fails with exact file/line when refresh latency scales with login/session count.
"""

from __future__ import annotations

import pytest

from tests.e2e.auth_refresh_scaling_lib import (
    format_failure,
    is_bug_confirmed,
    run_scaling_report,
)

pytestmark = pytest.mark.e2e


def test_refresh_without_cookie_is_fast(e2e_server: None) -> None:
    report = run_scaling_report(login_rounds=[1])
    assert report.refresh_no_cookie_ms < 500, (
        f"POST /auth/refresh without cookie took {report.refresh_no_cookie_ms}ms — "
        "unexpected; not the accumulated-token bug"
    )


def test_setup_status_stays_fast_during_refresh_scaling_test(e2e_server: None) -> None:
    report = run_scaling_report(login_rounds=[1, 21, 41])
    assert report.setup_status_ms < 500, (
        f"GET /auth/setup-status took {report.setup_status_ms}ms — "
        "this is NOT the refresh-token bcrypt bug (see auth.py validate_refresh_token)"
    )


def test_refresh_latency_stays_fast_with_accumulated_login_sessions(e2e_server: None) -> None:
    """
    After sha256 indexed lookup fix: refresh must stay under budget even with many sessions.
    """
    report = run_scaling_report(login_rounds=[1, 21, 41])
    if is_bug_confirmed(report):
        pytest.fail(format_failure(report))
    for s in report.samples:
        if s.http_status == 200:
            assert s.refresh_ms < 2000, format_failure(report)
