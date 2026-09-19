"""Phase 5 — the grant admin API's scope handling.

The writer refuses a mismatched (entity, tenant) pair. These tests cover the
handler side: the tenant is derived from the entity before the actor's scope is
checked, the capability asked for matches the entity type, and nothing about
which company a grant belongs to is taken from the request body.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.api.platform.controllers import admin_grants_api as api
from apps.backend.application.access.use_cases import grant_admin_service as svc
from apps.backend.domain.access.capabilities import (
    CAP_DASHBOARD_MANAGE,
    CAP_WORKSPACE_MANAGE,
    AdminScope,
)

WS_ID = str(uuid.uuid4())
DASH_ID = str(uuid.uuid4())
ACTOR = uuid.uuid4()


def _run(coro):
    return asyncio.run(coro)


def _scope(tenant_ids=(1,), site_wide=False) -> AdminScope:
    return AdminScope(
        actor_id=ACTOR,
        site_wide=site_wide,
        tenant_ids=frozenset(tenant_ids),
    )


def _guard(scope, calls):
    async def fake(request, capability):
        calls.append(capability)
        return scope

    return fake


def _replace_body(grants):
    return api.GrantsReplaceBody(grants=[api.GrantEntry(**g) for g in grants])


# --------------------------------------------------------------------------
# Tenant comes from the entity
# --------------------------------------------------------------------------


def test_tenant_written_is_the_entitys_not_the_requesters():
    calls: list = []
    written: dict = {}

    def fake_replace(**kw):
        written.update(kw)
        return []

    with (
        patch.object(svc, "entity_tenant", return_value=1),
        patch.object(api, "require_admin_scope", _guard(_scope(tenant_ids=(1,)), calls)),
        patch.object(api, "replace_grants", new=fake_replace),
    ):
        _run(
            api.replace_entity_grants(
                MagicMock(), "workspace", WS_ID,
                _replace_body([{"min_role": "tenant_member", "access": "view"}]),
            )
        )

    assert written["tenant_id"] == 1
    assert written["created_by"] == ACTOR


def test_a_foreign_entity_is_refused_before_anything_is_written():
    """Admin of tenant 1 reaching a workspace that lives in tenant 2."""
    calls: list = []
    with (
        patch.object(svc, "entity_tenant", return_value=2),
        patch.object(api, "require_admin_scope", _guard(_scope(tenant_ids=(1,)), calls)),
        patch.object(
            api, "replace_grants",
            new=MagicMock(side_effect=AssertionError("must not be called")),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(
                api.replace_entity_grants(
                    MagicMock(), "workspace", WS_ID,
                    _replace_body([{"min_role": "tenant_member", "access": "view"}]),
                )
            )
    assert exc.value.status_code == 403


def test_site_admin_reaches_a_foreign_tenant():
    calls: list = []
    written: dict = {}

    def fake_replace(**kw):
        written.update(kw)
        return []

    with (
        patch.object(svc, "entity_tenant", return_value=9),
        patch.object(api, "require_admin_scope", _guard(_scope(site_wide=True), calls)),
        patch.object(api, "replace_grants", new=fake_replace),
    ):
        _run(
            api.replace_entity_grants(
                MagicMock(), "workspace", WS_ID,
                _replace_body([{"min_role": "tenant_member", "access": "view"}]),
            )
        )
    assert written["tenant_id"] == 9


# --------------------------------------------------------------------------
# Capability follows the entity type
# --------------------------------------------------------------------------


def test_workspace_grants_ask_for_the_workspace_capability():
    calls: list = []
    with (
        patch.object(svc, "entity_tenant", return_value=1),
        patch.object(api, "require_admin_scope", _guard(_scope(), calls)),
        patch.object(api, "list_grants", return_value=[]),
    ):
        _run(api.list_entity_grants(MagicMock(), "workspace", WS_ID))
    assert calls == [CAP_WORKSPACE_MANAGE]


def test_dashboard_grants_ask_for_the_dashboard_capability():
    """Not the workspace one — a dashboard admin must not need workspace.manage."""
    calls: list = []
    with (
        patch.object(svc, "entity_tenant", return_value=1),
        patch.object(api, "require_admin_scope", _guard(_scope(), calls)),
        patch.object(api, "list_grants", return_value=[]),
    ):
        _run(api.list_entity_grants(MagicMock(), "dashboard", DASH_ID))
    assert calls == [CAP_DASHBOARD_MANAGE]


def test_revoke_uses_the_capability_for_its_entity_type():
    calls: list = []
    with (
        patch.object(svc, "entity_tenant", return_value=1),
        patch.object(api, "require_admin_scope", _guard(_scope(), calls)),
        patch.object(api, "revoke_grant", return_value=True),
    ):
        _run(api.revoke_entity_grant(MagicMock(), "dashboard", DASH_ID, "tenant_member"))
    assert calls == [CAP_DASHBOARD_MANAGE]


# --------------------------------------------------------------------------
# Error shapes
# --------------------------------------------------------------------------


def test_missing_entity_is_404_and_the_gate_ran_first():
    """The capability gate runs before the entity is looked up, so a caller
    without it does not learn whether the entity exists."""
    calls: list = []
    with (
        patch.object(svc, "entity_tenant", return_value=None),
        patch.object(api, "require_admin_scope", _guard(_scope(), calls)),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(api.list_entity_grants(MagicMock(), "workspace", WS_ID))
    assert exc.value.status_code == 404
    assert calls == [CAP_WORKSPACE_MANAGE]


def test_unsupported_entity_type_is_404():
    with pytest.raises(HTTPException) as exc:
        _run(api.list_entity_grants(MagicMock(), "billing", WS_ID))
    assert exc.value.status_code == 404
    assert "unsupported entity type" in str(exc.value.detail)


def test_revoke_with_an_unknown_min_role_is_400_before_any_lookup():
    calls: list = []
    with (
        patch.object(
            svc, "entity_tenant",
            new=MagicMock(side_effect=AssertionError("must not be called")),
        ),
        patch.object(api, "require_admin_scope", _guard(_scope(), calls)),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(api.revoke_entity_grant(MagicMock(), "workspace", WS_ID, "root"))
    assert exc.value.status_code == 400


def test_grant_error_from_the_service_is_400_not_500():
    calls: list = []
    with (
        patch.object(svc, "entity_tenant",
                     side_effect=svc.GrantError("unsupported entity type: x")),
        patch.object(api, "require_admin_scope", _guard(_scope(), calls)),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(api.list_entity_grants(MagicMock(), "workspace", WS_ID))
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------
# Body shape
# --------------------------------------------------------------------------


def test_the_replace_body_does_not_accept_a_tenant_id():
    """A body that could name a tenant is the hole; extra fields are refused."""
    with pytest.raises(Exception):
        api.GrantsReplaceBody(
            grants=[{"min_role": "tenant_member", "access": "view"}],
            tenant_id=99,  # type: ignore[call-arg]
        )


def test_a_grant_entry_does_not_accept_an_extra_field():
    with pytest.raises(Exception):
        api.GrantEntry(
            min_role="tenant_member",
            access="view",
            granted_to="someone",  # type: ignore[call-arg]
        )
