"""Unit tests for benchmark fixture secret readiness (no live server)."""

from __future__ import annotations

import httpx
from unittest.mock import MagicMock

from tests.benchmarks.agent.fixtures import (
    FixtureContext,
    _auto_user_b_credentials,
    _ensure_benchmark_user_b,
    _setup_gmail_secret,
    _setup_ssc_secret,
)


def test_gmail_secret_uses_existing_user_secret() -> None:
    client = MagicMock()
    client.get_json.return_value = {"services": ["gmail"]}
    ctx = FixtureContext(run_id="r", prefix="p-")
    _setup_gmail_secret(client, ctx)
    assert "gmail_secret" not in ctx.skipped
    client.post_json.assert_not_called()


def test_ssc_secret_skips_without_env_when_missing() -> None:
    client = MagicMock()
    client.get_json.return_value = {"services": []}
    ctx = FixtureContext(run_id="r", prefix="p-")
    _setup_ssc_secret(client, ctx)
    assert "ssc_secret" in ctx.skipped
    client.post_json.assert_not_called()


def test_auto_user_b_credentials_are_run_scoped() -> None:
    ctx = FixtureContext(run_id="20260626T041500Z", prefix="bench-")
    email, password = _auto_user_b_credentials(ctx)
    assert email == "bench-friend-20260626t041500z@agentlayer.local"
    assert password.startswith("BenchUserB-")


def test_benchmark_user_b_uses_e2e_env_when_present(monkeypatch) -> None:
    expected = MagicMock()
    admin = MagicMock()
    monkeypatch.setenv("AGENT_E2E_EMAIL_B", "friend@example.com")
    monkeypatch.setenv("AGENT_E2E_PASSWORD_B", "secret")
    monkeypatch.setattr("tests.benchmarks.agent.fixtures.ensure_user_b", lambda client: expected)

    assert _ensure_benchmark_user_b(admin, FixtureContext(run_id="r", prefix="p-")) is expected
    admin.post_json_allow.assert_not_called()


def test_benchmark_user_b_auto_creates_without_e2e_env(monkeypatch) -> None:
    admin = MagicMock()
    admin.role = "admin"
    admin.post_json_allow.return_value = httpx.Response(201)
    created = MagicMock()
    missing = httpx.HTTPStatusError(
        "missing",
        request=httpx.Request("POST", "http://test/auth/login"),
        response=httpx.Response(401),
    )
    calls = {"count": 0}

    def _login(email: str, password: str):
        calls["count"] += 1
        if calls["count"] == 1:
            raise missing
        created.email = email
        return created

    monkeypatch.delenv("AGENT_E2E_EMAIL_B", raising=False)
    monkeypatch.delenv("AGENT_E2E_PASSWORD_B", raising=False)
    monkeypatch.setattr("tests.benchmarks.agent.fixtures.E2EClient.login", _login)

    ctx = FixtureContext(run_id="20260626T041500Z", prefix="bench-")
    assert _ensure_benchmark_user_b(admin, ctx) is created
    email, password = _auto_user_b_credentials(ctx)
    admin.post_json_allow.assert_called_once_with(
        "/v1/admin/users",
        {"email": email, "password": password, "role": "user", "tenant_id": 1},
        ok={200, 201, 409},
    )
