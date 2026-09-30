"""The tuning console asks its routes the same two questions: ``agent.assign``, then site admin.

Measured here before it was fixed: one helper decided all fourteen tools with
``users.role == 'admin'``, a column the rest of the platform stopped trusting. It bought a
delegated company admin nothing, kept every tool open for a legacy row whose canonical
``site_role`` said ``site_user``, and — because nothing looked at the patch contents — let
either caller write an ``operator``-layer knob and so the single instance-wide
``operator_settings`` row, which their company confinement does not reach.

Every gate below was read off the route the tool mirrors
(``agent_config_admin_api.py``, ``benchmarks_admin_api.py``, ``benchmarks_experiments_api.py``,
``agents_admin_api.py``) and the assertions are about the stores: a denied call must not
have touched one, and an allowed one must carry the caller's own company.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from apps.backend.infrastructure.identity import console_access as console_guard
from plugins.tools.platform.operator import agent_config_tools as act

OWNER_TENANT = 7
OTHER_TENANT = 9
OPERATOR_KNOB = "operator_layer_knob"


class _Stores:
    """Every store the console reads or writes. Nothing here touches a database."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.reads: list[str] = []
        self.run_rows: dict[uuid.UUID, dict[str, Any]] = {}

    def _write(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        self.writes.append((name, kwargs))
        return {"id": str(kwargs.get("id") or uuid.uuid4())}

    # agent_config_store
    def create_session(self, **kwargs: Any) -> dict[str, Any]:
        return self._write("create_session", kwargs)

    def close_session(self, session_id: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._write("close_session", {"session_id": session_id, **kwargs})

    def get_session(self, *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        self.reads.append("get_session")
        return None

    def create_experiment(self, **kwargs: Any) -> dict[str, Any]:
        return self._write("create_experiment", kwargs)

    def get_experiment(self, *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        self.reads.append("get_experiment")
        return None

    def append_session_run(self, *_args: Any, **kwargs: Any) -> None:
        self._write("append_session_run", kwargs)

    def append_experiment_run(self, *_args: Any, **kwargs: Any) -> None:
        self._write("append_experiment_run", kwargs)

    def list_changelog(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        self.reads.append("list_changelog")
        return []

    # agent_config_service
    def apply_patches(self, **kwargs: Any) -> dict[str, Any]:
        return {**self._write("apply_patches", kwargs), "ok": True, "fingerprint": "fp-1"}

    # benchmark_runs_store
    def get_run(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        self.reads.append("get_run")
        return self.run_rows.get(run_id)

    async def start_benchmark_run(self, **kwargs: Any) -> dict[str, Any]:
        return self._write("start_benchmark_run", kwargs)

    def names(self) -> list[str]:
        return [name for name, _kwargs in self.writes]


@pytest.fixture
def stores(monkeypatch: pytest.MonkeyPatch) -> _Stores:
    s = _Stores()
    monkeypatch.setattr(act, "agent_config_store", s)
    monkeypatch.setattr(act, "agent_config_service", s)
    monkeypatch.setattr(act, "benchmark_runs_store", s)
    monkeypatch.setattr(act, "start_benchmark_run", s.start_benchmark_run)
    monkeypatch.setattr(act, "compute_fingerprint", lambda **_kw: "fp-1")
    monkeypatch.setattr(act, "snapshot", lambda **_kw: {"fingerprint": "fp-1"})
    monkeypatch.setattr(act, "all_knobs", lambda: [{"id": "runtime_knob", "layer": "runtime", "writable": False}])
    monkeypatch.setattr(act, "load_knob_registry", lambda: {"version": 3})
    monkeypatch.setattr(
        act,
        "knob_by_id",
        lambda knob_id: {"id": knob_id, "layer": "operator" if knob_id == OPERATOR_KNOB else "runtime"},
    )
    return s


def _signed_in(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    *,
    site_role: str,
    capabilities: tuple[str, ...] = (),
    tenant_id: int = OWNER_TENANT,
) -> None:
    """The identity the shared in-process guard reads for this call."""
    monkeypatch.setattr(console_guard, "get_identity", lambda: (tenant_id, actor))
    monkeypatch.setattr(console_guard.db, "user_site_role", lambda _uid: site_role)
    monkeypatch.setattr(console_guard.db, "user_capabilities", lambda _uid: set(capabilities))
    monkeypatch.setattr(console_guard.db, "user_tenant_id", lambda _uid: tenant_id)


def _delegated(monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID) -> None:
    """A company admin: ``agent.assign`` granted, the legacy column saying whatever it likes."""
    monkeypatch.setattr(console_guard.db, "user_role", lambda _uid: "admin")
    _signed_in(monkeypatch, actor, site_role="site_user", capabilities=("agent.assign",))


def _site_admin(monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID) -> None:
    _signed_in(monkeypatch, actor, site_role="site_admin")


def _run(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return json.loads(act.HANDLERS[tool](arguments))


@pytest.fixture
def actor() -> uuid.UUID:
    return uuid.uuid4()


SESSION_ARGS = {"label": "nightly", "cohort_label": "cohort-a"}
PATCH = [{"knob_id": "runtime_knob", "value": 1}]


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("agent_config_knobs", {}),
        ("agent_config_snapshot", {}),
        ("agent_config_changelog", {}),
        ("agent_config_apply", {"patches": PATCH}),
        ("tuning_session_create", SESSION_ARGS),
        ("agents_list", {}),
        ("benchmark_run_start", {"suite": "routing-core", "profiles": [{"id": "p"}]}),
        ("benchmark_run_get", {"run_id": "11111111-1111-1111-1111-111111111111"}),
        ("benchmark_experiment_create", {"label": "exp"}),
    ],
)
def test_anonymous_call_reaches_no_store(
    monkeypatch: pytest.MonkeyPatch, stores: _Stores, tool: str, arguments: dict[str, Any]
) -> None:
    monkeypatch.setattr(console_guard, "get_identity", lambda: (1, None))

    out = _run(tool, arguments)

    assert out["ok"] is False
    assert "authentication" in out["error"]
    assert stores.writes == []
    assert stores.reads == []


@pytest.mark.parametrize(
    ("tool", "arguments", "expected"),
    [
        ("agent_config_knobs", {}, "agent.assign"),
        ("agent_config_changelog", {}, "agent.assign"),
        ("tuning_session_create", SESSION_ARGS, "agent.assign"),
        ("agents_list", {}, "agent.assign"),
        ("benchmark_run_start", {"suite": "routing-core", "profiles": [{"id": "p"}]}, "site admin required"),
        ("benchmark_run_get", {"run_id": "11111111-1111-1111-1111-111111111111"}, "site admin required"),
        ("benchmark_experiment_create", {"label": "exp"}, "site admin required"),
    ],
)
def test_legacy_admin_row_without_a_grant_gets_nothing(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    stores: _Stores,
    tool: str,
    arguments: dict[str, Any],
    expected: str,
) -> None:
    # ``users.role == 'admin'`` was the whole test for this console. The canonical
    # identity says site_user and nothing was granted, so there is nothing to reach.
    monkeypatch.setattr(console_guard.db, "user_role", lambda _uid: "admin")
    _signed_in(monkeypatch, actor, site_role="site_user")

    out = _run(tool, arguments)

    assert out["ok"] is False
    assert expected in out["error"]
    assert stores.writes == []
    assert stores.reads == []


def test_delegated_holder_tunes_their_own_company(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _delegated(monkeypatch, actor)

    out = _run("tuning_session_create", SESSION_ARGS)

    assert out["ok"] is True
    assert [name for name, _ in stores.writes] == ["create_session"]
    assert stores.writes[0][1]["tenant_id"] == OWNER_TENANT


def test_delegated_holder_reads_knobs_without_writing(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _delegated(monkeypatch, actor)

    out = _run("agent_config_knobs", {})

    assert out["ok"] is True
    assert out["registry_version"] == 3
    assert stores.writes == []


def test_benchmark_work_is_closed_to_a_delegated_holder(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    # ``agent.assign`` is the tuning capability; the benchmark routes never delegate it
    # and neither does the console, even though the tool sits in the same module.
    _delegated(monkeypatch, actor)

    out = _run("benchmark_run_start", {"suite": "routing-core", "profiles": [{"id": "p"}]})

    assert out["ok"] is False
    assert out["error"] == "site admin required"
    assert stores.names() == []


def test_apply_with_a_benchmark_trigger_needs_site_admin(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _delegated(monkeypatch, actor)

    out = _run("agent_config_apply", {"patches": PATCH, "trigger_benchmark": True, "benchmark": {"profiles": [{"id": "p"}]}})

    assert out["ok"] is False
    assert out["error"] == "triggering a benchmark run requires site admin"
    # The route asks this before it writes, so a caller who cannot spend the compute
    # cannot bank the patch either.
    assert stores.names() == []


def test_site_admin_trigger_reaches_the_benchmark(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _site_admin(monkeypatch, actor)

    out = _run("agent_config_apply", {"patches": PATCH, "trigger_benchmark": True, "benchmark": {"profiles": [{"id": "p"}]}})

    assert out["ok"] is True
    assert stores.names() == ["apply_patches", "start_benchmark_run"]
    assert stores.writes[1][1]["tenant_id"] == OWNER_TENANT


def test_operator_layer_knob_needs_site_admin(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    # Such a knob writes the single ``operator_settings`` row, which has no tenant column:
    # the caller's company confinement does not reach it, so the route refuses it and so
    # must the console.
    _delegated(monkeypatch, actor)

    out = _run("agent_config_apply", {"patches": [{"knob_id": OPERATOR_KNOB, "value": True}]})

    assert out["ok"] is False
    assert OPERATOR_KNOB in out["error"]
    assert "site admin" in out["error"]
    assert stores.names() == []


def test_site_admin_may_write_an_operator_layer_knob(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _site_admin(monkeypatch, actor)

    out = _run("agent_config_apply", {"patches": [{"knob_id": OPERATOR_KNOB, "value": True}]})

    assert out["ok"] is True
    assert stores.names() == ["apply_patches"]


def test_benchmark_run_of_another_company_reads_as_missing(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _site_admin(monkeypatch, actor)
    foreign = uuid.uuid4()
    stores.run_rows[foreign] = {"id": str(foreign), "tenant_id": OTHER_TENANT}

    out = _run("benchmark_run_get", {"run_id": str(foreign)})

    assert out["ok"] is False
    # Same wording as a run that does not exist: a 403 would confirm whose run it is.
    assert out["error"] == "benchmark run not found"


def test_benchmark_run_of_the_callers_company_is_readable(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _site_admin(monkeypatch, actor)
    own = uuid.uuid4()
    stores.run_rows[own] = {"id": str(own), "tenant_id": OWNER_TENANT, "report_json": {"big": True}}

    out = _run("benchmark_run_get", {"run_id": str(own)})

    assert out["ok"] is True
    assert out["run"]["id"] == str(own)
    assert "report_json" not in out["run"]
