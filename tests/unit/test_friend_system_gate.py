"""The operator gate on the friendship / peer-sharing subsystem.

Before schema_137 this subsystem had no switch of any kind: no operator setting,
no deployment-mode predicate, and both routers were registered with no dependency.
Hiding the settings page was the only control, and every authenticated user could
reach /v1/friends and /v1/shares in every deployment mode.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from apps.backend.application.sharing.use_cases import sharing_controller_services as svc
from apps.backend.domain.tenant_capability import policy as nav_policy
from apps.backend.infrastructure.settings import operator_settings_readers as readers
from apps.backend.infrastructure.settings.operator_settings_forms import OperatorSettingsPatch


def test_on_by_default_when_the_column_is_absent(monkeypatch) -> None:
    # A settings row written before schema_137 has no key. Reading that as
    # "disabled" would switch the subsystem off for every existing install on
    # upgrade, so the default has to be on.
    monkeypatch.setattr(readers, "_cached_row", lambda: {})
    assert readers.friend_system_enabled() is True


def test_respects_the_flag_both_ways(monkeypatch) -> None:
    monkeypatch.setattr(readers, "_cached_row", lambda: {"friend_system_enabled": False})
    assert readers.friend_system_enabled() is False
    monkeypatch.setattr(readers, "_cached_row", lambda: {"friend_system_enabled": True})
    assert readers.friend_system_enabled() is True


def test_guard_allows_through_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(svc.operator_settings, "friend_system_enabled", lambda: True)
    asyncio.run(svc.require_friend_system())


def test_guard_refuses_with_404_when_disabled(monkeypatch) -> None:
    # 404, not 403: an undeployed subsystem should not tell a caller that it
    # exists and is merely forbidden.
    monkeypatch.setattr(svc.operator_settings, "friend_system_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(svc.require_friend_system())
    assert exc.value.status_code == 404
    assert exc.value.detail == svc.FRIEND_SYSTEM_DISABLED_DETAIL


def test_both_peer_routers_carry_the_guard() -> None:
    """The guard is a router dependency, so a route added later is covered.

    Asserted on the routers themselves rather than on a handler list, because a
    per-endpoint guard is one forgotten decorator away from a hole.
    """
    from apps.backend.api.sharing.controllers.friends_api import router as friends_router
    from apps.backend.api.sharing.controllers.shares_api import router as shares_router

    for router in (friends_router, shares_router):
        guards = [d.dependency for d in router.dependencies]
        assert svc.require_friend_system in guards, router.prefix


def test_gate_is_operator_patchable() -> None:
    assert "friend_system_enabled" in OperatorSettingsPatch.model_fields


def test_friends_is_a_known_nav_item() -> None:
    # Absent before the gate: a tenant listing "friends" in ui.allowed_nav had
    # the value silently dropped, so the item could not be turned off per tenant.
    assert "friends" in nav_policy.KNOWN_NAV_ITEMS
