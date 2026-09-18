"""P3 — batch ``scope='user'`` agent access policy assignment for one person."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.api.agents.controllers import agents_admin_api as api_mod
from apps.backend.application.agent_runtime.use_cases import agent_governance_services as svc_mod
from apps.backend.domain.access.capabilities import AdminScope


def _registry_with(*ids: str) -> MagicMock:
    reg = MagicMock()
    reg.get_agent.side_effect = lambda aid: {"id": aid} if (aid or "").strip() in set(ids) else None
    return reg


def test_batch_upsert_sets_user_scope_for_each_agent() -> None:
    row = {"id": 1, "scope": "user", "agent_id": "x"}
    with (
        patch.object(svc_mod, "get_agent_registry", return_value=_registry_with("general", "coding")),
        patch.object(svc_mod.agent_access_policy_store, "upsert_agent_policy", return_value=row) as upsert,
    ):
        out = svc_mod.batch_upsert_user_agent_policies(
            user_id=uuid.uuid4(),
            agent_ids=["general", "coding"],
            direct_state="allow",
            delegate_state="inherit",
            notes="P3 grant",
            updated_by=uuid.uuid4(),
        )

    assert out == [row, row]
    calls = upsert.call_args_list
    assert len(calls) == 2
    for call in calls:
        kwargs = call.kwargs
        assert kwargs["scope"] == "user"
        assert kwargs["direct_state"] == "allow"
        assert kwargs["delegate_state"] == "inherit"
        assert kwargs["notes"] == "P3 grant"


def test_batch_upsert_dedupes_agent_ids() -> None:
    with (
        patch.object(svc_mod, "get_agent_registry", return_value=_registry_with("general")),
        patch.object(svc_mod.agent_access_policy_store, "upsert_agent_policy", return_value={"id": 1}) as upsert,
    ):
        svc_mod.batch_upsert_user_agent_policies(
            user_id=uuid.uuid4(),
            agent_ids=["general", " general ", "general"],
            direct_state="allow",
            delegate_state="inherit",
            notes=None,
            updated_by=uuid.uuid4(),
        )
    assert upsert.call_count == 1


def test_batch_upsert_rejects_unknown_agent() -> None:
    with (
        patch.object(svc_mod, "get_agent_registry", return_value=_registry_with("general")),
        patch.object(svc_mod.agent_access_policy_store, "upsert_agent_policy") as upsert,
    ):
        with pytest.raises(ValueError) as exc:
            svc_mod.batch_upsert_user_agent_policies(
                user_id=uuid.uuid4(),
                agent_ids=["general", "nope"],
                direct_state="allow",
                delegate_state="inherit",
                notes=None,
                updated_by=uuid.uuid4(),
            )
    assert "nope" in str(exc.value)
    upsert.assert_not_called()


def test_batch_endpoint_requires_admin_and_maps_errors() -> None:
    actor = uuid.uuid4()
    scope = AdminScope(actor_id=actor, site_wide=True, tenant_ids=frozenset())

    def _ok(**_kwargs: object) -> list[dict]:
        return [{"id": 1, "scope": "user", "agent_id": "general"}]

    def _boom(**_kwargs: object) -> list[dict]:
        raise ValueError("unknown agent id(s): ghost")

    async def run_ok() -> None:
        with (
            patch.object(api_mod, "require_admin_scope", new=AsyncMock(return_value=scope)),
            patch.object(api_mod, "batch_upsert_user_agent_policies", new=MagicMock(side_effect=_ok)),
        ):
            resp = await api_mod.admin_batch_agent_access_policy(
                MagicMock(),
                api_mod.AgentAccessBatchBody(
                    user_id=uuid.uuid4(), agent_ids=["general"], direct_state="allow"
                ),
            )
        assert resp["ok"] is True
        assert len(resp["policies"]) == 1

    async def run_bad() -> None:
        with (
            patch.object(api_mod, "require_admin_scope", new=AsyncMock(return_value=scope)),
            patch.object(api_mod, "batch_upsert_user_agent_policies", new=MagicMock(side_effect=_boom)),
        ):
            with pytest.raises(HTTPException) as exc:
                await api_mod.admin_batch_agent_access_policy(
                    MagicMock(),
                    api_mod.AgentAccessBatchBody(user_id=uuid.uuid4(), agent_ids=["ghost"]),
                )
            assert exc.value.status_code == 400

    asyncio.run(run_ok())
    asyncio.run(run_bad())
