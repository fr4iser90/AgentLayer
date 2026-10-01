"""The reviewer console asks each mirrored route's own two questions.

Measured here before it was fixed: one helper (``_admin_tid_uid``) decided all fifteen
tools from ``users.role``, a column the rest of the platform stopped trusting — so what a
caller could reach had nothing to do with what they were granted. A legacy ``admin`` row
held all fifteen, including the nine whose routes (``/v1/admin/benchmarks/*``) carry no
capability slug and admit a site admin only, plus the run trace behind ``observability.read``;
an account the column called ``user`` held none, granted or not.

The gate per tool was read off the route it mirrors (``benchmarks_admin_api.py``,
``benchmarks_experiments_api.py``, ``agent_config_admin_api.py``, ``run_traces_admin_api.py``)
and the assertions are about the stores: a denied call must not have touched one, an allowed
call must carry the caller's own company into the read.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from apps.backend.domain.access.capabilities import CAP_AGENT_ASSIGN, CAP_OBSERVABILITY_READ
from apps.backend.infrastructure.identity import console_access as console_guard
from plugins.tools.platform.reviewer import audit as reviewer

OWNER_TENANT = 7
OTHER_TENANT = 9

# The nine tools whose routes carry no capability slug: ``require_site_admin`` is all they ask.
SITE_WIDE_TOOLS = (
    "benchmark_analysis_get",
    "benchmark_cohorts_list",
    "benchmark_cohort_compare",
    "benchmark_stats_get",
    "benchmark_experiment_get",
    "benchmark_experiment_report",
    "benchmark_run_get",
    "review_submit",
    "review_get",
)
# The five whose routes ask ``require_admin_scope(request, agent.assign)``.
ASSIGN_TOOLS = (
    "agent_config_snapshot",
    "agent_config_fingerprint",
    "agent_config_changelog",
    "agents_get",
    "review_recommend_patches",
)
# Which store call each tool's successful read turns into.
READ_OF = {
    "benchmark_analysis_get": "list_runs_for_stats",
    "benchmark_cohorts_list": "list_runs_for_stats",
    "benchmark_cohort_compare": "list_runs_for_stats",
    "benchmark_stats_get": "list_runs_for_stats",
    "benchmark_experiment_get": "get_experiment",
    "benchmark_experiment_report": "experiment_report",
    "benchmark_run_get": "benchmark_get_run",
    "agent_config_snapshot": "snapshot",
    "agent_config_fingerprint": "fingerprint_response",
    "agent_config_changelog": "list_changelog",
    "agents_get": "registry_get_agent",
    "review_recommend_patches": "draft_patches",
    "review_submit": "run_review",
    "review_get": "get_review",
    "run_trace_get": "trace_get_run",
}

EXPERIMENT_ID = str(uuid.uuid4())
REVIEW_ID = str(uuid.uuid4())
BENCH_RUN_ID = str(uuid.uuid4())
AGENT_RUN_ID = str(uuid.uuid4())

ARGS: dict[str, dict[str, Any]] = {
    "benchmark_analysis_get": {},
    "benchmark_cohorts_list": {},
    "benchmark_cohort_compare": {"cohort_a": "before", "cohort_b": "after"},
    "benchmark_stats_get": {},
    "benchmark_experiment_get": {"experiment_id": EXPERIMENT_ID},
    "benchmark_experiment_report": {"experiment_id": EXPERIMENT_ID},
    "benchmark_run_get": {"run_id": BENCH_RUN_ID},
    "agent_config_snapshot": {},
    "agent_config_fingerprint": {},
    "agent_config_changelog": {},
    "agents_get": {"agent_id": "coding"},
    "review_recommend_patches": {"patches": [{"knob_id": "runtime_knob", "value": 1}]},
    "review_submit": {"summary": "drift on routing cases"},
    "review_get": {"review_id": REVIEW_ID},
    "run_trace_get": {"run_id": AGENT_RUN_ID},
}


class _Ledger:
    """Which store method ran for which company, so a denial can be proven silent."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def record(self, name: str, tenant_id: Any = None) -> None:
        self.calls.append((name, None if tenant_id is None else int(tenant_id)))

    def names(self) -> list[str]:
        return [name for name, _tenant in self.calls]

    def tenant_of(self, name: str) -> int | None:
        for called, tenant in self.calls:
            if called == name:
                return tenant
        raise AssertionError(f"{name} did not run; calls were {self.names()}")


class _ConfigStores:
    """``agent_config_store`` / ``agent_config_service`` — tenant-scoped reads, drafting only."""

    def __init__(self, ledger: _Ledger) -> None:
        self.ledger = ledger
        self.experiments: dict[str, int] = {EXPERIMENT_ID: OWNER_TENANT}
        self.reviews: dict[str, int] = {REVIEW_ID: OWNER_TENANT}

    def get_experiment(self, experiment_id: Any, *, tenant_id: int | None = None) -> dict[str, Any] | None:
        self.ledger.record("get_experiment", tenant_id)
        if self.experiments.get(str(experiment_id)) != tenant_id:
            return None
        return {"id": str(experiment_id)}

    def experiment_report(self, experiment_id: Any, *, tenant_id: int | None = None) -> dict[str, Any] | None:
        self.ledger.record("experiment_report", tenant_id)
        if self.experiments.get(str(experiment_id)) != tenant_id:
            return None
        return {"id": str(experiment_id), "reviews": []}

    def get_review(self, review_id: Any, *, tenant_id: int | None = None) -> dict[str, Any] | None:
        self.ledger.record("get_review", tenant_id)
        if self.reviews.get(str(review_id)) != tenant_id:
            return None
        return {"id": str(review_id), "verdict": "neutral"}

    def list_changelog(self, tenant_id: int | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
        self.ledger.record("list_changelog", tenant_id)
        return []

    def draft_patches(self, *, tenant_id: int | None = None, **_kwargs: Any) -> dict[str, Any]:
        # Drafting is the whole tool: it must never reach ``apply_patches``.
        self.ledger.record("draft_patches", tenant_id)
        return {"patches": [], "applied": 0}


class _BenchmarkStore:
    def __init__(self, ledger: _Ledger) -> None:
        self.ledger = ledger
        self.runs: dict[str, int] = {BENCH_RUN_ID: OWNER_TENANT}

    def list_runs_for_stats(self, *, tenant_id: int | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
        self.ledger.record("list_runs_for_stats", tenant_id)
        return []

    def get_run(self, run_id: Any) -> dict[str, Any] | None:
        # Unscoped by design — the handler compares the row's company with the caller's,
        # exactly as ``/v1/admin/benchmarks/runs/{run_id}`` does.
        self.ledger.record("benchmark_get_run")
        home = self.runs.get(str(run_id))
        if home is None:
            return None
        return {"id": str(run_id), "tenant_id": home}


class _TraceStores:
    def __init__(self, ledger: _Ledger) -> None:
        self.ledger = ledger
        self.agent_runs: dict[str, int] = {AGENT_RUN_ID: OWNER_TENANT}

    def get_run(self, *, run_id: Any, tenant_id: int | None = None) -> dict[str, Any] | None:
        self.ledger.record("trace_get_run", tenant_id)
        if self.agent_runs.get(str(run_id)) != tenant_id:
            return None
        return {"id": str(run_id), "status": "completed"}

    def list_runs(self, **_kwargs: Any) -> list[dict[str, Any]]:
        self.ledger.record("list_child_runs")
        return []

    def get_task(self, **_kwargs: Any) -> dict[str, Any] | None:
        self.ledger.record("get_task")
        return None

    @staticmethod
    def row_to_public(row: dict[str, Any]) -> dict[str, Any]:
        return dict(row)


class _Registry:
    """The code-defined agent registry — instance-wide, so its route carries no tenant read."""

    def __init__(self, ledger: _Ledger) -> None:
        self.ledger = ledger

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        self.ledger.record("registry_get_agent")
        return {"id": agent_id} if agent_id == "coding" else None


@dataclass
class _Stores:
    ledger: _Ledger
    config: _ConfigStores
    benchmarks: _BenchmarkStore
    traces: _TraceStores
    review_calls: list[dict[str, Any]]


def _payload(led: _Ledger, name: str, payload: dict[str, Any]):
    def call(*_args: Any, tenant_id: int | None = None, **_kwargs: Any) -> dict[str, Any]:
        led.record(name, tenant_id)
        return payload

    return call


@pytest.fixture
def stores(monkeypatch: pytest.MonkeyPatch) -> _Stores:
    led = _Ledger()
    config = _ConfigStores(led)
    benchmarks = _BenchmarkStore(led)
    traces = _TraceStores(led)
    monkeypatch.setattr(reviewer, "agent_config_store", config)
    monkeypatch.setattr(reviewer, "agent_config_service", config)
    monkeypatch.setattr(reviewer, "benchmark_runs_store", benchmarks)
    monkeypatch.setattr(reviewer, "agent_runs_store", traces)
    monkeypatch.setattr(reviewer, "agent_tasks_store", traces)
    monkeypatch.setattr(reviewer, "get_agent_registry", lambda: _Registry(led))
    monkeypatch.setattr(
        reviewer, "tool_invocations_for_run", lambda _run_id: [{"id": 1, "tool_name": "search"}]
    )
    for pure, payload in (
        ("analyze_runs", {"analysis": {}}),
        ("list_cohorts", {"cohorts": []}),
        ("compare_cohorts", {"delta": 0}),
        ("aggregate_benchmark_stats", {"stats": []}),
        ("snapshot", {"fingerprint": "fp-1"}),
        ("fingerprint_response", {"fingerprint": "fp-1"}),
    ):
        monkeypatch.setattr(reviewer, pure, _payload(led, pure, payload))
    review_calls: list[dict[str, Any]] = []

    def run_review(**kwargs: Any) -> dict[str, Any]:
        led.record("run_review", kwargs.get("tenant_id"))
        review_calls.append(kwargs)
        return {"id": REVIEW_ID}

    monkeypatch.setattr(reviewer, "run_review", run_review)
    return _Stores(ledger=led, config=config, benchmarks=benchmarks, traces=traces, review_calls=review_calls)


def _signed_in(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    *,
    site_role: str,
    capabilities: tuple[str, ...] = (),
    tenant_id: int = OWNER_TENANT,
) -> None:
    """The identity the shared in-process guard reads for this call.

    ``users.role`` is deliberately left unset: the console must not consult it, so nothing
    here has to set it for these callers to work.
    """
    monkeypatch.setattr(console_guard, "get_identity", lambda: (tenant_id, actor))
    monkeypatch.setattr(console_guard.db, "user_site_role", lambda _uid: site_role)
    monkeypatch.setattr(console_guard.db, "user_capabilities", lambda _uid: set(capabilities))
    monkeypatch.setattr(console_guard.db, "user_tenant_id", lambda _uid: tenant_id)


def _legacy_admin_row(monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID) -> None:
    """The old gate's only requirement, with a canonical identity that says otherwise."""
    monkeypatch.setattr(console_guard.db, "user_role", lambda _uid: "admin")
    _signed_in(monkeypatch, actor, site_role="site_user")


def _delegated(monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, *capabilities: str) -> None:
    _signed_in(monkeypatch, actor, site_role="site_user", capabilities=capabilities)


def _site_admin(monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID) -> None:
    _signed_in(monkeypatch, actor, site_role="site_admin")


def _run(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return json.loads(reviewer.HANDLERS[tool](arguments))


@pytest.fixture
def actor() -> uuid.UUID:
    return uuid.uuid4()


@pytest.mark.parametrize("tool", sorted(ARGS))
def test_anonymous_call_reaches_no_store(monkeypatch: pytest.MonkeyPatch, stores: _Stores, tool: str) -> None:
    monkeypatch.setattr(console_guard, "get_identity", lambda: (1, None))

    out = _run(tool, ARGS[tool])

    assert out["ok"] is False
    assert "authentication" in out["error"]
    assert stores.ledger.names() == []


@pytest.mark.parametrize("tool", sorted(SITE_WIDE_TOOLS))
def test_legacy_admin_row_reaches_no_benchmark_or_review_tool(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores, tool: str
) -> None:
    # ``users.role == 'admin'`` was the whole test for these nine. Their routes ask
    # ``require_site_admin`` and the canonical identity says ``site_user``, so there is
    # nothing here to reach — not a cohort list, not a review row.
    _legacy_admin_row(monkeypatch, actor)

    out = _run(tool, ARGS[tool])

    assert out["ok"] is False
    assert out["error"] == "site admin required"
    assert stores.ledger.names() == []


@pytest.mark.parametrize("tool", sorted(ASSIGN_TOOLS))
def test_legacy_admin_row_reaches_no_config_tool(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores, tool: str
) -> None:
    _legacy_admin_row(monkeypatch, actor)

    out = _run(tool, ARGS[tool])

    assert out["ok"] is False
    assert CAP_AGENT_ASSIGN in out["error"]
    assert stores.ledger.names() == []


def test_legacy_admin_row_reaches_no_run_trace(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _legacy_admin_row(monkeypatch, actor)

    out = _run("run_trace_get", ARGS["run_trace_get"])

    assert out["ok"] is False
    assert CAP_OBSERVABILITY_READ in out["error"]
    assert stores.ledger.names() == []


@pytest.mark.parametrize("tool", sorted(ASSIGN_TOOLS))
def test_delegated_holder_reads_their_own_company(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores, tool: str
) -> None:
    # A company admin the legacy column never admitted: the route's slug is now enough,
    # and the read carries their own company.
    _delegated(monkeypatch, actor, CAP_AGENT_ASSIGN)

    out = _run(tool, ARGS[tool])

    assert out["ok"] is True
    read = READ_OF[tool]
    assert stores.ledger.names() == [read]
    if read != "registry_get_agent":
        assert stores.ledger.tenant_of(read) == OWNER_TENANT


@pytest.mark.parametrize("tool", sorted(SITE_WIDE_TOOLS))
def test_benchmark_and_review_work_is_closed_to_a_delegated_holder(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores, tool: str
) -> None:
    # ``agent.assign`` is the config capability. The benchmark and review routes never
    # delegate it, and ``review.benchmark`` / ``review.config`` only pick which tools an
    # agent is given — they are not delegable slugs, so they buy nothing here either.
    _delegated(monkeypatch, actor, CAP_AGENT_ASSIGN)

    out = _run(tool, ARGS[tool])

    assert out["ok"] is False
    assert out["error"] == "site admin required"
    assert stores.ledger.names() == []


def test_run_trace_needs_observability_read(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _delegated(monkeypatch, actor, CAP_AGENT_ASSIGN)

    out = _run("run_trace_get", ARGS["run_trace_get"])

    assert out["ok"] is False
    assert CAP_OBSERVABILITY_READ in out["error"]
    assert stores.ledger.names() == []


def test_run_trace_holder_reads_their_own_company(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _delegated(monkeypatch, actor, CAP_OBSERVABILITY_READ)

    out = _run("run_trace_get", ARGS["run_trace_get"])

    assert out["ok"] is True
    assert stores.ledger.tenant_of("trace_get_run") == OWNER_TENANT
    assert out["tool_invocations"] == [{"id": 1, "tool_name": "search"}]


def test_run_trace_of_another_company_reads_as_missing(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _delegated(monkeypatch, actor, CAP_OBSERVABILITY_READ)
    foreign = uuid.uuid4()
    stores.traces.agent_runs[str(foreign)] = OTHER_TENANT

    out = _run("run_trace_get", {"run_id": str(foreign)})

    assert out["ok"] is False
    # Same wording as a run that does not exist: an "outside your company" answer would
    # confirm whose run it is.
    assert out["error"] == "run trace not found"
    # The tool-invocation read never happened: the run lookup is what answers for it.
    assert stores.ledger.names() == ["trace_get_run"]


@pytest.mark.parametrize(
    ("tool", "foreign_arguments"),
    [
        ("benchmark_experiment_get", {"experiment_id": "22222222-2222-2222-2222-222222222222"}),
        ("benchmark_experiment_report", {"experiment_id": "22222222-2222-2222-2222-222222222222"}),
        ("review_get", {"review_id": "33333333-3333-3333-3333-333333333333"}),
    ],
)
def test_rows_of_another_company_read_as_missing(
    monkeypatch: pytest.MonkeyPatch,
    actor: uuid.UUID,
    stores: _Stores,
    tool: str,
    foreign_arguments: dict[str, Any],
) -> None:
    _site_admin(monkeypatch, actor)

    out = _run(tool, foreign_arguments)

    assert out["ok"] is False
    assert out["error"] == {
        "benchmark_experiment_get": "experiment not found",
        "benchmark_experiment_report": "experiment not found",
        "review_get": "review not found",
    }[tool]
    # The scoped read is what hides the row, so the caller's company must be in it.
    assert stores.ledger.names() == [READ_OF[tool]]
    assert stores.ledger.tenant_of(READ_OF[tool]) == OWNER_TENANT


def test_benchmark_run_of_another_company_reads_as_missing(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    # Unlike the three above, this store read is unscoped: ``/v1/admin/benchmarks/runs/{id}``
    # fetches the row and compares its company itself, so the handler has to copy that too.
    _site_admin(monkeypatch, actor)
    foreign = uuid.uuid4()
    stores.benchmarks.runs[str(foreign)] = OTHER_TENANT

    out = _run("benchmark_run_get", {"run_id": str(foreign)})

    assert out["ok"] is False
    # Same wording as a run that does not exist: "outside your company" would name its owner.
    assert out["error"] == "benchmark run not found"


def test_benchmark_run_of_the_callers_company_is_readable(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _site_admin(monkeypatch, actor)

    out = _run("benchmark_run_get", ARGS["benchmark_run_get"])

    assert out["ok"] is True
    assert out["run"]["id"] == BENCH_RUN_ID


def test_review_submit_is_the_only_persisting_tool_and_keeps_the_callers_company(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    _site_admin(monkeypatch, actor)

    out = _run("review_submit", ARGS["review_submit"])

    assert out["ok"] is True
    assert stores.ledger.names() == ["run_review"]
    assert stores.ledger.tenant_of("run_review") == OWNER_TENANT
    # The route posts ``actor_type="user"`` because a human pressed the button. A console
    # must not sign a machine's verdict as a human's.
    assert stores.review_calls[0]["actor_type"] == "reviewer_agent"


def test_an_identity_without_a_company_reads_one_company_never_all(
    monkeypatch: pytest.MonkeyPatch, actor: uuid.UUID, stores: _Stores
) -> None:
    # These are tenant-scoped reads: a missing company narrows to company 1 rather than
    # dropping the filter and returning every company's runs.
    _site_admin(monkeypatch, actor)
    monkeypatch.setattr(reviewer.db, "user_tenant_id", lambda _uid: None)

    out = _run("benchmark_analysis_get", {})

    assert out["ok"] is True
    assert stores.ledger.tenant_of("list_runs_for_stats") == 1
