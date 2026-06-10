"""Bench JWT refresh and multi-profile run continuity (multi-hour regression)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.benchmarks.agent import harness
from tests.benchmarks.agent.harness import (
    BenchSession,
    ModelProfile,
    ScenarioResult,
    _bench_token_refresh_interval_s,
    _scenario_crash_result,
    run_benchmark,
)
from tests.benchmarks.agent.cases import AgentScenario


class _FakeHttp:
    pass


class _FakeE2EClient:
    def __init__(self, *, token: str, user_id: str = "bench-user") -> None:
        self.http = _FakeHttp()
        self.token = token
        self.user_id = user_id
        self.role = "admin"
        self.email = "bench@example.com"

    def close(self) -> None:
        pass

    def get_json(self, path: str, **params: Any) -> dict[str, Any]:
        return {}

    def patch_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return {}


def _ok_result(*, run_id: str, profile: ModelProfile, scenario: AgentScenario) -> ScenarioResult:
    return ScenarioResult(
        run_id=run_id,
        scenario_id=scenario.id,
        profile_label=profile.label,
        model=profile.model,
        catalog_owned_by=profile.catalog_owned_by,
        agent_id=profile.agent_id,
        passed=True,
        score=1.0,
        failure_reason=None,
        latency_ms=1.0,
        prompt_tokens=1,
        completion_tokens=1,
        tool_call_count=0,
        tool_names=[],
        agent_run_id=None,
        assistant_excerpt="ok",
    )


def test_bench_token_refresh_interval_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_BENCH_TOKEN_REFRESH_MINUTES", "0.5")
    assert _bench_token_refresh_interval_s() == 60.0
    monkeypatch.setenv("AGENT_BENCH_TOKEN_REFRESH_MINUTES", "120")
    assert _bench_token_refresh_interval_s() == 7200.0


def test_bench_session_refresh_replaces_client(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = iter(["tok-a", "tok-b", "tok-c"])

    def fake_resolve(**_kwargs: Any) -> tuple[_FakeE2EClient, _FakeE2EClient]:
        tok = next(tokens)
        client = _FakeE2EClient(token=tok)
        return client, client

    monkeypatch.setattr(harness, "resolve_bench_clients", fake_resolve)
    session = BenchSession.open(run_as_user_id=uuid.uuid4())
    first = session.client
    session.refresh(force=True)
    assert session.client is not first
    assert session.client.token == "tok-b"
    session.close()


def test_bench_session_refresh_if_due_respects_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_resolve(**_kwargs: Any) -> tuple[_FakeE2EClient, _FakeE2EClient]:
        calls.append("resolve")
        return _FakeE2EClient(token=f"tok-{len(calls)}"), _FakeE2EClient(token=f"tok-{len(calls)}")

    monkeypatch.setattr(harness, "resolve_bench_clients", fake_resolve)
    monkeypatch.setenv("AGENT_BENCH_TOKEN_REFRESH_MINUTES", "30")
    session = BenchSession.open(run_as_user_id=uuid.uuid4())
    assert len(calls) == 1
    session.refresh_if_due()
    assert len(calls) == 1
    session._last_refresh_monotonic = time.monotonic() - 31 * 60
    session.refresh_if_due()
    assert len(calls) == 2
    session.close()


def test_run_benchmark_runs_all_profiles_with_forced_refresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: profile 2 must run even after a long profile 1 (JWT refresh between profiles)."""
    manifest = tmp_path / "mini.yaml"
    manifest.write_text(
        "version: 1\ntier_max: 1\n"
        "profiles:\n  - label: dummy\n    catalog_owned_by: provider_0\n    model: x\n"
        "scenarios:\n  - S2_simple_chat\n",
        encoding="utf-8",
    )
    profiles = [
        ModelProfile(label="llama", catalog_owned_by="provider_1", model="qwen-a"),
        ModelProfile(label="ollama", catalog_owned_by="provider_2", model="qwen-b"),
    ]
    profiles_seen: list[tuple[str, str]] = []
    refresh_forces: list[bool] = []
    real_refresh = BenchSession.refresh

    def track_refresh(self: BenchSession, *, force: bool = False) -> None:
        refresh_forces.append(force)
        real_refresh(self, force=force)

    token_seq = iter(["t0", "t1", "t2", "t3", "t4"])

    def fake_resolve(**_kwargs: Any) -> tuple[_FakeE2EClient, _FakeE2EClient]:
        tok = next(token_seq, "t-end")
        client = _FakeE2EClient(token=tok)
        return client, client

    def fake_run_scenario(
        client: _FakeE2EClient,
        *,
        profile: ModelProfile,
        scenario: AgentScenario,
        run_id: str,
        fixture_ctx: Any,
        defaults: dict[str, Any],
        on_live: Any = None,
        **_kwargs: Any,
    ) -> ScenarioResult:
        profiles_seen.append((profile.label, client.token))
        return _ok_result(run_id=run_id, profile=profile, scenario=scenario)

    monkeypatch.setattr(harness, "resolve_bench_clients", fake_resolve)
    monkeypatch.setattr(BenchSession, "refresh", track_refresh)
    monkeypatch.setattr(harness, "require_server", lambda: None)
    monkeypatch.setattr(harness, "apply_fixtures", lambda *a, **k: None)
    monkeypatch.setattr(harness, "run_scenario", fake_run_scenario)
    monkeypatch.setattr(harness, "_git_sha", lambda: None)

    report = run_benchmark(
        manifest_path=manifest,
        profiles_override=profiles,
        profiles_source_override="test",
    )

    assert [label for label, _ in profiles_seen] == ["llama", "ollama"]
    assert len(report.results) == 2
    assert all(r.passed for r in report.results)
    assert refresh_forces.count(True) >= 2


def test_run_benchmark_continues_after_scenario_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "mini.yaml"
    manifest.write_text(
        "version: 1\ntier_max: 1\n"
        "profiles:\n  - label: dummy\n    catalog_owned_by: provider_0\n    model: x\n"
        "scenarios:\n  - S2_simple_chat\n",
        encoding="utf-8",
    )
    profiles = [
        ModelProfile(label="p1", catalog_owned_by="provider_1", model="m1"),
        ModelProfile(label="p2", catalog_owned_by="provider_2", model="m2"),
    ]
    calls: list[str] = []

    def fake_run_scenario(
        _client: _FakeE2EClient,
        *,
        profile: ModelProfile,
        scenario: AgentScenario,
        run_id: str,
        fixture_ctx: Any,
        defaults: dict[str, Any],
        on_live: Any = None,
        **_kwargs: Any,
    ) -> ScenarioResult:
        calls.append(profile.label)
        if profile.label == "p1":
            raise httpx.HTTPStatusError(
                "401",
                request=httpx.Request("GET", "http://127.0.0.1:8080/v1/workspaces"),
                response=httpx.Response(401),
            )
        return _ok_result(run_id=run_id, profile=profile, scenario=scenario)

    def fake_resolve(**_kwargs: Any) -> tuple[_FakeE2EClient, _FakeE2EClient]:
        client = _FakeE2EClient(token="tok")
        return client, client

    monkeypatch.setattr(harness, "resolve_bench_clients", fake_resolve)
    monkeypatch.setattr(harness, "require_server", lambda: None)
    monkeypatch.setattr(harness, "apply_fixtures", lambda *a, **k: None)
    monkeypatch.setattr(harness, "run_scenario", fake_run_scenario)
    monkeypatch.setattr(harness, "_git_sha", lambda: None)

    report = run_benchmark(
        manifest_path=manifest,
        profiles_override=profiles,
        profiles_source_override="test",
    )

    assert calls == ["p1", "p2"]
    assert len(report.results) == 2
    assert report.results[0].passed is False
    assert report.results[1].passed is True
    assert "401" in (report.results[0].error or "")


def test_scenario_crash_result_shape() -> None:
    profile = ModelProfile(label="x", catalog_owned_by="provider_1", model="m")
    scenario = harness.SCENARIO_BY_ID["S2_simple_chat"]
    row = _scenario_crash_result(
        run_id="run",
        scenario=scenario,
        profile=profile,
        exc=RuntimeError("boom"),
        fixtures=[],
    )
    assert row.passed is False
    assert row.error == "boom"


def test_simulated_three_hour_profile_loop_refreshes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each profile boundary must force-refresh even if refresh_if_due would skip."""
    monkeypatch.setenv("AGENT_BENCH_TOKEN_REFRESH_MINUTES", "120")
    session = BenchSession(
        run_as_user_id=uuid.uuid4(),
        friend_user_id=None,
        admin_user_id=None,
        client=_FakeE2EClient(token="initial"),
        admin_client=_FakeE2EClient(token="initial"),
    )
    forced: list[bool] = []
    real_refresh = BenchSession.refresh

    def track_refresh(self: BenchSession, *, force: bool = False) -> None:
        forced.append(force)
        if force:
            self._last_refresh_monotonic = time.monotonic()
            self.client = _FakeE2EClient(token=f"tok-{len(forced)}")

    monkeypatch.setattr(BenchSession, "refresh", track_refresh)

    for _ in range(3):
        session.refresh(force=True)
        for _step in range(40):
            session.refresh_if_due()
            time.sleep(0)

    assert forced.count(True) == 3
