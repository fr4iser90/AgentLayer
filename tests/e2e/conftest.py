"""Pytest fixtures for HTTP E2E journeys (running Agent Layer on :8088)."""

from __future__ import annotations

import pytest

from tests.e2e.helpers import E2EClient, admin_credentials, load_e2e_env, require_server


@pytest.fixture(scope="session", autouse=True)
def _e2e_env() -> None:
    load_e2e_env()


@pytest.fixture(scope="session")
def e2e_server() -> None:
    require_server()


@pytest.fixture(scope="session")
def admin_client(e2e_server: None) -> E2EClient:
    email, password = admin_credentials()
    client = E2EClient.login(email, password)
    yield client
    client.close()


@pytest.fixture(scope="session")
def user_b_client(admin_client: E2EClient) -> E2EClient:
    from tests.e2e.helpers import ensure_user_b, user_b_credentials

    try:
        user_b_credentials()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    client = ensure_user_b(admin_client)
    yield client
    client.close()
