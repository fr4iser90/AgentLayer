"""P2 — ``GET /v1/agents`` is authenticated, access-filtered and non-sensitive.

Closes B2: the registry endpoint previously handed every logged-in user the raw
agent dump (including ``system_prompt`` and tool allowlists) with no access check.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.api.agents.controllers import agents_api as api_mod
from apps.backend.application.agent_runtime.use_cases import agent_catalog as catalog_mod
from apps.backend.domain.agent_runtime import access as access_mod


class _MockUser:
    def __init__(self, uid: uuid.UUID, role: str) -> None:
        self.id = uid
        self.role = role


def _empty_policy_deps() -> MagicMock:
    deps = MagicMock()
    deps.list_agent_policies.return_value = []
    return deps


def _run(coro):
    return asyncio.run(coro)


def test_list_agents_requires_authentication() -> None:
    async def call() -> None:
        with patch.object(api_mod, "get_current_user", new=AsyncMock(side_effect=HTTPException(401))):
            with pytest.raises(HTTPException) as exc:
                await api_mod.list_agents(MagicMock())
            assert exc.value.status_code == 401

    _run(call())


def test_site_user_sees_only_enduser_agents() -> None:
    user = _MockUser(uuid.uuid4(), "site_user")
    user_id = user.id

    async def call() -> list[dict]:
        with (
            patch.object(api_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(access_mod, "_deps", _empty_policy_deps()),
            patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=False),
        ):
            return await api_mod.list_agents(MagicMock())

    agents = _run(call())
    ids = {a["id"] for a in agents}
    assert ids == {"general", "knowledge_companion"}
    for a in agents:
        assert "system_prompt" not in a
        assert a.get("invokable_by_caller") is True


def test_site_admin_sees_full_catalog_without_prompt_leak() -> None:
    user = _MockUser(uuid.uuid4(), "site_admin")

    async def call() -> list[dict]:
        with (
            patch.object(api_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(access_mod, "_deps", _empty_policy_deps()),
            patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=True),
        ):
            return await api_mod.list_agents(MagicMock())

    agents = _run(call())
    ids = {a["id"] for a in agents}
    assert {"general", "knowledge_companion"}.issubset(ids)
    # Admin sees specialists an end user cannot, proving the filter is role-driven.
    assert len(ids) > 2
    for a in agents:
        assert "system_prompt" not in a
        assert a.get("invokable_by_caller") is True
        assert "tool_allowlist" not in a and "tool_domains" not in a


def test_single_agent_endpoint_filters_and_sanitizes() -> None:
    user = _MockUser(uuid.uuid4(), "site_user")

    # Invokable for an end user: returned as a sanitized projection.
    async def knowledge() -> dict:
        with (
            patch.object(api_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(access_mod, "_deps", _empty_policy_deps()),
            patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=False),
        ):
            return await api_mod.get_agent(MagicMock(), "knowledge_companion")

    view = _run(knowledge())
    assert view["id"] == "knowledge_companion"
    assert "system_prompt" not in view

    # Admin-only agent: a non-caller gets 404 (no enumeration, no prompt).
    async def operator_blocked() -> None:
        with (
            patch.object(api_mod, "get_current_user", new=AsyncMock(return_value=user)),
            patch.object(access_mod, "_deps", _empty_policy_deps()),
            patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc:
                await api_mod.get_agent(MagicMock(), "operator")
            assert exc.value.status_code == 404

    _run(operator_blocked())


def test_agent_access_role_prefers_site_role_over_legacy_role() -> None:
    legacy_admin = _MockUser(uuid.uuid4(), "admin")

    # Legacy role='admin' but site_role='site_user' → not elevated for agent access.
    with patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=False):
        assert catalog_mod._agent_access_role(legacy_admin) == "user"

    # site_role='site_admin' → elevated regardless of the legacy role field.
    with patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=True):
        assert catalog_mod._agent_access_role(legacy_admin) == "admin"
