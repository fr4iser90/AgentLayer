"""Admin schedule endpoints act inside their scope, not inside their own company.

Two failures this pins down, both measured in the code before it was fixed:

- every handler resolved ``db.user_tenant_id(actor)``, so even a site admin saw
  one company's schedules while the list endpoint advertised company-wide filters;
- the create path checked only that the target is a schedulable agent id, never
  the two-layer target policy the user path applies, so a delegated
  ``schedule.manage`` holder could schedule an agent their company's allowlist
  denies.

The policy itself is stubbed here on purpose: what broke was the *call*, so the
assertions are about that call and the arguments it must carry.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fastapi import HTTPException

from apps.backend.api.scheduling.controllers import scheduler_job_runs_api as runs_mod
from apps.backend.api.scheduling.controllers import scheduler_jobs_admin_api as mod
from apps.backend.domain.access.capabilities import AdminScope
from apps.backend.infrastructure.scheduling import scheduler_jobs_store as real_jobs_store

OWNER_TENANT = 7
OTHER_TENANT = 9


def _scope(*, site_wide: bool, tenant_id: int = OWNER_TENANT) -> AdminScope:
    return AdminScope(
        actor_id=uuid.uuid4(),
        site_wide=site_wide,
        tenant_ids=frozenset() if site_wide else frozenset({tenant_id}),
    )


class _RecordingStore:
    """Records what the handlers asked the store for; returns nothing back."""

    def __init__(self) -> None:
        self.list_calls: list[dict[str, Any]] = []
        self.inserted: list[dict[str, Any]] = []
        self.deleted: list[uuid.UUID] = []
        self.job_rows: dict[uuid.UUID, dict[str, Any]] = {}
        self.runs_calls: list[dict[str, Any]] = []

    def list_jobs_for_scope(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.list_calls.append(kwargs)
        return []

    def insert_job(self, **kwargs: Any) -> dict[str, Any]:
        self.inserted.append(kwargs)
        return {"id": uuid.uuid4()}

    def get_job_any_tenant(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        return self.job_rows.get(job_id)

    def hard_delete_job(self, *, job_id: uuid.UUID, tenant_id: int, **_k: Any) -> bool:
        self.deleted.append(job_id)
        return True

    def list_runs_for_job(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.runs_calls.append(kwargs)
        return []

    def row_to_public(self, row: dict[str, Any]) -> dict[str, Any]:
        return real_jobs_store.row_to_public(row)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _RecordingStore:
    s = _RecordingStore()
    monkeypatch.setattr(mod, "scheduler_jobs_store", s)
    monkeypatch.setattr(runs_mod, "scheduler_jobs_store", s)
    monkeypatch.setattr(runs_mod, "scheduler_job_runs_store", s)
    monkeypatch.setattr(mod.db, "user_tenant_id", lambda _uid: OWNER_TENANT)
    return s


@pytest.fixture
def scope(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> AdminScope:
    site_wide = getattr(request, "param", False)
    sc = _scope(site_wide=site_wide)

    async def _fake(_request: Any, _capability: str) -> AdminScope:
        return sc

    monkeypatch.setattr(mod, "require_admin_scope", _fake)
    monkeypatch.setattr(runs_mod, "require_admin_scope", _fake)
    return sc


@pytest.fixture
def policy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _fake(**kwargs: Any) -> str | None:
        calls.append(kwargs)
        return None

    monkeypatch.setattr(mod, "schedule_permission_error", _fake)
    monkeypatch.setattr(mod, "agent_effective_role", lambda _uid, *_a: "user")
    return calls


def _create_body(**over: Any) -> Any:
    kwargs: dict[str, Any] = {
        "execution_target": "general",
        "instructions": "jeden morgen das Board zusammenfassen",
        "interval_minutes": 60,
    }
    kwargs.update(over)
    return mod.SchedulerJobCreateBody(**kwargs)


def test_delegated_holder_lists_their_own_company(store: _RecordingStore, scope: AdminScope) -> None:
    asyncio.run(mod.scheduler_job_list(request=None, limit=200))

    assert scope.site_wide is False
    assert store.list_calls[0]["tenant_ids"] == frozenset({OWNER_TENANT})


@pytest.mark.parametrize("scope", [True], indirect=True)
def test_site_admin_sees_every_company(store: _RecordingStore, scope: AdminScope) -> None:
    asyncio.run(mod.scheduler_job_list(request=None, limit=200))

    assert scope.site_wide is True
    assert store.list_calls[0]["tenant_ids"] is None, "site-wide must not filter by company"


@pytest.mark.parametrize("scope", [True], indirect=True)
def test_site_admin_narrowing_to_another_company_is_honoured(
    store: _RecordingStore, scope: AdminScope
) -> None:
    asyncio.run(mod.scheduler_job_list(request=None, tenant_id=OTHER_TENANT, limit=200))

    assert store.list_calls[0]["tenant_ids"] == frozenset({OTHER_TENANT})


def test_delegated_holder_cannot_list_another_company(store: _RecordingStore, scope: AdminScope) -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.scheduler_job_list(request=None, tenant_id=OTHER_TENANT, limit=200))

    assert exc.value.status_code == 403
    assert store.list_calls == [], "a denied filter must not fall back to a silent narrower query"


def test_mutation_on_a_foreign_job_is_not_found(store: _RecordingStore, scope: AdminScope) -> None:
    jid = uuid.uuid4()
    store.job_rows[jid] = {"id": jid, "tenant_id": OTHER_TENANT}

    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.scheduler_job_hard_delete(request=None, job_id=str(jid)))

    assert exc.value.status_code == 404, "another company's job must not be confirmed to exist"
    assert store.deleted == []


def test_mutation_on_an_own_company_job_reaches_the_store(store: _RecordingStore, scope: AdminScope) -> None:
    jid = uuid.uuid4()
    store.job_rows[jid] = {"id": jid, "tenant_id": OWNER_TENANT}

    out = asyncio.run(mod.scheduler_job_hard_delete(request=None, job_id=str(jid)))

    assert out["deleted"] is True
    assert store.deleted == [jid]


def test_runs_of_a_foreign_job_are_not_found(store: _RecordingStore, scope: AdminScope) -> None:
    jid = uuid.uuid4()
    store.job_rows[jid] = {"id": jid, "tenant_id": OTHER_TENANT}

    with pytest.raises(HTTPException) as exc:
        asyncio.run(runs_mod.admin_list_scheduler_job_runs(request=None, job_id=str(jid)))

    assert exc.value.status_code == 404
    assert store.runs_calls == []


def test_runs_of_an_own_job_are_listed_in_that_company(
    store: _RecordingStore, scope: AdminScope
) -> None:
    jid = uuid.uuid4()
    store.job_rows[jid] = {"id": jid, "tenant_id": OWNER_TENANT}

    asyncio.run(runs_mod.admin_list_scheduler_job_runs(request=None, job_id=str(jid)))

    assert store.runs_calls[0]["tenant_id"] == OWNER_TENANT


def test_create_checks_the_target_policy_with_the_row_tenant(
    store: _RecordingStore, scope: AdminScope, policy: list[dict[str, Any]]
) -> None:
    asyncio.run(mod.scheduler_job_create(request=None, body=_create_body()))

    assert len(policy) == 1, "the admin path must apply the same target policy as the user path"
    assert policy[0]["execution_target"] == "general"
    assert policy[0]["tenant_id"] == OWNER_TENANT
    assert store.inserted, "positive control: an allowed target still creates"


def test_create_is_denied_when_the_policy_denies_the_target(
    store: _RecordingStore, scope: AdminScope, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Denied on a target that would otherwise pass every other check, so the only
    # thing standing between this request and an INSERT is the policy call.
    def _deny(**kwargs: Any) -> str:
        return f"execution_target {kwargs['execution_target']} is not available for your account"

    monkeypatch.setattr(mod, "schedule_permission_error", _deny)
    monkeypatch.setattr(mod, "agent_effective_role", lambda _uid, *_a: "user")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.scheduler_job_create(request=None, body=_create_body()))

    assert exc.value.status_code == 403
    assert "not available for your account" in str(exc.value.detail)
    assert store.inserted == []


@pytest.mark.parametrize("scope", [True], indirect=True)
def test_site_admin_creating_for_another_company_writes_there(
    store: _RecordingStore, scope: AdminScope, policy: list[dict[str, Any]]
) -> None:
    asyncio.run(mod.scheduler_job_create(request=None, body=_create_body(tenant_id=OTHER_TENANT)))

    assert store.inserted[0]["tenant_id"] == OTHER_TENANT
    assert policy[0]["tenant_id"] == OTHER_TENANT, "policy must judge the company being written to"