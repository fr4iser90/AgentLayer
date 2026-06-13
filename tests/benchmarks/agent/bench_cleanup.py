"""Delete benchmark sandbox resources by DB marker (and legacy bench-* names)."""

from __future__ import annotations

import uuid
from typing import Any

from tests.e2e.support.helpers import E2EClient

BENCH_RESOURCE_PREFIX = "bench-"


def matches_bench_prefix(name: str, prefix: str = BENCH_RESOURCE_PREFIX) -> bool:
    return bool(prefix) and (name or "").startswith(prefix)


def list_user_workspaces(client: E2EClient) -> list[dict[str, Any]]:
    data = client.get_json("/v1/workspaces")
    rows = data.get("workspaces") or []
    return [ws for ws in rows if isinstance(ws, dict)]


def workspace_quota_snapshot(client: E2EClient, *, bench_prefix: str = BENCH_RESOURCE_PREFIX) -> dict[str, int]:
    from apps.backend.infrastructure.benchmark_resource_service import workspace_quota_snapshot as _snap

    snap = _snap(uuid.UUID(client.user_id), include_legacy_prefix=True)
    return {
        "workspace_count": int(snap.get("workspace_count") or 0),
        "bench_workspace_count": int(snap.get("bench_workspace_count") or 0),
        "non_bench_workspace_count": int(snap.get("non_bench_workspace_count") or 0),
    }


def cleanup_bench_dashboards(
    client: E2EClient,
    *,
    dry_run: bool = False,
    benchmark_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Delete bench sandboxes dashboards for the client user (workspaces untouched)."""
    from apps.backend.infrastructure.benchmark_resource_service import (
        cleanup_benchmark_dashboards,
    )

    return cleanup_benchmark_dashboards(
        uuid.UUID(client.user_id),
        benchmark_run_id=benchmark_run_id,
        include_legacy_prefix=benchmark_run_id is None,
        dry_run=dry_run,
    )


def cleanup_prefix(
    client: E2EClient,
    *,
    prefix: str,
    dry_run: bool = False,
    include_conversations: bool = False,
    benchmark_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Delete benchmark sandboxes for the client user (marker + optional legacy prefix)."""
    from apps.backend.infrastructure.benchmark_resource_service import cleanup_benchmark_sandboxes

    del prefix, include_conversations  # legacy args; cleanup uses DB markers + bench-* fallback
    return cleanup_benchmark_sandboxes(
        uuid.UUID(client.user_id),
        benchmark_run_id=benchmark_run_id,
        include_legacy_prefix=benchmark_run_id is None,
        dry_run=dry_run,
    )


def prepare_bench_sandbox_cleanup(
    client: E2EClient,
    *,
    bench_prefix: str = BENCH_RESOURCE_PREFIX,
    min_free: int = 1,
    dry_run: bool = False,
    extra_deleted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del bench_prefix  # legacy arg
    from apps.backend.infrastructure.benchmark_resource_service import (
        prepare_benchmark_sandbox_cleanup,
    )

    return prepare_benchmark_sandbox_cleanup(
        uuid.UUID(client.user_id),
        min_free=min_free,
        dry_run=dry_run,
        include_legacy_prefix=True,
        extra_deleted=extra_deleted,
    )


def prepare_bench_workspace_quota(
    client: E2EClient,
    *,
    bench_prefix: str = BENCH_RESOURCE_PREFIX,
    min_free: int = 1,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backward-compatible alias — cleans workspaces, dashboards, and conversations."""
    return prepare_bench_sandbox_cleanup(
        client,
        bench_prefix=bench_prefix,
        min_free=min_free,
        dry_run=dry_run,
    )
