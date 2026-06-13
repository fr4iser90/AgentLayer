"""HTTP harness for live agent LLM benchmarks."""

from __future__ import annotations

import csv
import json
import logging
import os
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
import yaml

from tests.benchmarks.agent.bench_cleanup import cleanup_prefix, prepare_bench_sandbox_cleanup
from tests.benchmarks.agent.bench_profiles import BenchModelProfile, parse_profiles_from_env, profile_labels_filter
from tests.benchmarks.agent.bench_provider_registry import register_bench_llm_providers
from tests.benchmarks.agent.cases import (
    AgentScenario,
    SCENARIO_BY_ID,
    bench_dashboard_title,
    bench_workspace_name,
    bind_bench_run_prompt_locale,
    render_scenario_prompt,
    reset_bench_run_prompt_locale,
    resolve_prompt_locale,
    scenarios_for_tier,
)
from tests.benchmarks.agent.fixtures import (
    FixtureContext,
    apply_fixtures,
    collect_fixture_ids,
    fetch_dashboard,
    find_dashboard_by_title,
    fetch_git_changes,
    scenario_fixture_blocked,
    workspace_id_for_scenario,
)
from tests.benchmarks.agent.metrics import (
    RunMetrics,
    agent_run_id_from_ws_events,
    bench_ws_diagnostics,
    build_failure_export_report,
    build_run_metrics,
    extract_llm_stream_from_ws,
    live_snapshot_from_ws_events,
    tool_invocations_from_ws_events,
    tool_names_from_ws_events,
)
from tests.benchmarks.agent.rubrics import RubricOutcome, evaluate_rubric
from tests.benchmarks.agent.ws_runner import run_chat_via_websocket, timeline_capture_enabled
from tests.e2e.support.helpers import E2EClient, find_workspace_by_name, load_dotenv, operator_self_editing_enabled, require_server

logger = logging.getLogger(__name__)


class BenchmarkRunCancelled(Exception):
    """Admin cancelled a benchmark run (queued, between scenarios, or in-flight chat)."""


def _is_benchmark_server_unavailable(exc: BaseException) -> bool:
    """True when the local API is gone (docker stop, crash, connection refused)."""
    if isinstance(exc, (ConnectionRefusedError, ConnectionResetError, BrokenPipeError)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in (111, 104, 103):
        return True
    msg = str(exc).lower()
    if any(
        needle in msg
        for needle in (
            "connection refused",
            "connect call failed",
            "service restart",
            "connection reset",
            "broken pipe",
        )
    ):
        return True
    if "1012" in msg and "restart" in msg:
        return True
    origin = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if origin is not None and origin is not exc and _is_benchmark_server_unavailable(origin):
        return True
    return False


def _raise_if_benchmark_server_unavailable(exc: BaseException) -> None:
    if _is_benchmark_server_unavailable(exc):
        raise BenchmarkRunCancelled("Benchmark stopped: server unavailable") from exc


def _is_shutdown_transport_error(message: str | None) -> bool:
    if not (message or "").strip():
        return False
    low = message.lower()
    return any(
        needle in low
        for needle in (
            "service restart",
            "connection refused",
            "connect call failed",
            "connection reset",
            "server unavailable",
            "1012",
        )
    )


REPO_ROOT = Path(__file__).resolve().parents[3]


def repo_root() -> Path:
    return REPO_ROOT


def load_bench_env() -> None:
    """Bench secrets/settings from repo ``.env`` (same as server / CLI)."""
    load_dotenv(REPO_ROOT / ".env")


def bench_base_url() -> str:
    from tests.e2e.support.helpers import resolve_local_agent_base_url

    return resolve_local_agent_base_url()


def bench_credentials() -> tuple[str, str]:
    email = (
        os.environ.get("AGENT_BENCH_EMAIL")
        or os.environ.get("AGENT_E2E_EMAIL")
        or os.environ.get("AGENT_INITIAL_ADMIN_EMAIL")
        or ""
    ).strip()
    password = (
        os.environ.get("AGENT_BENCH_PASSWORD")
        or os.environ.get("AGENT_E2E_PASSWORD")
        or os.environ.get("AGENT_INITIAL_ADMIN_PASSWORD")
        or ""
    ).strip()
    if not email or not password:
        raise RuntimeError(
            "Missing bench credentials (AGENT_BENCH_* or AGENT_INITIAL_ADMIN_* in .env)"
        )
    return email, password


def _apply_bench_user_env(
    *,
    run_as_user_id: uuid.UUID | str | None = None,
    friend_user_id: uuid.UUID | str | None = None,
    admin_user_id: uuid.UUID | str | None = None,
) -> None:
    if friend_user_id:
        os.environ["AGENT_BENCH_FRIEND_USER_ID"] = str(friend_user_id)
    else:
        os.environ.pop("AGENT_BENCH_FRIEND_USER_ID", None)
    if admin_user_id:
        os.environ["AGENT_BENCH_ADMIN_USER_ID"] = str(admin_user_id)
    else:
        os.environ.pop("AGENT_BENCH_ADMIN_USER_ID", None)
    if run_as_user_id:
        os.environ["AGENT_BENCH_RUN_AS_USER_ID"] = str(run_as_user_id)
    else:
        os.environ.pop("AGENT_BENCH_RUN_AS_USER_ID", None)


def resolve_bench_clients(
    *,
    run_as_user_id: uuid.UUID | str | None = None,
    friend_user_id: uuid.UUID | str | None = None,
    admin_user_id: uuid.UUID | str | None = None,
) -> tuple[Any, Any | None]:
    """Return (run_as E2EClient, admin E2EClient for fixture admin ops)."""
    from tests.e2e.support.helpers import E2EClient

    _apply_bench_user_env(
        run_as_user_id=run_as_user_id,
        friend_user_id=friend_user_id,
        admin_user_id=admin_user_id,
    )

    if run_as_user_id:
        run_client = E2EClient.for_user_id(run_as_user_id, timeout=None)
    else:
        email, password = bench_credentials()
        run_client = E2EClient.login(email, password, timeout=None)

    admin_client: Any | None = None
    if admin_user_id:
        admin_client = E2EClient.for_user_id(admin_user_id, timeout=None)
    elif run_client.role == "admin":
        admin_client = run_client

    if admin_client and admin_client.user_id != run_client.user_id:
        os.environ["AGENT_BENCH_ADMIN_USER_ID"] = admin_client.user_id

    return run_client, admin_client


def _bench_token_refresh_interval_s() -> float:
    """Re-mint bench JWTs before ``ACCESS_TOKEN_EXPIRE_MINUTES`` (default 15)."""
    raw = (os.environ.get("AGENT_BENCH_TOKEN_REFRESH_MINUTES") or "10").strip()
    try:
        minutes = float(raw)
    except ValueError:
        minutes = 10.0
    return max(60.0, minutes * 60.0)


@dataclass
class BenchSession:
    """Mutable HTTP session for long benchmark runs (JWT refresh across profiles/scenarios)."""

    run_as_user_id: uuid.UUID | str | None
    friend_user_id: uuid.UUID | str | None
    admin_user_id: uuid.UUID | str | None
    client: E2EClient
    admin_client: E2EClient | None
    _last_refresh_monotonic: float = field(default_factory=time.monotonic)

    @classmethod
    def open(
        cls,
        *,
        run_as_user_id: uuid.UUID | str | None = None,
        friend_user_id: uuid.UUID | str | None = None,
        admin_user_id: uuid.UUID | str | None = None,
    ) -> BenchSession:
        client, admin_client = resolve_bench_clients(
            run_as_user_id=run_as_user_id,
            friend_user_id=friend_user_id,
            admin_user_id=admin_user_id,
        )
        return cls(
            run_as_user_id=run_as_user_id,
            friend_user_id=friend_user_id,
            admin_user_id=admin_user_id,
            client=client,
            admin_client=admin_client,
        )

    def _close_client(self, row: E2EClient | None) -> None:
        if row is None:
            return
        try:
            row.close()
        except Exception:
            pass

    def refresh(self, *, force: bool = False) -> None:
        if not force and (time.monotonic() - self._last_refresh_monotonic) < _bench_token_refresh_interval_s():
            return
        old_client = self.client
        old_admin = self.admin_client
        client, admin_client = resolve_bench_clients(
            run_as_user_id=self.run_as_user_id,
            friend_user_id=self.friend_user_id,
            admin_user_id=self.admin_user_id,
        )
        self.client = client
        self.admin_client = admin_client
        self._last_refresh_monotonic = time.monotonic()
        if old_client.http is not self.client.http:
            self._close_client(old_client)
        if (
            old_admin is not None
            and old_admin is not old_client
            and old_admin.http is not self.client.http
            and (self.admin_client is None or old_admin.http is not self.admin_client.http)
        ):
            self._close_client(old_admin)

    def refresh_if_due(self) -> None:
        self.refresh(force=False)

    def admin_for_ops(self) -> E2EClient:
        return self.admin_client if self.admin_client is not None else self.client

    def close(self) -> None:
        if self.admin_client is not None and self.admin_client.http is not self.client.http:
            self._close_client(self.admin_client)
        self._close_client(self.client)
        self.admin_client = None


@dataclass
class ModelProfile:
    label: str
    catalog_owned_by: str
    model: str
    agent_id: str = "general"


_ASSISTANT_CONTENT_MAX = 12_000
_LIVE_PERSIST_MIN_S = 2.0


def _store_assistant_content(content: str | None) -> tuple[str, str, bool]:
    """Return (excerpt, stored_content, truncated)."""
    text = (content or "").strip()
    if len(text) <= _ASSISTANT_CONTENT_MAX:
        return text[:400], text, False
    clipped = text[:_ASSISTANT_CONTENT_MAX]
    return text[:400], clipped, True


@dataclass
class ScenarioResult:
    run_id: str
    scenario_id: str
    profile_label: str
    model: str
    catalog_owned_by: str
    agent_id: str
    passed: bool
    score: float
    failure_reason: str | None
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    tool_call_count: int
    tool_names: list[str]
    agent_run_id: str | None
    assistant_excerpt: str
    scenario_prompt: str = ""
    prompt_locale: str = "en"
    assistant_content: str = ""
    assistant_content_truncated: bool = False
    skipped: bool = False
    fixtures: list[str] = field(default_factory=list)
    error: str | None = None
    http_status: int | None = None
    run_metrics: dict[str, Any] | None = None
    rubric_failure_reason: str | None = None
    transport_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchRunReport:
    run_id: str
    started_at: str
    base_url: str
    git_sha: str | None
    tier_max: int
    manifest_path: str
    resource_prefix: str
    profiles: list[ModelProfile] = field(default_factory=list)
    profiles_source: str = ""
    fixtures_applied: list[str] = field(default_factory=list)
    fixtures_skipped: dict[str, str] = field(default_factory=dict)
    bench_cleanup: dict[str, Any] | None = None
    bench_cleanup_finish: dict[str, Any] | None = None
    prompt_locale: str = "en"
    results: list[ScenarioResult] = field(default_factory=list)
    in_flight: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "base_url": self.base_url,
            "git_sha": self.git_sha,
            "tier_max": self.tier_max,
            "manifest_path": self.manifest_path,
            "resource_prefix": self.resource_prefix,
            "profiles": [asdict(p) for p in self.profiles],
            "profiles_source": self.profiles_source,
            "fixtures_applied": self.fixtures_applied,
            "fixtures_skipped": self.fixtures_skipped,
            "bench_cleanup": self.bench_cleanup,
            "bench_cleanup_finish": self.bench_cleanup_finish,
            "prompt_locale": self.prompt_locale,
            "results": [r.to_dict() for r in self.results],
            "in_flight": self.in_flight,
        }


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:
        return None


def _resolve_manifest_path(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / "benchmarks" / path)


def _merge_manifest_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, val in overlay.items():
        if key == "includes":
            continue
        if key in ("scenarios", "fixtures") and isinstance(val, list):
            existing = list(merged.get(key) or [])
            for item in val:
                if item not in existing:
                    existing.append(item)
            merged[key] = existing
        elif key == "defaults" and isinstance(val, dict):
            defaults = dict(merged.get("defaults") or {})
            defaults.update(val)
            merged["defaults"] = defaults
        else:
            merged[key] = val
    return merged


def _load_manifest_raw(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"invalid manifest: {path}")

    includes = raw.get("includes")
    if includes:
        include_path = includes if isinstance(includes, str) else includes[0]
        inc = _load_manifest_raw(_resolve_manifest_path(Path(include_path)))
        return _merge_manifest_dict(inc, raw)

    profiles_from = raw.get("profiles_from")
    if profiles_from and not raw.get("profiles"):
        prof_path = path.parent / str(profiles_from)
        if not prof_path.is_file():
            prof_path = _resolve_manifest_path(Path(profiles_from))
        prof_raw = yaml.safe_load(prof_path.read_text(encoding="utf-8"))
        if isinstance(prof_raw, dict) and prof_raw.get("profiles"):
            raw = dict(raw)
            raw["profiles"] = prof_raw["profiles"]

    return raw


def load_manifest(path: Path) -> tuple[
    list[ModelProfile],
    list[str],
    int,
    dict[str, Any],
    list[str],
    str,
]:
    raw = _load_manifest_raw(path)
    tier_max = int(raw.get("tier_max") or 1)
    scenario_ids = [str(s) for s in (raw.get("scenarios") or [])]
    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    manifest_fixtures = [str(f) for f in (raw.get("fixtures") or [])]
    resource_prefix = str(raw.get("resource_prefix") or os.environ.get("AGENT_BENCH_PREFIX") or "bench-")

    profiles: list[ModelProfile] = []
    for row in raw.get("profiles") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        owned = str(row.get("catalog_owned_by") or "").strip()
        model = str(row.get("model") or "").strip()
        agent_id = str(row.get("agent_id") or "general").strip() or "general"
        if not label or not owned:
            continue
        profiles.append(
            ModelProfile(label=label, catalog_owned_by=owned, model=model, agent_id=agent_id)
        )
    if not profiles and not parse_profiles_from_env():
        raise ValueError(f"manifest has no profiles: {path}")
    return profiles, scenario_ids, tier_max, defaults, manifest_fixtures, resource_prefix


def profiles_from_admin_endpoints(client: E2EClient) -> list[ModelProfile]:
    """Enabled rows from Admin → Interfaces → LLM endpoints (keys stay in DB)."""
    from apps.backend.infrastructure.model_catalog_providers import db_catalog_provider_id

    payload = client.get_json("/v1/admin/external-llm/endpoints")
    rows = payload.get("endpoints") if isinstance(payload.get("endpoints"), list) else []
    out: list[ModelProfile] = []
    for ep in rows:
        if not isinstance(ep, dict):
            continue
        if ep.get("enabled") is False:
            continue
        if not str(ep.get("base_url") or "").strip():
            continue
        eid = int(ep["id"])
        model = str(ep.get("model_agent") or ep.get("model_default") or "").strip()
        out.append(
            ModelProfile(
                label=str(ep.get("label") or f"endpoint-{eid}"),
                catalog_owned_by=db_catalog_provider_id(eid),
                model=model,
                agent_id="general",
            )
        )
    return out


def resolve_benchmark_profiles(
    manifest_profiles: list[ModelProfile],
    *,
    client: E2EClient | None = None,
    run_id: str | None = None,
) -> tuple[list[ModelProfile], str, object | None]:
    """
    Priority:
    1. AGENT_BENCH_LLM_* in .env (optional CLI override)
    2. enabled Admin → LLM endpoints in DB (when client available)
    3. manifest profiles, filtered by AGENT_BENCH_PROFILES
    4. all manifest profiles

    Returns (profiles, source_label, BenchProviderRegistry|None for restore).
    """
    env_rows = parse_profiles_from_env()
    registry = None
    if env_rows:
        if client is not None and run_id and any(r.base_url for r in env_rows):
            env_rows, registry = register_bench_llm_providers(client, env_rows, run_id=run_id)
        missing_catalog = [r for r in env_rows if not r.catalog_owned_by]
        if missing_catalog:
            labels = ", ".join(r.label for r in missing_catalog)
            raise ValueError(
                f"bench profile(s) missing catalog after register: {labels}. "
                "Set AGENT_BENCH_LLM_N_BASE_URL or AGENT_BENCH_LLM_N_CATALOG."
            )
        return [
            ModelProfile(
                label=r.label,
                catalog_owned_by=r.catalog_owned_by,
                model=r.model,
                agent_id=r.agent_id,
            )
            for r in env_rows
        ], "env (AGENT_BENCH_LLM_*)", registry

    if client is not None:
        db_profiles = profiles_from_admin_endpoints(client)
        if db_profiles:
            labels = profile_labels_filter()
            if labels:
                by_label = {p.label: p for p in db_profiles}
                missing = [lb for lb in labels if lb not in by_label]
                if missing:
                    known = ", ".join(sorted(by_label)) or "(none)"
                    raise ValueError(
                        f"AGENT_BENCH_PROFILES unknown label(s): {missing}. Known: {known}"
                    )
                return [by_label[lb] for lb in labels], f"db endpoints filter ({','.join(labels)})", None
            return db_profiles, "admin external-llm endpoints (DB)", None

    labels = profile_labels_filter()
    if labels:
        by_label = {p.label: p for p in manifest_profiles}
        missing = [lb for lb in labels if lb not in by_label]
        if missing:
            known = ", ".join(sorted(by_label)) or "(none)"
            raise ValueError(
                f"AGENT_BENCH_PROFILES unknown label(s): {missing}. Known: {known}"
            )
        return [by_label[lb] for lb in labels], f"manifest filter ({','.join(labels)})", None

    if not manifest_profiles:
        raise ValueError(
            "No benchmark profiles. Add LLM endpoints in Admin → Interfaces, "
            "or set AGENT_BENCH_LLM_1_* in .env, or profiles in benchmarks/manifests/_profiles.yaml"
        )
    return list(manifest_profiles), "manifest (_profiles.yaml)", None


def _resolve_scenarios(
    manifest_ids: list[str],
    tier_max: int,
    only_ids: list[str] | None = None,
) -> list[AgentScenario]:
    if only_ids:
        out: list[AgentScenario] = []
        for sid in only_ids:
            sc = SCENARIO_BY_ID.get(sid)
            if sc is None:
                raise ValueError(f"unknown scenario id: {sid}")
            out.append(sc)
        return out
    if manifest_ids:
        out = []
        for sid in manifest_ids:
            sc = SCENARIO_BY_ID.get(sid)
            if sc is None:
                raise ValueError(f"unknown scenario id in manifest: {sid}")
            if sc.tier <= tier_max:
                out.append(sc)
        return out
    return scenarios_for_tier(tier_max)


def _env_truthy(name: str, *, default: str = "") -> bool:
    return (os.environ.get(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def _render_scenario_prompt(scenario: AgentScenario, fixture_ctx: FixtureContext) -> str:
    return render_scenario_prompt(scenario, fixture_ctx)


def _effective_agent_id(profile: ModelProfile, scenario: AgentScenario) -> str:
    if scenario.agent_id and scenario.agent_id != "general":
        return scenario.agent_id
    return profile.agent_id or scenario.agent_id or "general"


def _dashboard_state_for_rubric(
    client: E2EClient,
    *,
    scenario: AgentScenario,
    fixture_ctx: FixtureContext,
) -> tuple[dict[str, Any] | None, str | None]:
    expected_title = bench_dashboard_title(scenario, fixture_ctx.prefix)
    try:
        if scenario.rubric == "d1_dashboard_create":
            title = expected_title or f"{fixture_ctx.prefix}create"
            return find_dashboard_by_title(client, title), title
        if expected_title:
            return find_dashboard_by_title(client, expected_title), expected_title
    except httpx.HTTPError as exc:
        _raise_if_benchmark_server_unavailable(exc)
    return None, None


def _find_workspace_for_rubric(client: E2EClient, ws_name: str) -> dict[str, Any] | None:
    try:
        return find_workspace_by_name(client, ws_name)
    except httpx.HTTPError as exc:
        _raise_if_benchmark_server_unavailable(exc)
        return None


def _workspace_row_for_rubric(
    client: E2EClient,
    *,
    scenario: AgentScenario,
    fixture_ctx: FixtureContext,
) -> dict[str, Any] | None:
    ws_name = bench_workspace_name(scenario, fixture_ctx.prefix)
    if not ws_name:
        return None
    return _find_workspace_for_rubric(client, ws_name)


def _git_state_for_rubric(
    client: E2EClient,
    *,
    scenario: AgentScenario,
    fixture_ctx: FixtureContext,
) -> dict[str, Any] | None:
    ws_name = bench_workspace_name(scenario, fixture_ctx.prefix)
    if not ws_name:
        return None
    ws = _find_workspace_for_rubric(client, ws_name)
    if not ws:
        return None
    ws_id = str(ws.get("id") or "").strip()
    if not ws_id:
        return None
    try:
        summary = fetch_git_changes(client, ws_id)
    except httpx.HTTPError:
        return None
    if not isinstance(summary, dict):
        return None
    for path in ("README.md", "README", "readme.md"):
        try:
            detail = fetch_git_changes(client, ws_id, file_path=path)
        except httpx.HTTPError:
            continue
        if isinstance(detail, dict) and (
            detail.get("has_changes") or str(detail.get("diff") or "").strip()
        ):
            return {**summary, "file_diff": detail}
    files = summary.get("files") if isinstance(summary.get("files"), list) else []
    if files and isinstance(files[0], dict):
        first_path = str(files[0].get("path") or files[0].get("file") or "").strip()
        if first_path:
            try:
                detail = fetch_git_changes(client, ws_id, file_path=first_path)
                if isinstance(detail, dict):
                    return {**summary, "file_diff": detail}
            except httpx.HTTPError:
                pass
    return summary


def _extract_assistant_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            return str(msg.get("content") or "")
    return str(data.get("content") or "")


def _fetch_run_trace(
    client: E2EClient, agent_run_id: str | None
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any] | None]:
    if not agent_run_id or client.role != "admin":
        return [], [], None
    try:
        data = client.get_json(f"/v1/admin/run-traces/runs/{agent_run_id}")
    except httpx.HTTPError:
        return [], [], None
    invocations = data.get("tool_invocations") or []
    if not isinstance(invocations, list):
        invocations = []
    run = data.get("run") if isinstance(data.get("run"), dict) else None
    names = [str(i.get("tool_name") or "") for i in invocations if isinstance(i, dict)]
    return [n for n in names if n], invocations, run


def _scenario_crash_result(
    *,
    run_id: str,
    scenario: AgentScenario,
    profile: ModelProfile,
    exc: BaseException,
    fixtures: list[str],
    fixture_ctx: FixtureContext | None = None,
) -> ScenarioResult:
    msg = str(exc).strip() or exc.__class__.__name__
    scenario_prompt = (
        _render_scenario_prompt(scenario, fixture_ctx) if fixture_ctx is not None else ""
    )
    return ScenarioResult(
        run_id=run_id,
        scenario_id=scenario.id,
        profile_label=profile.label,
        model=profile.model,
        catalog_owned_by=profile.catalog_owned_by,
        agent_id=_effective_agent_id(profile, scenario),
        passed=False,
        score=0.0,
        failure_reason=msg,
        latency_ms=0.0,
        prompt_tokens=None,
        completion_tokens=None,
        tool_call_count=0,
        tool_names=[],
        agent_run_id=None,
        assistant_excerpt="",
        scenario_prompt=scenario_prompt,
        prompt_locale=resolve_prompt_locale(),
        fixtures=fixtures,
        error=msg,
    )


def _skipped_result(
    *,
    run_id: str,
    scenario: AgentScenario,
    profile: ModelProfile,
    reason: str,
    fixtures: list[str],
    fixture_ctx: FixtureContext | None = None,
) -> ScenarioResult:
    scenario_prompt = (
        _render_scenario_prompt(scenario, fixture_ctx) if fixture_ctx is not None else ""
    )
    return ScenarioResult(
        run_id=run_id,
        scenario_id=scenario.id,
        profile_label=profile.label,
        model=profile.model,
        catalog_owned_by=profile.catalog_owned_by,
        agent_id=profile.agent_id,
        passed=False,
        score=0.0,
        failure_reason=reason,
        latency_ms=0.0,
        prompt_tokens=None,
        completion_tokens=None,
        tool_call_count=0,
        tool_names=[],
        agent_run_id=None,
        assistant_excerpt="",
        scenario_prompt=scenario_prompt,
        prompt_locale=resolve_prompt_locale(),
        skipped=True,
        fixtures=fixtures,
        error="skipped",
    )


def _create_chat_conversation(
    client: E2EClient,
    *,
    profile: ModelProfile,
    scenario: AgentScenario,
    workspace_id: str | None,
    benchmark_run_id: uuid.UUID | None = None,
) -> str | None:
    """Create a server conversation the same way ChatPage.startNewChat does."""
    payload: dict[str, Any] = {
        "title": f"bench {scenario.id}",
        "mode": "agent",
        "model": profile.model,
        "messages": [],
        "agent_log": {"v": 2, "current": [], "turns": []},
        "agent_id": _effective_agent_id(profile, scenario),
        "model_catalog_owned_by": profile.catalog_owned_by,
    }
    if workspace_id:
        payload["workspace_id"] = workspace_id
    if benchmark_run_id is not None:
        payload["benchmark_run_id"] = str(benchmark_run_id)
    try:
        data = client.post_json("/v1/user/conversations", payload)
        conv = data.get("conversation") or {}
        cid = conv.get("id")
        return str(cid) if cid else None
    except httpx.HTTPError as exc:
        _raise_if_benchmark_server_unavailable(exc)
        logger.warning("benchmark conversation create failed for %s: %s", scenario.id, exc)
        return None


def _build_chat_body(
    *,
    profile: ModelProfile,
    scenario: AgentScenario,
    scenario_prompt: str,
    workspace_id: str | None,
    conversation_id: str | None,
    benchmark_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Chat-parity body; benchmarks always enable LLM stream for admin WS live preview."""
    body: dict[str, Any] = {
        "model": profile.model,
        "messages": [{"role": "user", "content": scenario_prompt}],
        "agent_id": _effective_agent_id(profile, scenario),
        "agent_model_catalog_owned_by": profile.catalog_owned_by,
        "agent_stream_llm": True,
    }
    if workspace_id:
        body["workspace_id"] = workspace_id
    if conversation_id:
        body["conversation_id"] = conversation_id
    if benchmark_run_id is not None:
        body["benchmark_run_id"] = str(benchmark_run_id)
    if scenario.plain_completion:
        body["agent_plain_completion"] = True
    return body


def _apply_bench_run_limits(
    body: dict[str, Any],
    *,
    max_tool_rounds_override: int | None,
) -> None:
    """Optional admin run cap — only when explicitly set (chat uses server default otherwise)."""
    if max_tool_rounds_override is not None:
        body["agent_max_tool_rounds"] = max_tool_rounds_override


def run_scenario(
    client: E2EClient,
    *,
    profile: ModelProfile,
    scenario: AgentScenario,
    run_id: str,
    fixture_ctx: FixtureContext,
    defaults: dict[str, Any],
    on_live: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    scenario_timeout_sec: float | None = None,
    max_tool_rounds_override: int | None = None,
    benchmark_run_id: uuid.UUID | None = None,
    prompt_locale: str | None = None,
) -> ScenarioResult:
    fixture_list = list(scenario.requires)
    if not profile.model:
        return ScenarioResult(
            run_id=run_id,
            scenario_id=scenario.id,
            profile_label=profile.label,
            model=profile.model,
            catalog_owned_by=profile.catalog_owned_by,
            agent_id=profile.agent_id,
            passed=False,
            score=0.0,
            failure_reason="profile.model is empty — set model id in manifest profiles",
            latency_ms=0.0,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_count=0,
            tool_names=[],
            agent_run_id=None,
            assistant_excerpt="",
            fixtures=fixture_list,
            error="missing model",
        )

    scenario_prompt = _render_scenario_prompt(scenario, fixture_ctx)
    ws_id = workspace_id_for_scenario(fixture_ctx, scenario.requires)
    conversation_id = _create_chat_conversation(
        client,
        profile=profile,
        scenario=scenario,
        workspace_id=ws_id,
        benchmark_run_id=benchmark_run_id,
    )
    body = _build_chat_body(
        profile=profile,
        scenario=scenario,
        scenario_prompt=scenario_prompt,
        workspace_id=ws_id,
        conversation_id=conversation_id,
        benchmark_run_id=benchmark_run_id,
    )
    _apply_bench_run_limits(body, max_tool_rounds_override=max_tool_rounds_override)
    effective_agent = str(body["agent_id"] or "")

    t0 = time.perf_counter()
    error: str | None = None
    http_status: int | None = None
    data: dict[str, Any] = {}
    ws_events: list[dict[str, Any]] = []
    capture_mode = "http"

    use_ws = timeline_capture_enabled()
    if use_ws:
        try:
            capture_mode = "websocket"
            ws_buf: list[dict[str, Any]] = []

            def _on_ws_event(msg: dict[str, Any]) -> None:
                ws_buf.append(msg)
                if on_live is not None:
                    on_live(
                        live_snapshot_from_ws_events(
                            ws_buf,
                            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                        )
                    )

            data, ws_events, ws_err = run_chat_via_websocket(
                base_url=bench_base_url(),
                token=client.token,
                body=body,
                on_event=_on_ws_event,
                cancel_check=cancel_check,
                timeout_sec=scenario_timeout_sec,
            )
            if ws_err and not data:
                if _is_shutdown_transport_error(ws_err):
                    raise BenchmarkRunCancelled("Benchmark stopped: server unavailable")
                error = ws_err
            elif ws_err:
                error = ws_err
        except BenchmarkRunCancelled:
            raise
        except Exception as exc:
            _raise_if_benchmark_server_unavailable(exc)
            logger.warning("benchmark ws capture failed, falling back to HTTP: %s", exc)
            use_ws = False
            ws_events = []
            data = {}

    if not use_ws or (use_ws and not data and not error):
        if not use_ws:
            capture_mode = "http"
        try:
            http_timeout = scenario_timeout_sec if scenario_timeout_sec and scenario_timeout_sec > 0 else None
            resp = client.http.post(
                "/v1/chat/completions",
                json=body,
                timeout=http_timeout,
            )
            http_status = resp.status_code
            if resp.status_code >= 400:
                error = f"HTTP {resp.status_code}: {resp.text[:500]}"
            else:
                payload = resp.json()
                data = payload if isinstance(payload, dict) else {}
        except httpx.HTTPError as exc:
            _raise_if_benchmark_server_unavailable(exc)
            error = str(exc)

    latency_ms = (time.perf_counter() - t0) * 1000.0

    content = _extract_assistant_content(data)
    if not content.strip() and ws_events:
        stream = extract_llm_stream_from_ws(ws_events)
        stream_parts: list[str] = []
        if stream.get("reasoning"):
            stream_parts.append(str(stream["reasoning"]))
        if stream.get("text"):
            stream_parts.append(str(stream["text"]))
        if stream_parts:
            content = "\n\n".join(stream_parts)
    agent_run_id = str(data.get("agent_run_id") or "") or None
    if not agent_run_id and ws_events:
        agent_run_id = agent_run_id_from_ws_events(ws_events)

    tool_names, invocations, agent_run = _fetch_run_trace(client, agent_run_id)
    if ws_events:
        ws_tool_names = tool_names_from_ws_events(ws_events)
        ws_invocations = tool_invocations_from_ws_events(ws_events)
        if len(ws_tool_names) > len(tool_names):
            tool_names = ws_tool_names
        if len(ws_invocations) > len(invocations):
            invocations = ws_invocations
        elif not invocations and ws_invocations:
            invocations = ws_invocations

    cache_disabled = body.get("cache_prompt") is False if "cache_prompt" in body else None
    run_metrics_obj: RunMetrics = build_run_metrics(
        completion=data,
        ws_events=ws_events or None,
        tool_invocations=invocations,
        agent_run=agent_run,
        capture_mode=capture_mode,
        provider_cache_prompt_disabled=cache_disabled,
    )
    run_metrics_dict = run_metrics_obj.to_dict()
    if ws_events or error:
        diag = bench_ws_diagnostics(ws_events, error=error)
        if diag:
            run_metrics_dict["bench_diagnostics"] = diag
            if not agent_run_id and diag.get("agent_run_id_ws"):
                agent_run_id = str(diag["agent_run_id_ws"])
    if cache_disabled is not None or run_metrics_obj.provider_cached_prompt_tokens is not None:
        run_metrics_dict.setdefault("provider_cache", {})
        if cache_disabled is not None:
            run_metrics_dict["provider_cache"]["cache_prompt_disabled"] = cache_disabled
        if run_metrics_obj.provider_cached_prompt_tokens is not None:
            run_metrics_dict["provider_cache"]["cached_prompt_tokens"] = (
                run_metrics_obj.provider_cached_prompt_tokens
            )
    if error and http_status is not None:
        run_metrics_dict["http_status"] = http_status
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    prompt_tokens = run_metrics_obj.prompt_tokens
    if prompt_tokens is None and usage.get("prompt_tokens") is not None:
        prompt_tokens = int(usage["prompt_tokens"])
    completion_tokens = run_metrics_obj.completion_tokens
    if completion_tokens is None and usage.get("completion_tokens") is not None:
        completion_tokens = int(usage["completion_tokens"])

    dashboard_state, expected_title = _dashboard_state_for_rubric(
        client,
        scenario=scenario,
        fixture_ctx=fixture_ctx,
    )
    git_changes = _git_state_for_rubric(
        client,
        scenario=scenario,
        fixture_ctx=fixture_ctx,
    )
    workspace_row = _workspace_row_for_rubric(
        client,
        scenario=scenario,
        fixture_ctx=fixture_ctx,
    )

    rubric_kwargs: dict[str, Any] = {
        "content": content,
        "tool_names": tool_names,
        "tool_invocations": invocations,
        "latency_ms": latency_ms,
        "http_status": http_status,
        "indexed": fixture_ctx.indexed,
        "dashboard_state": dashboard_state,
        "expected_title": expected_title,
        "git_changes": git_changes,
        "workspace_row": workspace_row,
    }
    rubric_substantive: RubricOutcome = evaluate_rubric(
        scenario.rubric,
        error=None,
        **rubric_kwargs,
    )
    transport_error = (error or "").strip() or None
    rubric_failure = (
        None
        if rubric_substantive.passed
        else (rubric_substantive.failure_reason or "rubric failed")
    )
    passed = rubric_substantive.passed and transport_error is None
    score = 0.0 if not passed else rubric_substantive.score
    failure_reason = transport_error or rubric_failure

    excerpt, stored_content, content_truncated = _store_assistant_content(content)
    return ScenarioResult(
        run_id=run_id,
        scenario_id=scenario.id,
        profile_label=profile.label,
        model=profile.model,
        catalog_owned_by=profile.catalog_owned_by,
        agent_id=body["agent_id"],
        passed=passed,
        score=score,
        failure_reason=failure_reason,
        rubric_failure_reason=rubric_failure,
        transport_error=transport_error,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        tool_call_count=len(tool_names),
        tool_names=tool_names,
        agent_run_id=agent_run_id,
        assistant_excerpt=excerpt,
        scenario_prompt=scenario_prompt,
        prompt_locale=resolve_prompt_locale(),
        assistant_content=stored_content,
        assistant_content_truncated=content_truncated,
        fixtures=fixture_list,
        error=error,
        http_status=http_status,
        run_metrics=run_metrics_dict,
    )


def _bench_summary_from_report(report: BenchRunReport) -> dict[str, Any]:
    passed = sum(1 for r in report.results if r.passed and not r.skipped)
    executed = sum(1 for r in report.results if not r.skipped)
    return {
        "passed": passed,
        "executed": executed,
        "total": len(report.results),
        "skipped": sum(1 for r in report.results if r.skipped),
        "profiles_source": report.profiles_source,
    }


def _notify_progress(
    report: BenchRunReport,
    on_progress: Callable[[BenchRunReport], None] | None,
) -> None:
    if on_progress is not None:
        on_progress(report)


def _bench_in_flight_row(
    *,
    scenario: AgentScenario,
    profile: ModelProfile,
    fixture_ctx: FixtureContext,
    phase: str = "starting",
    detail: str = "",
) -> dict[str, Any]:
    return {
        "scenario_id": scenario.id,
        "profile_label": profile.label,
        "model": profile.model,
        "catalog_owned_by": profile.catalog_owned_by,
        "agent_id": _effective_agent_id(profile, scenario),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "detail": detail,
        "llm_round_count": 0,
        "tool_call_count": 0,
        "tool_names": [],
        "elapsed_ms": 0.0,
    }


def _make_live_pusher(
    report: BenchRunReport,
    on_progress: Callable[[BenchRunReport], None] | None,
) -> Callable[[dict[str, Any]], None]:
    last_persist = time.monotonic()

    def push(patch: dict[str, Any], *, force: bool = False) -> None:
        nonlocal last_persist
        if report.in_flight is None:
            return
        report.in_flight.update(patch)
        now = time.monotonic()
        if not force and (now - last_persist) < _LIVE_PERSIST_MIN_S:
            return
        last_persist = now
        _notify_progress(report, on_progress)

    return push


def run_benchmark(
    *,
    manifest_path: Path,
    tier: int | None = None,
    profile_filter: str | None = None,
    scenario_filter: list[str] | None = None,
    extra_fixtures: list[str] | None = None,
    profiles_override: list[ModelProfile] | None = None,
    profiles_source_override: str | None = None,
    run_as_user_id: uuid.UUID | str | None = None,
    friend_user_id: uuid.UUID | str | None = None,
    admin_user_id: uuid.UUID | str | None = None,
    on_progress: Callable[[BenchRunReport], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    scenario_timeout_sec: float | None = None,
    max_tool_rounds_override: int | None = None,
    benchmark_run_id: uuid.UUID | str | None = None,
    cleanup_on_start: bool = True,
    cleanup_on_finish: bool = True,
    prompt_locale: str | None = None,
) -> BenchRunReport:
    from tests.benchmarks.agent.cases import available_prompt_locales, resolve_prompt_locale

    load_bench_env()
    locale = resolve_prompt_locale(prompt_locale)
    valid_locales = set(available_prompt_locales())
    if locale not in valid_locales:
        opts = ", ".join(sorted(valid_locales))
        raise ValueError(f"unsupported prompt_locale {locale!r} (available: {opts})")

    locale_token = bind_bench_run_prompt_locale(locale)
    os.environ.setdefault("AGENT_E2E_BASE_URL", bench_base_url())
    require_server()

    manifest_path = manifest_path.resolve()
    manifest_profiles, manifest_scenario_ids, tier_max_manifest, defaults, manifest_fixtures, resource_prefix = (
        load_manifest(manifest_path)
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"{resource_prefix.rstrip('-')}-{run_id}-"
    bench_run_uuid: uuid.UUID | None = None
    if benchmark_run_id is not None:
        try:
            bench_run_uuid = uuid.UUID(str(benchmark_run_id))
        except (ValueError, TypeError):
            bench_run_uuid = None

    session = BenchSession.open(
        run_as_user_id=run_as_user_id,
        friend_user_id=friend_user_id,
        admin_user_id=admin_user_id,
    )

    cleanup: dict[str, Any] | None = None
    if cleanup_on_start:
        try:
            cleanup = prepare_bench_sandbox_cleanup(session.client)
            logger.info("benchmark pre-run bench cleanup: %s", cleanup)
            if cleanup.get("has_benchmark_workspace_headroom") is False:
                logger.warning(
                    "benchmark workspace quota full after bench cleanup "
                    "(bench_count=%s bench_headroom=%s); W*/C* scenarios will be skipped",
                    (cleanup.get("after") or {}).get("bench_workspace_count"),
                    cleanup.get("benchmark_workspace_headroom"),
                )
            elif cleanup.get("has_workspace_headroom") is False:
                logger.warning(
                    "user workspace quota full after bench cleanup "
                    "(count=%s headroom=%s); non-bench scenarios may fail on workspace.create",
                    cleanup.get("after", {}).get("workspace_count"),
                    cleanup.get("workspace_headroom"),
                )
        except Exception as exc:
            cleanup = {"error": str(exc)}
            logger.warning("benchmark pre-run bench cleanup failed: %s", exc)

    provider_registry = None
    if profiles_override is not None:
        profiles = list(profiles_override)
        profiles_source = profiles_source_override or "override"
    else:
        profiles, profiles_source, provider_registry = resolve_benchmark_profiles(
            manifest_profiles,
            client=session.client,
            run_id=run_id,
        )
    tier_max = tier if tier is not None else tier_max_manifest
    scenarios = _resolve_scenarios(manifest_scenario_ids, tier_max, scenario_filter)
    if not scenarios:
        raise RuntimeError(f"no scenarios for tier_max={tier_max}")

    if profile_filter:
        profiles = [p for p in profiles if p.label == profile_filter]
        if not profiles:
            raise RuntimeError(f"profile not found: {profile_filter}")
        profiles_source = f"{profiles_source} + CLI --profile {profile_filter}"

    fixture_ids = collect_fixture_ids(
        [s.requires for s in scenarios],
        manifest_fixtures + (extra_fixtures or []),
    )

    fixture_ctx = FixtureContext(run_id=run_id, prefix=prefix)

    report = BenchRunReport(
        run_id=run_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        base_url=bench_base_url(),
        git_sha=_git_sha(),
        tier_max=tier_max,
        manifest_path=str(manifest_path),
        resource_prefix=prefix,
        profiles=list(profiles),
        profiles_source=profiles_source,
        bench_cleanup=cleanup,
        prompt_locale=locale,
    )

    self_editing_prev: bool | None = None
    if "agentlayer_self" in fixture_ids:
        admin_ops = session.admin_for_ops()
        if admin_ops.role == "admin":
            self_editing_prev = operator_self_editing_enabled(admin_ops)
            if not self_editing_prev:
                admin_ops.patch_json(
                    "/v1/admin/operator-settings",
                    {"workspace_allow_self_editing": True},
                )

    try:
        apply_fixtures(session.client, fixture_ctx, fixture_ids)
        report.fixtures_applied = sorted(fixture_ctx.applied)
        report.fixtures_skipped = dict(fixture_ctx.skipped)
        _notify_progress(report, on_progress)

        from tests.benchmarks.agent.project_run_runner import run_project_run_scenario

        def _record(result: ScenarioResult) -> None:
            report.results.append(result)
            _notify_progress(report, on_progress)

        for profile in profiles:
            session.refresh(force=True)
            for scenario in scenarios:
                if cancel_check and cancel_check():
                    raise BenchmarkRunCancelled("Benchmark cancelled by admin")
                session.refresh_if_due()
                block = scenario_fixture_blocked(fixture_ctx, scenario.requires)
                if block and any(
                    fid in fixture_ctx.skipped for fid in scenario.requires
                ):
                    _record(
                        _skipped_result(
                            run_id=run_id,
                            scenario=scenario,
                            profile=profile,
                            reason=block,
                            fixtures=list(scenario.requires),
                            fixture_ctx=fixture_ctx,
                        )
                    )
                    continue
                if scenario.skip_without_env and not _env_truthy(scenario.skip_without_env):
                    _record(
                        _skipped_result(
                            run_id=run_id,
                            scenario=scenario,
                            profile=profile,
                            reason=f"env {scenario.skip_without_env} not set",
                            fixtures=list(scenario.requires),
                            fixture_ctx=fixture_ctx,
                        )
                    )
                    continue
                if (
                    scenario.bench_workspace_suffix
                    and isinstance(cleanup, dict)
                    and cleanup.get("has_benchmark_workspace_headroom") is False
                ):
                    bench_headroom = cleanup.get("benchmark_workspace_headroom")
                    bench_left = (cleanup.get("after") or {}).get("bench_workspace_count")
                    _record(
                        _skipped_result(
                            run_id=run_id,
                            scenario=scenario,
                            profile=profile,
                            reason=(
                                "benchmark workspace quota full after cleanup "
                                f"(bench_headroom={bench_headroom}, bench_remaining={bench_left}); "
                                "use Admin → Benchmarks → Clean bench workspaces"
                            ),
                            fixtures=list(scenario.requires),
                            fixture_ctx=fixture_ctx,
                        )
                    )
                    continue
                if block:
                    _record(
                        ScenarioResult(
                            run_id=run_id,
                            scenario_id=scenario.id,
                            profile_label=profile.label,
                            model=profile.model,
                            catalog_owned_by=profile.catalog_owned_by,
                            agent_id=profile.agent_id,
                            passed=False,
                            score=0.0,
                            failure_reason=block,
                            latency_ms=0.0,
                            prompt_tokens=None,
                            completion_tokens=None,
                            tool_call_count=0,
                            tool_names=[],
                            agent_run_id=None,
                            assistant_excerpt="",
                            fixtures=list(scenario.requires),
                            error=block,
                        )
                    )
                    continue

                live_push = _make_live_pusher(report, on_progress)
                report.in_flight = _bench_in_flight_row(
                    scenario=scenario,
                    profile=profile,
                    fixture_ctx=fixture_ctx,
                    phase="starting",
                )
                live_push({}, force=True)

                def _on_live(patch: dict[str, Any]) -> None:
                    live_push(patch)

                try:
                    result = (
                        run_project_run_scenario(
                            session,
                            profile=profile,
                            scenario=scenario,
                            run_id=run_id,
                            fixture_ctx=fixture_ctx,
                            defaults=defaults,
                            on_live=_on_live,
                        )
                        if scenario.execution == "project_run"
                        else run_scenario(
                            session.client,
                            profile=profile,
                            scenario=scenario,
                            run_id=run_id,
                            fixture_ctx=fixture_ctx,
                            defaults=defaults,
                            on_live=_on_live,
                            cancel_check=cancel_check,
                            scenario_timeout_sec=scenario_timeout_sec,
                            max_tool_rounds_override=max_tool_rounds_override,
                            benchmark_run_id=bench_run_uuid,
                        )
                    )
                except BenchmarkRunCancelled:
                    raise
                except Exception as exc:
                    logger.exception(
                        "benchmark scenario %s profile %s crashed",
                        scenario.id,
                        profile.label,
                    )
                    result = _scenario_crash_result(
                        run_id=run_id,
                        scenario=scenario,
                        profile=profile,
                        exc=exc,
                        fixtures=list(scenario.requires),
                        fixture_ctx=fixture_ctx,
                    )
                finally:
                    report.in_flight = None
                    _notify_progress(report, on_progress)
                _record(result)
                if cancel_check and cancel_check():
                    raise BenchmarkRunCancelled("Benchmark cancelled by admin")
    finally:
        session.refresh(force=True)
        if self_editing_prev is False:
            try:
                session.admin_for_ops().patch_json(
                    "/v1/admin/operator-settings",
                    {"workspace_allow_self_editing": False},
                )
            except httpx.HTTPError:
                pass
        if provider_registry is not None:
            try:
                provider_registry.restore(session.admin_for_ops())
            except httpx.HTTPError:
                pass
        if cleanup_on_finish:
            try:
                run_stats = cleanup_prefix(
                    session.client,
                    prefix=prefix,
                    benchmark_run_id=bench_run_uuid,
                )
                finish_stats = prepare_bench_sandbox_cleanup(
                    session.client,
                    extra_deleted=run_stats,
                )
                finish_stats["run_prefix"] = prefix
                finish_stats["run_prefix_deleted"] = run_stats
                report.bench_cleanup_finish = finish_stats
                logger.info(
                    "benchmark post-run cleanup run_prefix=%s bench-*: %s",
                    prefix,
                    finish_stats,
                )
            except Exception as exc:
                report.bench_cleanup_finish = {"error": str(exc)}
                logger.warning("benchmark post-run cleanup failed: %s", exc)
        session.close()
        reset_bench_run_prompt_locale(locale_token)

    return report


def _scenario_insights_summary(run_metrics: dict[str, Any] | None) -> str:
    if not isinstance(run_metrics, dict):
        return ""
    diag = run_metrics.get("bench_diagnostics")
    if not isinstance(diag, dict):
        return ""
    insights = diag.get("insights")
    if not isinstance(insights, list):
        return ""
    return " | ".join(str(line).strip() for line in insights[:4] if str(line).strip())


def _bench_diagnostics(result: ScenarioResult) -> dict[str, Any]:
    rm = result.run_metrics if isinstance(result.run_metrics, dict) else {}
    diag = rm.get("bench_diagnostics")
    return diag if isinstance(diag, dict) else {}


def _workspace_create_name_from_tool_rounds(tool_rounds: list[dict[str, Any]]) -> str:
    for row in tool_rounds:
        name = str(row.get("name") or "").strip().lower()
        if name not in ("workspace.create", "workspaces.create", "create"):
            continue
        args = row.get("normalized_arguments")
        if isinstance(args, dict):
            nm = str(args.get("name") or "").strip()
            if nm:
                return nm
        wire = row.get("wire_arguments")
        if isinstance(wire, dict):
            nm = str(wire.get("name") or "").strip()
            if nm:
                return nm
        if isinstance(wire, str) and wire.strip():
            try:
                parsed = json.loads(wire)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                nm = str(parsed.get("name") or "").strip()
                if nm:
                    return nm
            return wire.strip()[:200]
    return ""


def _failure_export_debug_fields(
    result: ScenarioResult,
    *,
    resource_prefix: str | None = None,
) -> dict[str, Any]:
    """Extra columns for failures.json / failures CSV (debugging only)."""
    diag = _bench_diagnostics(result)
    session = diag.get("session") if isinstance(diag.get("session"), dict) else {}
    tool_rounds = diag.get("tool_rounds") if isinstance(diag.get("tool_rounds"), list) else []
    event_counts = diag.get("event_counts") if isinstance(diag.get("event_counts"), dict) else {}
    ws_errors = diag.get("ws_errors") if isinstance(diag.get("ws_errors"), list) else []

    forwarded = session.get("forwarded_tools")
    forwarded_names: list[str] = []
    if isinstance(forwarded, list):
        forwarded_names = [str(x).strip() for x in forwarded if str(x).strip()]

    expected_ws = ""
    if resource_prefix:
        scenario = SCENARIO_BY_ID.get(result.scenario_id)
        if scenario is not None:
            ws_name = bench_workspace_name(scenario, resource_prefix)
            if ws_name:
                expected_ws = ws_name

    delegate_calls = sum(
        1 for row in tool_rounds if str(row.get("name") or "").strip().lower() == "delegate"
    )

    err_parts: list[str] = []
    for row in ws_errors[-3:]:
        if not isinstance(row, dict):
            continue
        typ = str(row.get("type") or "").strip()
        detail = str(row.get("detail") or row.get("message") or "").strip()
        if typ or detail:
            err_parts.append(f"{typ}: {detail}"[:180] if detail else typ)

    report = build_failure_export_report(
        diag,
        transport_error=result.transport_error or result.error,
        rubric_failure=result.rubric_failure_reason,
        assistant_excerpt=result.assistant_excerpt,
    )
    subagent_ids = [
        str(sa.get("agent_id") or "").strip()
        for sa in (report.get("subagents") or [])
        if isinstance(sa, dict) and str(sa.get("agent_id") or "").strip()
    ]
    subagent_steps_lines: list[str] = []
    for sa in report.get("subagents") or []:
        if not isinstance(sa, dict):
            continue
        aid = str(sa.get("agent_id") or "subagent")
        for step in sa.get("steps") or []:
            if not isinstance(step, dict):
                continue
            tool = str(step.get("tool") or "?")
            phase = str(step.get("phase") or "?")
            ok = step.get("ok")
            ok_s = "" if ok is None else (" ok" if ok else " FAIL")
            err = str(step.get("error") or "").strip()
            line = f"{aid}/{tool} {phase}{ok_s}"
            if err:
                line += f": {err[:80]}"
            subagent_steps_lines.append(line)

    return {
        "agent_id": str(result.agent_id or ""),
        "effective_agent_id": str(session.get("effective_agent_id") or ""),
        "forwarded_tool_count": session.get("forwarded_tool_count"),
        "forwarded_tools": ", ".join(forwarded_names[:24])
        + (f" (+{len(forwarded_names) - 24})" if len(forwarded_names) > 24 else ""),
        "assistant_excerpt": (result.assistant_excerpt or "").strip()[:500],
        "expected_workspace_name": expected_ws,
        "workspace_create_name": _workspace_create_name_from_tool_rounds(tool_rounds),
        "delegate_call_count": delegate_calls,
        "subagent_start_count": int(event_counts.get("subagent_start_count") or 0),
        "ws_errors": " | ".join(err_parts),
        "report_summary": str(report.get("summary") or ""),
        "blocked_phase": str(report.get("blocked_phase") or ""),
        "blocked_detail": str(report.get("blocked_detail") or ""),
        "subagent_agents": ", ".join(subagent_ids),
        "subagent_steps": " | ".join(subagent_steps_lines[:12]),
        "parent_tool_rounds_json": json.dumps(
            report.get("parent_tool_rounds") or [], ensure_ascii=False
        )[:4000],
        "report": report,
    }


def scenario_export_row(result: ScenarioResult) -> dict[str, Any]:
    """Flat row for summary CSV (base columns)."""
    rm = result.run_metrics if isinstance(result.run_metrics, dict) else {}
    tools = ", ".join(result.tool_names[:12])
    if len(result.tool_names) > 12:
        tools += f" (+{len(result.tool_names) - 12})"
    return {
        "scenario_id": result.scenario_id,
        "profile_label": result.profile_label,
        "model": result.model,
        "skipped": result.skipped,
        "passed": result.passed,
        "transport_error": result.transport_error or result.error or "",
        "rubric_failure": result.rubric_failure_reason or "",
        "failure_reason": result.failure_reason or "",
        "insights": _scenario_insights_summary(rm),
        "tool_call_count": result.tool_call_count,
        "tools": tools,
        "llm_round_count": rm.get("llm_round_count", ""),
        "latency_ms": round(result.latency_ms, 1),
        "agent_run_id": result.agent_run_id or "",
    }


def failure_export_row(
    result: ScenarioResult,
    *,
    resource_prefix: str | None = None,
) -> dict[str, Any]:
    """Failures export: base row plus debug fields."""
    row = scenario_export_row(result)
    row.update(_failure_export_debug_fields(result, resource_prefix=resource_prefix))
    return row


def failures_from_report(report: BenchRunReport) -> list[dict[str, Any]]:
    return [
        failure_export_row(r, resource_prefix=report.resource_prefix)
        for r in report.results
        if not r.skipped and not r.passed
    ]


def write_report(report: BenchRunReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dir = out_dir / report.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "manifest.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )

    for result in report.results:
        safe_label = result.profile_label.replace("/", "_").replace(" ", "_")
        prof_dir = run_dir / safe_label
        prof_dir.mkdir(parents=True, exist_ok=True)
        (prof_dir / f"{result.scenario_id}.json").write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )

    csv_path = run_dir / "summary.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "scenario_id",
                "profile_label",
                "model",
                "skipped",
                "passed",
                "score",
                "latency_ms",
                "tool_call_count",
                "compaction_count",
                "llm_round_count",
                "context_utilization_pct",
                "total_tokens",
                "transport_error",
                "rubric_failure",
                "failure_reason",
                "insights",
                "tools",
            ],
        )
        writer.writeheader()
        for r in report.results:
            rm = r.run_metrics if isinstance(r.run_metrics, dict) else {}
            row = scenario_export_row(r)
            writer.writerow(
                {
                    "scenario_id": r.scenario_id,
                    "profile_label": r.profile_label,
                    "model": r.model,
                    "skipped": r.skipped,
                    "passed": r.passed,
                    "score": r.score,
                    "latency_ms": f"{r.latency_ms:.1f}",
                    "tool_call_count": r.tool_call_count,
                    "compaction_count": rm.get("compaction_count", 0),
                    "llm_round_count": rm.get("llm_round_count", 0),
                    "context_utilization_pct": rm.get("context_utilization_pct", ""),
                    "total_tokens": rm.get("total_tokens", ""),
                    "transport_error": row["transport_error"],
                    "rubric_failure": row["rubric_failure"],
                    "failure_reason": row["failure_reason"],
                    "insights": row["insights"],
                    "tools": row["tools"],
                }
            )

    failures = failures_from_report(report)
    (run_dir / "failures.json").write_text(
        json.dumps(
            {
                "run_id": report.run_id,
                "resource_prefix": report.resource_prefix,
                "failure_count": len(failures),
                "failures": failures,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return run_dir


def print_summary_table(report: BenchRunReport) -> None:
    print(f"\nAgent LLM benchmark run {report.run_id} (tier ≤ {report.tier_max})")
    print(f"  manifest:  {report.manifest_path}")
    print(f"  prefix:    {report.resource_prefix}")
    print(f"  base_url:  {report.base_url}")
    print(f"  git_sha:   {report.git_sha or '-'}")
    print(f"  profiles:  {len(report.profiles)} ({report.profiles_source})")
    for p in report.profiles:
        print(f"             - {p.label}: {p.catalog_owned_by} / {p.model or '(empty model)'}")
    print(f"  fixtures:  applied={report.fixtures_applied} skipped={report.fixtures_skipped or '-'}")
    print(f"  cases:     {len(report.results)}")
    executed = [r for r in report.results if not r.skipped]
    passed = sum(1 for r in executed if r.passed)
    skipped = sum(1 for r in report.results if r.skipped)
    print(f"  passed:    {passed}/{len(executed)} ({skipped} skipped)")
    print()
    for r in report.results:
        if r.skipped:
            mark = "SKIP"
        else:
            mark = "PASS" if r.passed else "FAIL"
        extra = f" — {r.failure_reason}" if r.failure_reason else ""
        rm = r.run_metrics if isinstance(r.run_metrics, dict) else {}
        compact = rm.get("compaction_count", 0)
        ctx_pct = rm.get("context_utilization_pct")
        ctx_s = f" ctx={ctx_pct}%" if ctx_pct is not None else ""
        print(
            f"  [{mark}] {r.profile_label} / {r.scenario_id}: "
            f"{r.latency_ms:.0f}ms tools={r.tool_call_count} compact={compact}{ctx_s} "
            f"score={r.score:.2f}{extra}"
        )
