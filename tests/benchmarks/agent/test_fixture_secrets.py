"""Unit tests for benchmark fixture secret readiness (no live server)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.benchmarks.agent.fixtures import FixtureContext, _setup_gmail_secret, _setup_ssc_secret


def test_gmail_secret_uses_existing_user_secret() -> None:
    client = MagicMock()
    client.get_json.return_value = {"services": ["gmail"]}
    ctx = FixtureContext(run_id="r", prefix="p-")
    _setup_gmail_secret(client, ctx)
    assert ctx.gmail_service_key == "gmail"
    assert "gmail_secret" not in ctx.skipped
    client.post_json.assert_not_called()


def test_ssc_secret_skips_without_env_when_missing() -> None:
    client = MagicMock()
    client.get_json.return_value = {"services": []}
    ctx = FixtureContext(run_id="r", prefix="p-")
    _setup_ssc_secret(client, ctx)
    assert "ssc_secret" in ctx.skipped
    client.post_json.assert_not_called()
