"""Shared assertions for cross-user IDOR E2E tests (security, not LLM)."""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.support.helpers import E2EClient

_DENY = frozenset({401, 403, 404})


def assert_cross_user_get_blocked(
    *,
    owner: E2EClient,
    other: E2EClient,
    path: str,
    resource_label: str,
) -> None:
    """
    User A (owner) created ``path``; User B must **not** read it.

    Pass = owner GET 200, other GET 401/403/404.
    Fail = other GET 200 (IDOR vulnerability).
    """
    owner_resp = owner.http.get(path)
    if owner_resp.status_code != 200:
        pytest.fail(
            f"E2E setup failed: owner cannot read own {resource_label} "
            f"({path} -> HTTP {owner_resp.status_code}: {owner_resp.text[:200]})"
        )

    other_resp = other.http.get(path)
    if other_resp.status_code in _DENY:
        return

    pytest.fail(
        f"SECURITY FAIL (IDOR): {other.email} must not read {owner.email}'s {resource_label}. "
        f"Expected HTTP 401/403/404, got {other_resp.status_code}: {other_resp.text[:400]}"
    )


def assert_cross_user_mutate_blocked(
    *,
    other: E2EClient,
    method: str,
    path: str,
    json_body: dict | None,
    resource_label: str,
    action: str,
) -> None:
    """User B must not PATCH/DELETE another user's resource."""
    resp = other.http.request(method, path, json=json_body)
    if resp.status_code in _DENY:
        return
    pytest.fail(
        f"SECURITY FAIL (IDOR): {other.email} must not {action} {resource_label}. "
        f"Expected HTTP 401/403/404, got {resp.status_code}: {resp.text[:400]}"
    )
