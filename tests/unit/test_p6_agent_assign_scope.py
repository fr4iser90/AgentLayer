"""Tenant scope on the ``agent.assign`` surface.

Before the scope layer a delegated ``agent.assign`` holder of company A could
read and rewrite company B's agent policies, and ``POST
/v1/admin/agents/access-policy/batch`` granted agents against *any* ``user_id``
with no tenant check at all. Two extra traps are covered here:

* ``agent_access_policy_store`` OR-joins its filters, so a ``user_id`` filter is
  not bounded by the ``tenant_id`` filter and needs its own check, and
* ``scope='global'`` reaches every tenant, so it is never a delegated action.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.api.agents.controllers import agents_admin_api as api
from apps.backend.domain.access.capabilities import AdminScope

_ACTOR = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_OWN_TENANT = 4
_OTHER_TENANT = 9
_USER_OWN = uuid.UUID("22222222-2222-2222-2222-222222222222")
_USER_OTHER = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _delegated() -> AdminScope:
    return AdminScope(actor_id=_ACTOR, site_wide=False, tenant_ids=frozenset({_OWN_TENANT}))


def _site() -> AdminScope:
    return AdminScope(actor_id=_ACTOR, site_wide=True, tenant_ids=frozenset())


def _tenant_of(uid) -> int:
    if uid == _USER_OTHER:
        return _OTHER_TENANT
    return _OWN_TENANT


def _patches(scope: AdminScope, **overrides):
    """Common patches: the guard returns ``scope``, tenant lookups are real ints."""
    mocks = {
        "require_admin_scope": AsyncMock(return_value=scope),
    }
    db = MagicMock()
    db.user_tenant_id = MagicMock(side_effect=_tenant_of)
    mocks["db"] = db
    for name, value in overrides.items():
        mocks[name] = value
    return mocks


class ExitStackPatches:
    def __init__(self, scope: AdminScope, **overrides) -> None:
        self.scope = scope
        self.overrides = overrides
        self.stack = None

    def __enter__(self):
        from contextlib import ExitStack

        self.stack = ExitStack()
        for name, value in _patches(self.scope, **self.overrides).items():
            self.stack.enter_context(patch.object(api, name, new=value))
        return self._view()

    def _view(self):
        return {name: getattr(api, name) for name in ("db",) + tuple(self.overrides)}

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)


# --- list ---


def test_list_delegated_defaults_to_own_tenant() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            list_agent_policy_rows=lambda **kw: captured.update(kw) or [],
        ):
            out = await api.admin_list_agent_policies(MagicMock(), tenant_id=None)
        assert captured["tenant_id"] == _OWN_TENANT
        assert out == {"policies": []}

    asyncio.run(run())


def test_list_delegated_denied_other_tenant() -> None:
    async def run() -> None:
        with ExitStackPatches(scope=_delegated(), list_agent_policy_rows=lambda **kw: []):
            with pytest.raises(HTTPException) as exc:
                await api.admin_list_agent_policies(MagicMock(), tenant_id=_OTHER_TENANT)
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_list_delegated_denied_other_tenants_user_id() -> None:
    """The OR-join trap: user_id is not bounded by the tenant filter."""
    async def run() -> None:
        with ExitStackPatches(scope=_delegated(), list_agent_policy_rows=lambda **kw: []):
            with pytest.raises(HTTPException) as exc:
                await api.admin_list_agent_policies(
                    MagicMock(), tenant_id=None, user_id=_USER_OTHER
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_list_site_admin_may_target_any_tenant() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_site(),
            list_agent_policy_rows=lambda **kw: captured.update(kw) or [],
        ):
            await api.admin_list_agent_policies(MagicMock(), tenant_id=_OTHER_TENANT)
        assert captured["tenant_id"] == _OTHER_TENANT

    asyncio.run(run())


# --- put ---


def _put_body(**kw):
    base = dict(scope="tenant", tenant_id=_OWN_TENANT, direct_state="allow")
    base.update(kw)
    return api.AgentAccessPolicyBody(**base)


def test_put_delegated_writes_own_tenant() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            upsert_agent_access_policy=lambda **kw: captured.update(kw) or {"ok": 1},
        ):
            out = await api.admin_put_agent_access_policy(MagicMock(), "todo_agent", _put_body())
        assert out["ok"] is True
        assert captured["tenant_id"] == _OWN_TENANT
        assert captured["updated_by"] == _ACTOR

    asyncio.run(run())


def test_put_delegated_denied_other_tenant() -> None:
    written: list[dict] = []

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            upsert_agent_access_policy=lambda **kw: written.append(kw) or {},
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_put_agent_access_policy(
                    MagicMock(), "todo_agent", _put_body(tenant_id=_OTHER_TENANT)
                )
        assert exc.value.status_code == 403
        assert written == []

    asyncio.run(run())


def test_put_delegated_denied_global_scope() -> None:
    written: list[dict] = []

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            upsert_agent_access_policy=lambda **kw: written.append(kw) or {},
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_put_agent_access_policy(
                    MagicMock(), "todo_agent", api.AgentAccessPolicyBody(scope="global")
                )
        assert exc.value.status_code == 403
        assert written == []

    asyncio.run(run())


def test_put_site_admin_may_write_global_scope() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_site(),
            upsert_agent_access_policy=lambda **kw: captured.update(kw) or {"ok": 1},
        ):
            out = await api.admin_put_agent_access_policy(
                MagicMock(), "todo_agent", api.AgentAccessPolicyBody(scope="global")
            )
        assert out["ok"] is True
        assert captured["scope"] == "global"

    asyncio.run(run())


def test_put_delegated_denied_user_policy_of_other_tenant() -> None:
    written: list[dict] = []

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            upsert_agent_access_policy=lambda **kw: written.append(kw) or {},
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_put_agent_access_policy(
                    MagicMock(), "todo_agent", _put_body(scope="user", user_id=_USER_OTHER)
                )
        assert exc.value.status_code == 403
        assert written == []

    asyncio.run(run())


# --- delete ---


def test_delete_delegated_denied_global_scope() -> None:
    async def run() -> None:
        with ExitStackPatches(scope=_delegated(), delete_agent_access_policy=lambda **kw: 1):
            with pytest.raises(HTTPException) as exc:
                await api.admin_delete_agent_access_policy(
                    MagicMock(), "todo_agent", scope="global", tenant_id=None
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_delete_delegated_denied_other_tenant() -> None:
    async def run() -> None:
        with ExitStackPatches(scope=_delegated(), delete_agent_access_policy=lambda **kw: 1):
            with pytest.raises(HTTPException) as exc:
                await api.admin_delete_agent_access_policy(
                    MagicMock(), "todo_agent", scope="tenant", tenant_id=_OTHER_TENANT
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_delete_delegated_may_delete_own_tenant_policy() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            delete_agent_access_policy=lambda **kw: captured.update(kw) or 1,
        ):
            out = await api.admin_delete_agent_access_policy(
                MagicMock(), "todo_agent", scope="tenant", tenant_id=_OWN_TENANT
            )
        assert out["deleted"] == 1
        assert captured["tenant_id"] == _OWN_TENANT

    asyncio.run(run())


# --- batch (the sharpest hole) ---


def _batch_body(user_id):
    return api.AgentAccessBatchBody(user_id=user_id, agent_ids=["todo_agent", "research_agent"])


def test_batch_delegated_grants_to_own_tenant_user() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            batch_upsert_user_agent_policies=lambda **kw: captured.update(kw) or [],
        ):
            out = await api.admin_batch_agent_access_policy(MagicMock(), _batch_body(_USER_OWN))
        assert out["ok"] is True
        assert captured["user_id"] == _USER_OWN
        assert captured["updated_by"] == _ACTOR

    asyncio.run(run())


def test_batch_delegated_denied_user_of_other_tenant() -> None:
    """The hole this closes: granting company A's agents to a company B person."""
    granted: list[dict] = []

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            batch_upsert_user_agent_policies=lambda **kw: granted.append(kw) or [],
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_batch_agent_access_policy(MagicMock(), _batch_body(_USER_OTHER))
        assert exc.value.status_code == 403
        assert granted == []

    asyncio.run(run())


def test_batch_site_admin_may_grant_any_tenant_user() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_site(),
            batch_upsert_user_agent_policies=lambda **kw: captured.update(kw) or [],
        ):
            out = await api.admin_batch_agent_access_policy(MagicMock(), _batch_body(_USER_OTHER))
        assert out["ok"] is True
        assert captured["user_id"] == _USER_OTHER

    asyncio.run(run())


# --- prompt versions (moved off require_admin) ---


def _registry() -> MagicMock:
    reg = MagicMock()
    reg.get_agent.side_effect = lambda aid: {"id": aid, "name": aid} if aid == "todo_agent" else None
    reg.agent_ids.return_value = ["todo_agent"]
    return reg


def _caller() -> MagicMock:
    return MagicMock(role="admin")


def test_prompt_versions_delegated_reads_own_tenant() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            get_agent_registry=_registry,
            list_agent_prompt_versions=lambda **kw: captured.update(kw) or [],
        ):
            out = await api.admin_list_agent_prompt_versions(
                MagicMock(), "todo_agent", tenant_id=None
            )
        assert captured["tenant_id"] == _OWN_TENANT
        assert out == {"versions": []}

    asyncio.run(run())


def test_prompt_versions_delegated_denied_other_tenant() -> None:
    read: list[dict] = []

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            get_agent_registry=_registry,
            list_agent_prompt_versions=lambda **kw: read.append(kw) or [],
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_list_agent_prompt_versions(
                    MagicMock(), "todo_agent", tenant_id=_OTHER_TENANT
                )
        assert exc.value.status_code == 403
        assert read == []

    asyncio.run(run())


def test_prompt_draft_delegated_writes_own_tenant() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            create_agent_prompt_draft=lambda **kw: captured.update(kw) or {"id": 1},
        ):
            out = await api.admin_create_agent_prompt_draft(
                MagicMock(),
                "todo_agent",
                api.AgentPromptDraftBody(prompt_text="do the thing"),
                tenant_id=None,
            )
        assert out["ok"] is True
        assert captured["tenant_id"] == _OWN_TENANT
        assert captured["created_by"] == _ACTOR

    asyncio.run(run())


def test_prompt_draft_delegated_denied_other_tenant() -> None:
    written: list[dict] = []

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            create_agent_prompt_draft=lambda **kw: written.append(kw) or {},
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_create_agent_prompt_draft(
                    MagicMock(),
                    "todo_agent",
                    api.AgentPromptDraftBody(prompt_text="do the thing"),
                    tenant_id=_OTHER_TENANT,
                )
        assert exc.value.status_code == 403
        assert written == []

    asyncio.run(run())


def test_prompt_publish_delegated_denied_other_tenant() -> None:
    published: list[dict] = []

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            publish_agent_prompt_version=lambda **kw: published.append(kw) or {},
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_publish_agent_prompt_version(
                    MagicMock(), "todo_agent", uuid.uuid4(), tenant_id=_OTHER_TENANT
                )
        assert exc.value.status_code == 403
        assert published == []

    asyncio.run(run())


def test_prompt_publish_delegated_may_publish_own_tenant() -> None:
    captured: dict[str, object] = {}
    vid = uuid.uuid4()

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            get_agent_prompt_version=lambda **kw: {"prompt_text": "do the thing"},
            gate_enabled=lambda: False,
            publish_agent_prompt_version=lambda **kw: captured.update(kw) or {"id": vid},
        ):
            out = await api.admin_publish_agent_prompt_version(
                MagicMock(), "todo_agent", vid, tenant_id=None, override_reason=None
            )
        assert out["ok"] is True
        assert captured["tenant_id"] == _OWN_TENANT
        assert captured["published_by"] == _ACTOR

    asyncio.run(run())


def test_get_agent_delegated_denied_other_tenant() -> None:
    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            get_agent_registry=_registry,
            get_current_user=AsyncMock(return_value=_caller()),
            resolve_agent_governance=lambda **kw: {},
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_get_agent(
                    MagicMock(), "todo_agent", tenant_id=_OTHER_TENANT, user_id=None
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_get_agent_delegated_denied_other_tenants_user_id() -> None:
    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            get_agent_registry=_registry,
            get_current_user=AsyncMock(return_value=_caller()),
            resolve_agent_governance=lambda **kw: {},
        ):
            with pytest.raises(HTTPException) as exc:
                await api.admin_get_agent(
                    MagicMock(), "todo_agent", tenant_id=None, user_id=_USER_OTHER
                )
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_get_agent_delegated_may_preview_own_tenant() -> None:
    captured: dict[str, object] = {}

    async def run() -> None:
        with ExitStackPatches(
            scope=_delegated(),
            get_agent_registry=_registry,
            get_current_user=AsyncMock(return_value=_caller()),
            resolve_agent_governance=lambda **kw: captured.update(kw) or {
                "effective_tool_names": [],
                "system_prompt": "",
            },
        ):
            out = await api.admin_get_agent(
                MagicMock(), "todo_agent", role=None, tenant_id=None, user_id=_USER_OWN
            )
        assert captured["tenant_id"] == _OWN_TENANT
        assert out["effective_preview"]["tenant_id"] == _OWN_TENANT

    asyncio.run(run())
