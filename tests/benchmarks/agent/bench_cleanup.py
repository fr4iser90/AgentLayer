"""Delete benchmark sandbox resources (workspaces, dashboards) by name prefix."""

from __future__ import annotations

import os
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
    workspaces = list_user_workspaces(client)
    bench_count = sum(1 for ws in workspaces if matches_bench_prefix(str(ws.get("name") or ""), bench_prefix))
    total = len(workspaces)
    return {
        "workspace_count": total,
        "bench_workspace_count": bench_count,
        "non_bench_workspace_count": max(0, total - bench_count),
    }


def _delete_resource(
    client: E2EClient,
    method: str,
    path: str,
    *,
    dry_run: bool,
    label: str,
) -> bool:
    if dry_run:
        return True
    resp = client.http.request(method, path)
    return resp.status_code in (200, 204, 404)


def cleanup_prefix(
    client: E2EClient,
    *,
    prefix: str,
    dry_run: bool = False,
    include_conversations: bool = False,
) -> dict[str, int]:
    """Delete workspaces/dashboards (and optionally conversations) whose name/title starts with prefix."""
    stats = {"workspaces": 0, "dashboards": 0, "conversations": 0}
    prefix = (prefix or BENCH_RESOURCE_PREFIX).strip()
    if not prefix:
        return stats

    for ws in list_user_workspaces(client):
        name = str(ws.get("name") or "")
        wid = str(ws.get("id") or "")
        if not matches_bench_prefix(name, prefix):
            continue
        if _delete_resource(
            client,
            "DELETE",
            f"/v1/workspaces/{wid}",
            dry_run=dry_run,
            label=f"workspace {name!r}",
        ):
            stats["workspaces"] += 1

    dash_data = client.get_json("/v1/dashboards")
    for dash in dash_data.get("dashboards") or []:
        if not isinstance(dash, dict):
            continue
        title = str(dash.get("title") or dash.get("name") or "")
        did = str(dash.get("id") or "")
        if not matches_bench_prefix(title, prefix):
            continue
        if _delete_resource(
            client,
            "DELETE",
            f"/v1/dashboards/{did}",
            dry_run=dry_run,
            label=f"dashboard {title!r}",
        ):
            stats["dashboards"] += 1

    if include_conversations:
        conv_data = client.get_json("/v1/user/conversations")
        rows: list[Any] = conv_data.get("conversations") or conv_data.get("items") or []
        for conv in rows:
            if not isinstance(conv, dict):
                continue
            title = str(conv.get("title") or "")
            cid = str(conv.get("id") or "")
            if not matches_bench_prefix(title, prefix):
                continue
            if _delete_resource(
                client,
                "DELETE",
                f"/v1/user/conversations/{cid}",
                dry_run=dry_run,
                label=f"conversation {title!r}",
            ):
                stats["conversations"] += 1

    return stats


def prepare_bench_workspace_quota(
    client: E2EClient,
    *,
    bench_prefix: str = BENCH_RESOURCE_PREFIX,
    min_free: int = 1,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Remove stale bench-* sandboxes, then report whether the user has room for workspace.create scenarios.

    Only deletes resources whose names start with ``bench_prefix`` — never touches AgentLayer-* or other
    production workspaces.
    """
    before = workspace_quota_snapshot(client, bench_prefix=bench_prefix)
    deleted = cleanup_prefix(client, prefix=bench_prefix, dry_run=dry_run)
    after = workspace_quota_snapshot(client, bench_prefix=bench_prefix)
    workspace_quota = int(os.environ.get("AGENT_BENCH_WORKSPACE_QUOTA", "10") or "10")
    workspace_headroom = max(0, workspace_quota - after["workspace_count"])
    has_headroom = workspace_headroom >= min_free

    return {
        "before": before,
        "after": after,
        "deleted": deleted,
        "workspace_quota": workspace_quota,
        "workspace_headroom": workspace_headroom,
        "has_workspace_headroom": has_headroom,
        "dry_run": dry_run,
    }
