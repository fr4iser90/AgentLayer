"""Pytest fixtures for HTTP E2E journeys (running Agent Layer on :8088)."""

from __future__ import annotations

import pytest

from tests.e2e.support.helpers import E2EClient, admin_credentials, env_truthy, load_e2e_env, require_server


@pytest.fixture(scope="session", autouse=True)
def _e2e_env() -> None:
    load_e2e_env()


@pytest.fixture(scope="session", autouse=True)
def _e2e_require_live_llm(_e2e_env: None) -> None:
    """E2E always uses the server's real LLM catalog — no mock/stub path."""
    if env_truthy("AGENT_E2E_MOCK_LLM"):
        pytest.fail(
            "AGENT_E2E_MOCK_LLM is not supported — remove it from .env and restart the server. "
            "E2E requires a live LLM provider (LLM_PROVIDER_* or Admin LLM endpoints)."
        )
    require_server()
    email, password = admin_credentials()
    client = E2EClient.login(email, password)
    try:
        models_resp = client.get_json("/v1/models")
        rows = models_resp.get("data") if isinstance(models_resp, dict) else None
        if not rows:
            pytest.fail(
                "E2E requires at least one LLM in GET /v1/models — configure LLM_PROVIDER_* "
                "or Admin → Interfaces → LLM endpoints on the running server"
            )
    finally:
        client.close()


@pytest.fixture(scope="session")
def e2e_server(_e2e_require_live_llm: None) -> None:
    """Running Agent Layer with live LLM catalog (see ``_e2e_require_live_llm``)."""


@pytest.fixture(scope="session")
def admin_client(e2e_server: None) -> E2EClient:
    email, password = admin_credentials()
    client = E2EClient.login(email, password)
    yield client
    client.close()


@pytest.fixture(scope="session")
def user_b_client(admin_client: E2EClient) -> E2EClient:
    from tests.e2e.support.helpers import ensure_user_b, user_b_credentials

    try:
        user_b_credentials()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    client = ensure_user_b(admin_client)
    yield client
    client.close()


@pytest.fixture
def e2e_resources(admin_client: E2EClient):
    """Track conversations/dashboards/workspaces; delete after each E2E test."""
    from tests.e2e.support.cleanup import E2EResourceTracker

    tracker = E2EResourceTracker(admin_client)
    yield tracker
    tracker.cleanup()
