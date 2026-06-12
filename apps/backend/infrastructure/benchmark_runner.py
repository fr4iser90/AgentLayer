"""Execute agent LLM benchmarks in a background thread (admin UI)."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from apps.backend.infrastructure import benchmark_runs_store
from apps.backend.infrastructure.model_catalog_providers import db_catalog_provider_id

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]

_run_lock = asyncio.Lock()
_cancel_flags: dict[uuid.UUID, threading.Event] = {}


def request_benchmark_cancel(run_id: uuid.UUID) -> bool:
    """Signal cancellation for a queued/running run. Returns False if not active."""
    row = benchmark_runs_store.get_run(run_id)
    if not row:
        return False
    status = str(row.get("status") or "")
    if status not in ("queued", "running"):
        return False
    _cancel_flags.setdefault(run_id, threading.Event()).set()
    return True


def cancel_all_active_benchmark_runs() -> int:
    """Signal cancel for every queued/running run (process shutdown)."""
    count = 0
    try:
        for run_id in benchmark_runs_store.list_active_run_ids():
            _cancel_flags.setdefault(run_id, threading.Event()).set()
            count += 1
    except Exception:
        logger.warning("benchmark cancel-all: db lookup failed", exc_info=True)
    for run_id in list(_cancel_flags):
        if _cancel_flags[run_id].is_set():
            continue
        row = benchmark_runs_store.get_run(run_id)
        if row and str(row.get("status") or "") in ("queued", "running"):
            _cancel_flags[run_id].set()
            count += 1
    return count


def _cancel_check_for(run_id: uuid.UUID) -> Callable[[], bool]:
    return _cancel_flags.setdefault(run_id, threading.Event()).is_set


def _clear_cancel_flag(run_id: uuid.UUID) -> None:
    _cancel_flags.pop(run_id, None)


def list_suites() -> list[dict[str, Any]]:
    from tests.benchmarks.agent.catalog import list_suites_detailed

    return list_suites_detailed()


def benchmark_catalog() -> dict[str, Any]:
    from tests.benchmarks.agent.catalog import catalog_payload

    return catalog_payload()


def manifest_path_for_suite(suite: str) -> Path:
    from tests.benchmarks.agent.catalog import _SUITE_MANIFESTS

    rel = _SUITE_MANIFESTS.get(suite)
    if not rel:
        raise ValueError(f"unknown suite: {suite}")
    return _REPO_ROOT / rel


def list_benchmark_llm_providers() -> list[dict[str, Any]]:
    """Unified LLM providers for benchmarks: ``LLM_PROVIDER_*`` in .env plus Admin DB endpoints."""
    from apps.backend.infrastructure.model_catalog_providers import list_provider_specs
    from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

    db_enabled: dict[int, bool] = {}
    try:
        from apps.backend.infrastructure.db import db

        for row in db.external_llm_endpoints_list_all():
            db_enabled[int(row["id"])] = bool(row.get("enabled", True))
    except RuntimeError:
        pass

    seen_urls: set[str] = set()
    out: list[dict[str, Any]] = []
    for sp in list_provider_specs(force_refresh=True):
        base = (sp.base_url or "").strip()
        if not base:
            continue
        if sp.db_endpoint_id is not None and not db_enabled.get(sp.db_endpoint_id, True):
            continue
        url_key = (normalize_external_llm_base_url(base) or base).lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        out.append(
            {
                "catalog_owned_by": sp.provider_id,
                "label": sp.label,
                "base_url": base,
                "source": sp.source,
                "endpoint_id": sp.db_endpoint_id,
                "model_default": sp.model_default,
                "model_agent": sp.model_agent,
                "model_coding": sp.model_coding,
            }
        )
    return out


def _validate_profiles(raw_profiles: list[dict[str, Any]]) -> None:
    if not raw_profiles:
        raise ValueError("at least one profile required")
    ok = False
    for row in raw_profiles:
        if not isinstance(row, dict):
            continue
        if row.get("endpoint_id") is not None:
            ok = True
        elif str(row.get("base_url") or "").strip():
            ok = True
        elif str(row.get("catalog_owned_by") or "").strip():
            ok = True
    if not ok:
        raise ValueError("profiles must include endpoint_id, base_url, or catalog_owned_by")


def _build_model_profiles(
    profiles_raw: list[dict[str, Any]],
    *,
    client: Any,
    run_id_str: str,
) -> tuple[list[Any], Any | None]:
    from tests.benchmarks.agent.bench_profiles import BenchModelProfile
    from tests.benchmarks.agent.bench_provider_registry import register_bench_llm_providers
    from tests.benchmarks.agent.harness import ModelProfile

    bench_rows: list[BenchModelProfile] = []
    model_profiles: list[ModelProfile] = []

    for row in profiles_raw:
        if not isinstance(row, dict):
            continue
        catalog = str(row.get("catalog_owned_by") or "").strip()
        if catalog:
            model_profiles.append(
                ModelProfile(
                    label=str(row.get("label") or catalog),
                    catalog_owned_by=catalog,
                    model=str(row.get("model") or ""),
                    agent_id=str(row.get("agent_id") or "general"),
                )
            )
            continue
        if row.get("endpoint_id") is not None:
            eid = int(row["endpoint_id"])
            model_profiles.append(
                ModelProfile(
                    label=str(row.get("label") or f"endpoint-{eid}"),
                    catalog_owned_by=db_catalog_provider_id(eid),
                    model=str(row.get("model") or ""),
                    agent_id=str(row.get("agent_id") or "general"),
                )
            )
            continue
        base_url = str(row.get("base_url") or "").strip()
        if base_url:
            bench_rows.append(
                BenchModelProfile(
                    label=str(row.get("label") or "bench"),
                    catalog_owned_by="",
                    model=str(row.get("model") or ""),
                    agent_id=str(row.get("agent_id") or "general"),
                    base_url=base_url,
                    api_key=str(row.get("api_key") or ""),
                    api_header_name=str(row.get("api_header_name") or ""),
                )
            )
        elif row.get("catalog_owned_by"):
            model_profiles.append(
                ModelProfile(
                    label=str(row.get("label") or "bench"),
                    catalog_owned_by=str(row.get("catalog_owned_by") or ""),
                    model=str(row.get("model") or ""),
                    agent_id=str(row.get("agent_id") or "general"),
                )
            )

    registry = None
    if bench_rows:
        resolved, registry = register_bench_llm_providers(client, bench_rows, run_id=run_id_str)
        for r in resolved:
            model_profiles.append(
                ModelProfile(
                    label=r.label,
                    catalog_owned_by=r.catalog_owned_by,
                    model=r.model,
                    agent_id=r.agent_id,
                )
            )

    if not model_profiles:
        raise RuntimeError("no valid benchmark profiles")
    return model_profiles, registry


def _run_sync(
    run_id: uuid.UUID,
    *,
    suite: str,
    profiles_raw: list[dict[str, Any]],
    scenario_filter: list[str] | None = None,
    extra_fixtures: list[str] | None = None,
    tier_max: int | None = None,
    run_as_user_id: uuid.UUID | None = None,
    friend_user_id: uuid.UUID | None = None,
    admin_user_id: uuid.UUID | None = None,
    scenario_timeout_sec: float | None = None,
    max_tool_rounds_override: int | None = None,
    retain_workspaces: bool = False,
) -> None:
    from tests.benchmarks.agent.harness import (
        BenchmarkRunCancelled,
        load_bench_env,
        resolve_bench_clients,
        run_benchmark,
        write_report,
    )

    benchmark_runs_store.update_run(
        run_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )

    load_bench_env()
    from tests.e2e.support.helpers import resolve_local_agent_base_url

    os.environ["AGENT_E2E_BASE_URL"] = resolve_local_agent_base_url()

    manifest = manifest_path_for_suite(suite)
    registry = None
    admin_client = None
    run_client = None

    try:
        if _cancel_check_for(run_id)():
            raise BenchmarkRunCancelled("Benchmark cancelled before start")

        run_client, admin_client = resolve_bench_clients(
            run_as_user_id=run_as_user_id,
            friend_user_id=friend_user_id,
            admin_user_id=admin_user_id,
        )
        profile_client = admin_client or run_client
        model_profiles, registry = _build_model_profiles(
            profiles_raw,
            client=profile_client,
            run_id_str=run_id.hex[:12],
        )
        if admin_client is not None and admin_client.http is not run_client.http:
            admin_client.close()
            admin_client = None
        run_client.close()
        run_client = None

        def _persist_progress(report: Any) -> None:
            try:
                from tests.benchmarks.agent.harness import _bench_summary_from_report

                summary = _bench_summary_from_report(report)
                benchmark_runs_store.update_run(
                    run_id,
                    resource_prefix=report.resource_prefix or None,
                    summary_json=summary,
                    report_json=report.to_dict(),
                )
            except Exception:
                logger.warning("benchmark progress persist failed", exc_info=True)

        report = run_benchmark(
            manifest_path=manifest,
            profiles_override=model_profiles,
            profiles_source_override="admin-ui",
            scenario_filter=scenario_filter,
            extra_fixtures=extra_fixtures,
            tier=tier_max,
            run_as_user_id=run_as_user_id,
            friend_user_id=friend_user_id,
            admin_user_id=admin_user_id,
            on_progress=_persist_progress,
            cancel_check=_cancel_check_for(run_id),
            scenario_timeout_sec=scenario_timeout_sec,
            max_tool_rounds_override=max_tool_rounds_override,
            benchmark_run_id=run_id,
            cleanup_on_start=True,
            cleanup_on_finish=not retain_workspaces,
        )

        results_dir = _REPO_ROOT / "benchmarks" / "results"
        write_report(report, results_dir)

        summary = {
            "passed": sum(1 for r in report.results if r.passed and not r.skipped),
            "executed": sum(1 for r in report.results if not r.skipped),
            "total": len(report.results),
            "skipped": sum(1 for r in report.results if r.skipped),
            "profiles_source": report.profiles_source,
        }

        benchmark_runs_store.update_run(
            run_id,
            status="completed",
            finished_at=datetime.now(timezone.utc),
            resource_prefix=report.resource_prefix,
            summary_json=summary,
            report_json=report.to_dict(),
        )
    except BenchmarkRunCancelled:
        logger.info("benchmark run %s cancelled", run_id)
        summary = {
            "passed": 0,
            "executed": 0,
            "total": 0,
            "skipped": 0,
            "profiles_source": "admin-ui",
        }
        report_json: dict[str, Any] | None = None
        try:
            row = benchmark_runs_store.get_run(run_id)
            if row and isinstance(row.get("report_json"), dict):
                report_json = row["report_json"]
                results = report_json.get("results") or []
                summary = {
                    "passed": sum(1 for r in results if r.get("passed") and not r.get("skipped")),
                    "executed": sum(1 for r in results if not r.get("skipped")),
                    "total": len(results),
                    "skipped": sum(1 for r in results if r.get("skipped")),
                    "profiles_source": report_json.get("profiles_source") or "admin-ui",
                }
                report_json = {**report_json, "in_flight": None}
        except Exception:
            logger.warning("benchmark cancel summary failed", exc_info=True)
        benchmark_runs_store.update_run(
            run_id,
            status="cancelled",
            finished_at=datetime.now(timezone.utc),
            error_text="Benchmark cancelled by admin.",
            summary_json=summary,
            report_json=report_json,
        )
    except Exception as exc:
        logger.exception("benchmark run %s failed", run_id)
        benchmark_runs_store.update_run(
            run_id,
            status="failed",
            finished_at=datetime.now(timezone.utc),
            error_text=str(exc)[:4000],
        )
    finally:
        _clear_cancel_flag(run_id)
        if admin_client is not None and run_client is not None and admin_client.http is not run_client.http:
            admin_client.close()
        if run_client is not None:
            run_client.close()
        if registry is not None:
            try:
                from tests.benchmarks.agent.harness import bench_credentials
                from tests.e2e.support.helpers import E2EClient

                if admin_user_id:
                    restore_client = E2EClient.for_user_id(admin_user_id)
                else:
                    email, password = bench_credentials()
                    restore_client = E2EClient.login(email, password)
                try:
                    registry.restore(restore_client)
                finally:
                    restore_client.close()
            except Exception:
                logger.warning("benchmark registry restore failed", exc_info=True)


async def schedule_benchmark_run(
    run_id: uuid.UUID,
    *,
    suite: str,
    profiles: list[dict[str, Any]],
    scenario_filter: list[str] | None = None,
    extra_fixtures: list[str] | None = None,
    tier_max: int | None = None,
    run_as_user_id: uuid.UUID | None = None,
    friend_user_id: uuid.UUID | None = None,
    admin_user_id: uuid.UUID | None = None,
    scenario_timeout_sec: float | None = None,
    max_tool_rounds_override: int | None = None,
    retain_workspaces: bool = False,
) -> None:
    async with _run_lock:
        await asyncio.to_thread(
            _run_sync,
            run_id,
            suite=suite,
            profiles_raw=profiles,
            scenario_filter=scenario_filter,
            extra_fixtures=extra_fixtures,
            tier_max=tier_max,
            run_as_user_id=run_as_user_id,
            friend_user_id=friend_user_id,
            admin_user_id=admin_user_id,
            scenario_timeout_sec=scenario_timeout_sec,
            max_tool_rounds_override=max_tool_rounds_override,
            retain_workspaces=retain_workspaces,
        )


async def start_benchmark_run(
    *,
    tenant_id: int,
    user_id: uuid.UUID | None,
    suite: str,
    profiles: list[dict[str, Any]],
    scenarios: list[str] | None = None,
    fixtures: list[str] | None = None,
    tier_max: int | None = None,
    run_as_user_id: uuid.UUID | None = None,
    friend_user_id: uuid.UUID | None = None,
    admin_user_id: uuid.UUID | None = None,
    scenario_timeout_sec: float | None = None,
    max_tool_rounds_override: int | None = None,
    retain_workspaces: bool = False,
) -> dict[str, Any]:
    from tests.benchmarks.agent.catalog import _SUITE_MANIFESTS

    if benchmark_runs_store.any_running(tenant_id=tenant_id):
        raise RuntimeError("a benchmark is already running for this tenant")
    if suite not in _SUITE_MANIFESTS:
        raise ValueError(f"unknown suite: {suite}")
    _validate_profiles(profiles)
    if scenarios is not None and not scenarios:
        raise ValueError("at least one scenario required")
    manifest = str(manifest_path_for_suite(suite))
    effective_run_as = run_as_user_id or user_id
    run_config = {
        "profiles": profiles,
        "scenarios": scenarios,
        "fixtures": fixtures,
        "tier_max": tier_max,
        "run_as_user_id": str(effective_run_as) if effective_run_as else None,
        "friend_user_id": str(friend_user_id) if friend_user_id else None,
        "admin_user_id": str(admin_user_id) if admin_user_id else None,
        "scenario_timeout_sec": scenario_timeout_sec,
        "max_tool_rounds_override": max_tool_rounds_override,
        "retain_workspaces": retain_workspaces,
    }
    row = benchmark_runs_store.create_run(
        tenant_id=tenant_id,
        user_id=effective_run_as,
        suite=suite,
        manifest_path=manifest,
        profiles=run_config,
    )
    rid = uuid.UUID(str(row["id"]))
    asyncio.create_task(
        schedule_benchmark_run(
            rid,
            suite=suite,
            profiles=profiles,
            scenario_filter=scenarios,
            extra_fixtures=fixtures,
            tier_max=tier_max,
            run_as_user_id=effective_run_as,
            friend_user_id=friend_user_id,
            admin_user_id=admin_user_id,
            scenario_timeout_sec=scenario_timeout_sec,
            max_tool_rounds_override=max_tool_rounds_override,
            retain_workspaces=retain_workspaces,
        )
    )
    return row
