"""Benchmark sandbox resources — DB markers, quota, cleanup (not name-prefix only)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

BENCH_LEGACY_NAME_PREFIX = "bench-"
BENCH_LEGACY_CONVERSATION_PREFIX = "bench "


def _default_benchmark_workspace_quota() -> int:
    raw = (os.environ.get("AGENT_BENCH_WORKSPACE_QUOTA") or "10").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 10


def user_benchmark_workspace_quota(user_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(benchmark_workspace_quota, 10) FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    if row and row[0] is not None:
        return max(1, int(row[0]))
    return _default_benchmark_workspace_quota()


def _bench_match_sql(
    column: str,
    *,
    legacy: bool,
    legacy_pattern: str,
) -> tuple[str, list[Any]]:
    if legacy:
        return f"(benchmark_run_id IS NOT NULL OR {column} LIKE %s)", [legacy_pattern]
    return "benchmark_run_id IS NOT NULL", []


def _count_user_bench_rows(
    user_id: uuid.UUID,
    *,
    table: str,
    user_column: str,
    label_column: str,
    tenant_id: int | None = None,
    legacy_pattern: str,
    include_legacy_prefix: bool,
) -> tuple[int, int]:
    bench_sql, bench_params = _bench_match_sql(
        label_column,
        legacy=include_legacy_prefix,
        legacy_pattern=legacy_pattern,
    )
    tenant_sql = ""
    where_params: list[Any] = [user_id]
    if tenant_id is not None:
        tenant_sql = " AND tenant_id = %s"
        where_params.append(tenant_id)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE {bench_sql})
                FROM {table}
                WHERE {user_column} = %s{tenant_sql}
                """,
                tuple(bench_params + where_params),
            )
            row = cur.fetchone()
    total = int(row[0] or 0) if row else 0
    bench = int(row[1] or 0) if row else 0
    return total, bench


def benchmark_sandbox_snapshot(
    user_id: uuid.UUID,
    *,
    include_legacy_prefix: bool = True,
) -> dict[str, int | bool]:
    """Workspaces, dashboards, and conversations — bench-tagged and legacy bench-* / bench title."""
    tenant_id = db.user_tenant_id(user_id)
    ws = workspace_quota_snapshot(user_id, include_legacy_prefix=include_legacy_prefix)
    dash_total, dash_bench = _count_user_bench_rows(
        user_id,
        table="user_dashboards",
        user_column="owner_user_id",
        label_column="title",
        tenant_id=tenant_id,
        legacy_pattern=f"{BENCH_LEGACY_NAME_PREFIX}%",
        include_legacy_prefix=include_legacy_prefix,
    )
    conv_total, conv_bench = _count_user_bench_rows(
        user_id,
        table="chat_conversations",
        user_column="user_id",
        label_column="title",
        legacy_pattern=f"{BENCH_LEGACY_CONVERSATION_PREFIX}%",
        include_legacy_prefix=include_legacy_prefix,
    )
    return {
        **ws,
        "dashboard_count": dash_total,
        "bench_dashboard_count": dash_bench,
        "non_bench_dashboard_count": max(0, dash_total - dash_bench),
        "conversation_count": conv_total,
        "bench_conversation_count": conv_bench,
        "non_bench_conversation_count": max(0, conv_total - conv_bench),
        "has_bench_sandbox_resources": (
            int(ws.get("bench_workspace_count") or 0) > 0
            or dash_bench > 0
            or conv_bench > 0
        ),
    }


def workspace_quota_snapshot(
    user_id: uuid.UUID,
    *,
    include_legacy_prefix: bool = True,
) -> dict[str, int]:
    bench_sql, bench_params = _bench_match_sql(
        "name",
        legacy=include_legacy_prefix,
        legacy_pattern=f"{BENCH_LEGACY_NAME_PREFIX}%",
    )
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE {bench_sql})
                FROM project_workspaces
                WHERE owner_user_id = %s
                """,
                tuple(bench_params + [user_id]),
            )
            row = cur.fetchone()
            cur.execute(
                "SELECT COALESCE(workspace_quota, 10) FROM users WHERE id = %s",
                (user_id,),
            )
            quota_row = cur.fetchone()
    total = int(row[0] or 0) if row else 0
    bench = int(row[1] or 0) if row else 0
    user_quota = int(quota_row[0] or 10) if quota_row else 10
    bench_quota = user_benchmark_workspace_quota(user_id)
    non_bench = max(0, total - bench)
    user_headroom = max(0, user_quota - non_bench)
    bench_headroom = max(0, bench_quota - bench)
    return {
        "workspace_count": total,
        "bench_workspace_count": bench,
        "non_bench_workspace_count": non_bench,
        "workspace_quota": user_quota,
        "benchmark_workspace_quota": bench_quota,
        "workspace_headroom": user_headroom,
        "benchmark_workspace_headroom": bench_headroom,
        "has_workspace_headroom": user_headroom > 0,
        "has_benchmark_workspace_headroom": bench_headroom > 0,
    }


def tag_dashboard_benchmark_run(
    dashboard_id: uuid.UUID | str,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    benchmark_run_id: uuid.UUID,
) -> None:
    did = uuid.UUID(str(dashboard_id))
    rid = uuid.UUID(str(benchmark_run_id))
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_dashboards
                SET benchmark_run_id = %s, updated_at = now()
                WHERE id = %s AND owner_user_id = %s AND tenant_id = %s AND benchmark_run_id IS NULL
                """,
                (rid, did, owner_user_id, tenant_id),
            )
        conn.commit()


def tag_workspace_benchmark_run(
    workspace_id: uuid.UUID | str,
    owner_user_id: uuid.UUID,
    benchmark_run_id: uuid.UUID,
) -> None:
    wid = uuid.UUID(str(workspace_id))
    rid = uuid.UUID(str(benchmark_run_id))
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE project_workspaces
                SET benchmark_run_id = %s, updated_at = now()
                WHERE id = %s AND owner_user_id = %s AND benchmark_run_id IS NULL
                """,
                (rid, wid, owner_user_id),
            )
        conn.commit()


def cleanup_benchmark_sandboxes(
    user_id: uuid.UUID,
    *,
    benchmark_run_id: uuid.UUID | None = None,
    include_legacy_prefix: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete benchmark-tagged (or legacy bench-* / bench title) resources for a user."""
    from apps.backend.dashboard import db as dashboard_db
    from apps.backend.infrastructure import agent_runs_store, notifications_store
    from apps.backend.infrastructure.conversations_db import conversation_delete
    from apps.backend.infrastructure.workspace_service import delete_owned_workspace

    stats: dict[str, Any] = {
        "workspaces": 0,
        "dashboards": 0,
        "conversations": 0,
        "notifications": 0,
        "errors": [],
    }
    busy_workspace_ids = agent_runs_store.running_workspace_ids_for_user(user_id)
    errors: list[str] = stats["errors"]
    tenant_id = db.user_tenant_id(user_id)
    legacy = include_legacy_prefix and benchmark_run_id is None

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            if benchmark_run_id is not None:
                cur.execute(
                    """
                    SELECT id, name FROM project_workspaces
                    WHERE owner_user_id = %s AND benchmark_run_id = %s
                    """,
                    (user_id, benchmark_run_id),
                )
            else:
                bench_sql, bench_params = _bench_match_sql(
                    "name",
                    legacy=legacy,
                    legacy_pattern=f"{BENCH_LEGACY_NAME_PREFIX}%",
                )
                cur.execute(
                    f"""
                    SELECT id, name FROM project_workspaces
                    WHERE owner_user_id = %s AND {bench_sql}
                    """,
                    tuple([user_id] + bench_params),
                )
            workspace_rows = cur.fetchall()

            if benchmark_run_id is not None:
                cur.execute(
                    """
                    SELECT id, title FROM user_dashboards
                    WHERE owner_user_id = %s AND tenant_id = %s AND benchmark_run_id = %s
                    """,
                    (user_id, tenant_id, benchmark_run_id),
                )
            else:
                bench_sql, bench_params = _bench_match_sql(
                    "title",
                    legacy=legacy,
                    legacy_pattern=f"{BENCH_LEGACY_NAME_PREFIX}%",
                )
                cur.execute(
                    f"""
                    SELECT id, title FROM user_dashboards
                    WHERE owner_user_id = %s AND tenant_id = %s AND {bench_sql}
                    """,
                    tuple([user_id, tenant_id] + bench_params),
                )
            dashboard_rows = cur.fetchall()

            if benchmark_run_id is not None:
                cur.execute(
                    """
                    SELECT id, title FROM chat_conversations
                    WHERE user_id = %s AND benchmark_run_id = %s
                    """,
                    (user_id, benchmark_run_id),
                )
            else:
                bench_sql, bench_params = _bench_match_sql(
                    "title",
                    legacy=legacy,
                    legacy_pattern=f"{BENCH_LEGACY_CONVERSATION_PREFIX}%",
                )
                cur.execute(
                    f"""
                    SELECT id, title FROM chat_conversations
                    WHERE user_id = %s AND {bench_sql}
                    """,
                    tuple([user_id] + bench_params),
                )
            conversation_rows = cur.fetchall()

    for row in workspace_rows:
        wid = str(row[0])
        name = str(row[1] or "")
        if dry_run:
            stats["workspaces"] += 1
            continue
        try:
            wid_uuid = uuid.UUID(wid)
        except (ValueError, TypeError):
            wid_uuid = None
        if wid_uuid is not None and wid_uuid in busy_workspace_ids:
            errors.append(f"workspace {name!r}: active agent run — skipped")
            continue
        try:
            if delete_owned_workspace(workspace_id=wid, owner_user_id=user_id):
                stats["workspaces"] += 1
            else:
                errors.append(f"workspace {name!r}: not deleted")
        except Exception as exc:
            errors.append(f"workspace {name!r}: {exc}")

    for row in dashboard_rows:
        did = uuid.UUID(str(row[0]))
        title = str(row[1] or "")
        if dry_run:
            stats["dashboards"] += 1
            continue
        try:
            if dashboard_db.dashboard_delete(user_id, tenant_id, did):
                stats["dashboards"] += 1
            else:
                errors.append(f"dashboard {title!r}: not deleted")
        except Exception as exc:
            errors.append(f"dashboard {title!r}: {exc}")

    for row in conversation_rows:
        cid = uuid.UUID(str(row[0]))
        title = str(row[1] or "")
        if dry_run:
            stats["conversations"] += 1
            continue
        try:
            if conversation_delete(user_id, cid):
                stats["conversations"] += 1
            else:
                errors.append(f"conversation {title!r}: not deleted")
        except Exception as exc:
            errors.append(f"conversation {title!r}: {exc}")

    if not dry_run:
        dash_ids: list[uuid.UUID] = []
        for row in dashboard_rows:
            try:
                dash_ids.append(uuid.UUID(str(row[0])))
            except (ValueError, TypeError):
                continue
        try:
            stats["notifications"] = notifications_store.delete_benchmark_notifications(
                user_id,
                dashboard_ids=dash_ids or None,
                benchmark_run_id=benchmark_run_id,
                include_legacy_prefix=include_legacy_prefix,
            )
        except Exception as exc:
            errors.append(f"notifications: {exc}")

    if not errors:
        del stats["errors"]
    return stats


def _merge_deleted_stats(*parts: dict[str, Any] | None) -> dict[str, int]:
    out = {"workspaces": 0, "dashboards": 0, "conversations": 0, "notifications": 0}
    for part in parts:
        if not isinstance(part, dict):
            continue
        for key in out:
            out[key] += int(part.get(key) or 0)
    return out


def prepare_benchmark_sandbox_cleanup(
    user_id: uuid.UUID,
    *,
    min_free: int = 1,
    dry_run: bool = False,
    include_legacy_prefix: bool = True,
    extra_deleted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delete all benchmark sandboxes (workspaces, dashboards, conversations) and return quota snapshot."""
    before = benchmark_sandbox_snapshot(user_id, include_legacy_prefix=include_legacy_prefix)
    deleted = cleanup_benchmark_sandboxes(
        user_id,
        include_legacy_prefix=include_legacy_prefix,
        dry_run=dry_run,
    )
    after = benchmark_sandbox_snapshot(user_id, include_legacy_prefix=include_legacy_prefix)
    bench_headroom = int(after.get("benchmark_workspace_headroom") or 0)
    has_headroom = after.get("has_benchmark_workspace_headroom", False) and bench_headroom >= min_free
    merged_deleted = _merge_deleted_stats(deleted, extra_deleted)
    err_list = deleted.get("errors") if isinstance(deleted.get("errors"), list) else []
    out: dict[str, Any] = {
        "before": before,
        "after": after,
        "deleted": merged_deleted,
        "workspace_quota": after.get("workspace_quota"),
        "benchmark_workspace_quota": after.get("benchmark_workspace_quota"),
        "workspace_headroom": after.get("workspace_headroom"),
        "benchmark_workspace_headroom": after.get("benchmark_workspace_headroom"),
        "has_workspace_headroom": has_headroom,
        "dry_run": dry_run,
    }
    if err_list:
        out["errors"] = [str(e) for e in err_list[:32]]
    return out


def prepare_benchmark_workspace_quota(
    user_id: uuid.UUID,
    *,
    min_free: int = 1,
    dry_run: bool = False,
    include_legacy_prefix: bool = True,
) -> dict[str, Any]:
    """Backward-compatible alias — cleans workspaces, dashboards, and conversations."""
    return prepare_benchmark_sandbox_cleanup(
        user_id,
        min_free=min_free,
        dry_run=dry_run,
        include_legacy_prefix=include_legacy_prefix,
    )
