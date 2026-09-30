"""The operator console asks the same two questions as ``/v1/admin/*``: capability, then reach.

Measured in the console before this was fixed:

- every handler decided with ``db.user_role(uid) == "admin"``, the legacy column, so
  the ``users.site_role`` / ``users.capabilities`` a delegated admin was actually
  granted bought them nothing — and a person whose legacy role still said ``admin``
  kept the whole console after being demoted in the canonical one;
- ``users_list`` answered with ``list_all_users()``, every mailbox on the instance,
  the exact leak ``GET /v1/admin/users`` had already been changed to stop.

The handlers now walk :func:`scope_for` / :func:`site_scope`, so the assertions are
about what each handler hands the store: the caller's company, ``None`` for a site
admin, and nothing at all once a call is denied.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from apps.backend.infrastructure.scheduling import scheduler_jobs_store as real_jobs_store

OWNER_TENANT = 7
OTHER_TENANT = 9


class _RecordingStore:
    """What the console asked the stores for; nothing here reads a database."""

    def __init__(self) -> None:
        self.list_calls: list[dict[str, Any]] = []
        self.inserted: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.deleted: list[dict[str, Any]] = []
        self.job_rows: dict[uuid.UUID, dict[str, Any]] = {}

    def list_jobs_for_scope(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.list_calls.append(kwargs)
        return []

    def insert_job(self, **kwargs: Any) -> dict[str, Any]:
        self.inserted.append(kwargs)
        return {"id": uuid.uuid4()}

    def get_job_any_tenant(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        return self.job_rows.get(job_id)

    def update_job(self, **kwargs: Any) -> dict[str, Any] | None:
        self.updated.append(kwargs)
        return {"id": kwargs["job_id"]}

    def hard_delete_job(self, **kwargs: Any) -> bool:
        self.deleted.append(kwargs)
        return True

    def row_to_public(self, row: dict[str, Any]) -> dict[str, Any]:
        return real_jobs_store.row_to_public(row)


@pytest.fixture
def actor() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _RecordingStore:
    s = _RecordingStore()
    from plugins.tools.platform.operator import admin as oa

    monkeypatch.setattr(oa, "scheduler_jobs_store", s)
    return s


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Captures the ``tenant_ids`` each ``users_list`` call handed the user store."""

    calls: list[Any] = []

    def _fake(*, tenant_ids: Any = "unset") -> list[dict[str, Any]]:
        calls.append(tenant_ids)
        return []

    from plugins.tools.platform.operator import admin as oa

    monkeypatch.setattr(oa, "list_all_users", _fake)
    return calls


def _identity(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    *,
    site_role: str,
    capabilities: tuple[str, ...],
    tenant_id: int = OWNER_TENANT,
) -> None:
    """An identity as the console reads it: canonical role, grants, home company."""
    from plugins.tools.platform.operator import admin as oa

    monkeypatch.setattr(oa, "get_identity", lambda: (tenant_id, actor))
    monkeypatch.setattr(oa.db, "user_site_role", lambda _uid: site_role)
    monkeypatch.setattr(oa.db, "user_capabilities", lambda _uid: set(capabilities))
    monkeypatch.setattr(oa.db, "user_tenant_id", lambda _uid: tenant_id)


def _delegated(monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, *caps: str) -> None:
    _identity(
        monkeypatch,
        actor,
        site_role="site_user",
        capabilities=caps or ("user.manage",),
    )


def _site_admin(monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID) -> None:
    _identity(monkeypatch, actor, site_role="site_admin", capabilities=())


def test_no_identity_is_denied(monkeypatch: pytest.MonkeyPatch, store: _RecordingStore) -> None:
    from plugins.tools.platform.operator import admin as oa

    monkeypatch.setattr(oa, "get_identity", lambda: (1, None))

    out = json.loads(oa.users_list({}))

    assert out["ok"] is False
    assert "authentication" in out["error"]
    assert store.list_calls == []


def test_legacy_admin_without_a_grant_gets_nothing(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, mailbox: list[Any]
) -> None:
    from plugins.tools.platform.operator import admin as oa

    # ``users.role == 'admin'`` used to be the whole test; the canonical identity says
    # site_user and no capability was granted, so there is nothing to reach.
    monkeypatch.setattr(oa.db, "user_role", lambda _uid: "admin")
    _delegated(monkeypatch, actor)
    monkeypatch.setattr(oa.db, "user_capabilities", lambda _uid: set())

    out = json.loads(oa.users_list({}))

    assert out["ok"] is False
    assert "user.manage" in out["error"]
    assert mailbox == [], "a denied capability must not reach the user store"


def test_delegated_holder_lists_their_own_company(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, mailbox: list[Any]
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor, "user.manage")

    out = json.loads(oa.users_list({}))

    assert out["ok"] is True
    assert mailbox == [frozenset({OWNER_TENANT})]


def test_site_admin_lists_every_company(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, mailbox: list[Any]
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _site_admin(monkeypatch, actor)

    out = json.loads(oa.users_list({}))

    assert out["ok"] is True
    assert mailbox == [None], "site-wide must not filter by company"


def test_schedules_of_another_company_are_denied_without_querying(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, store: _RecordingStore
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor, "schedule.manage")

    out = json.loads(oa.scheduler_job_list({"tenant_id": OTHER_TENANT}))

    assert out["ok"] is False
    assert "outside your admin scope" in out["error"]
    assert store.list_calls == [], "a denied filter must not fall back to a narrower query"


def test_delegated_holder_lists_their_own_company_schedules(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, store: _RecordingStore
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor, "schedule.manage")

    out = json.loads(oa.scheduler_job_list({}))

    assert out["ok"] is True
    assert store.list_calls[0]["tenant_ids"] == frozenset({OWNER_TENANT})


def test_site_admin_lists_every_company_schedules(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, store: _RecordingStore
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _site_admin(monkeypatch, actor)

    out = json.loads(oa.scheduler_job_list({}))

    assert out["ok"] is True
    assert store.list_calls[0]["tenant_ids"] is None


def test_site_admin_narrowing_to_another_company_is_honoured(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, store: _RecordingStore
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _site_admin(monkeypatch, actor)

    out = json.loads(oa.scheduler_job_list({"tenant_id": OTHER_TENANT}))

    assert out["ok"] is True
    assert store.list_calls[0]["tenant_ids"] == frozenset({OTHER_TENANT})


@pytest.mark.parametrize(
    "tool_call",
    [
        lambda oa, jid: oa.scheduler_job_patch({"job_id": str(jid), "title": "x"}),
        lambda oa, jid: oa.scheduler_job_set_enabled({"job_id": str(jid), "enabled": False}),
        lambda oa, jid: oa.scheduler_job_set_archived({"job_id": str(jid), "archived": True}),
        lambda oa, jid: oa.scheduler_job_delete({"job_id": str(jid)}),
    ],
    ids=["patch", "enabled", "archived", "delete"],
)
def test_mutation_on_a_foreign_job_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    store: _RecordingStore,
    tool_call: Any,
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor, "schedule.manage")
    jid = uuid.uuid4()
    store.job_rows[jid] = {"id": jid, "tenant_id": OTHER_TENANT}

    out = json.loads(tool_call(oa, jid))

    assert out["ok"] is False
    assert out["error"] == "job not found", "another company's job must not be confirmed to exist"
    assert store.updated == []
    assert store.deleted == []


def test_mutation_on_an_own_job_reaches_the_store(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, store: _RecordingStore
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor, "schedule.manage")
    jid = uuid.uuid4()
    store.job_rows[jid] = {"id": jid, "tenant_id": OWNER_TENANT}

    out = json.loads(oa.scheduler_job_delete({"job_id": str(jid)}))

    assert out["ok"] is True
    assert store.deleted[0]["job_id"] == jid
    assert store.deleted[0]["tenant_id"] == OWNER_TENANT


@pytest.fixture
def policy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    from plugins.tools.platform.operator import admin as oa

    monkeypatch.setattr(oa, "agent_effective_role", lambda _uid, *_a: "user")
    monkeypatch.setattr(
        "apps.backend.domain.scheduling.targets.schedule_permission_error",
        lambda **kwargs: calls.append(kwargs) or None,
    )
    return calls


def _create_args(**over: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "execution_target": "general",
        "instructions": "jeden morgen das Board zusammenfassen",
        "interval_minutes": 60,
    }
    args.update(over)
    return args


def test_create_checks_the_target_policy_with_the_row_tenant(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    store: _RecordingStore,
    policy: list[dict[str, Any]],
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor, "schedule.manage")

    out = json.loads(oa.scheduler_job_create(_create_args()))

    assert len(policy) == 1, "the console must apply the same target policy as the route"
    assert policy[0]["tenant_id"] == OWNER_TENANT
    assert policy[0]["user_id"] == actor
    assert store.inserted[0]["tenant_id"] == OWNER_TENANT
    assert out["ok"] is True


def test_create_is_denied_when_the_policy_denies_the_target(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    store: _RecordingStore,
) -> None:
    from plugins.tools.platform.operator import admin as oa

    # A target that passes every other check, so only the policy stands between this
    # call and the INSERT.
    monkeypatch.setattr(
        "apps.backend.domain.scheduling.targets.schedule_permission_error",
        lambda **kwargs: f"execution_target {kwargs['execution_target']} is not available for your account",
    )
    monkeypatch.setattr(oa, "agent_effective_role", lambda _uid, *_a: "user")
    _delegated(monkeypatch, actor, "schedule.manage")

    out = json.loads(oa.scheduler_job_create(_create_args()))

    assert out["ok"] is False
    assert "not available for your account" in out["error"]
    assert store.inserted == []


def test_site_admin_creating_for_another_company_writes_there(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    store: _RecordingStore,
    policy: list[dict[str, Any]],
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _site_admin(monkeypatch, actor)

    out = json.loads(oa.scheduler_job_create(_create_args(tenant_id=OTHER_TENANT)))

    assert out["ok"] is True
    assert store.inserted[0]["tenant_id"] == OTHER_TENANT
    assert policy[0]["tenant_id"] == OTHER_TENANT, "policy must judge the company being written to"


@pytest.mark.parametrize(
    "tool_name",
    ["settings_get", "interfaces_get", "tenants_list", "tools_catalog", "reload_tools"],
)
def test_site_only_tools_deny_a_delegated_holder(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, tool_name: str
) -> None:
    """No capability slug means no shortcut: a delegated holder is refused outright."""
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor, "user.manage", "schedule.manage", "dashboard.manage")
    monkeypatch.setattr(oa, "operator_settings_public_dict", lambda: {})
    monkeypatch.setattr(oa, "interface_hints_public", lambda: {})
    monkeypatch.setattr(oa.db, "tenants_list", lambda: [{"id": 1}])

    out = json.loads(oa.HANDLERS[tool_name]({}))

    assert out["ok"] is False
    assert out["error"] == "site admin required"


def test_site_only_tools_admit_a_site_admin(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID
) -> None:
    from plugins.tools.platform.operator import admin as oa

    _site_admin(monkeypatch, actor)
    monkeypatch.setattr(oa, "operator_settings_public_dict", lambda: {"discord_bot_enabled": False})
    monkeypatch.setattr(oa, "interface_hints_public", lambda: {"agent_mode": "sandbox"})

    out = json.loads(oa.settings_get({}))

    assert out["ok"] is True
    assert out["settings"] == {"discord_bot_enabled": False}


def test_presets_only_need_to_be_signed_in(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID
) -> None:
    """The preset templates are shared prose; the route that draws them asks for nothing more."""
    from plugins.tools.platform.operator import admin as oa

    _delegated(monkeypatch, actor)

    out = json.loads(oa.scheduler_presets_list({}))

    assert out["ok"] is True
    assert isinstance(out["presets"], list)
