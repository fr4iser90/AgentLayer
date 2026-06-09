"""Benchmark fixture setup (composable test data / sandbox resources)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from tests.e2e.support.helpers import (
    AGENTLAYER_SELF_NAME,
    E2EClient,
    ensure_git_workspace,
    ensure_user_b,
    find_workspace_by_name,
    git_clone_url,
    operator_self_editing_enabled,
    wait_index_idle,
)

FixtureFn = Callable[[E2EClient, "FixtureContext"], None]


@dataclass
class FixtureContext:
    run_id: str
    prefix: str
    workspace_id: str | None = None
    workspace_name: str | None = None
    workspace_by_fixture: dict[str, str] = field(default_factory=dict)
    dashboard_by_fixture: dict[str, str] = field(default_factory=dict)
    indexed: bool = False
    user_b_id: str | None = None
    dashboard_id: str | None = None
    gmail_service_key: str | None = None
    git_remote_url: str | None = None
    applied: set[str] = field(default_factory=set)
    skipped: dict[str, str] = field(default_factory=dict)

    def is_available(self, fixture_id: str) -> bool:
        if fixture_id in self.skipped:
            return False
        return fixture_id in self.applied

    def skip_reason(self, fixture_id: str) -> str | None:
        return self.skipped.get(fixture_id)


def workspace_id_for_scenario(
    ctx: FixtureContext,
    requires: tuple[str, ...],
) -> str | None:
    """Pick workspace UUID when multiple fixture types ran in one benchmark."""
    if "workspace_agentlayer_git" in requires:
        wid = ctx.workspace_by_fixture.get("workspace_agentlayer_git")
        if wid:
            return wid
    if "workspace_git" in requires or "workspace_indexed" in requires:
        wid = ctx.workspace_by_fixture.get("workspace_git")
        if wid:
            return wid
    if "agentlayer_self" in requires:
        wid = ctx.workspace_by_fixture.get("agentlayer_self")
        if wid:
            return wid
    if requires and ctx.workspace_id:
        return ctx.workspace_id
    return None


def dashboard_id_for_scenario(
    ctx: FixtureContext,
    requires: tuple[str, ...],
    *,
    agent_id: str = "",
) -> str | None:
    if "dashboard_empty" in requires:
        did = ctx.dashboard_by_fixture.get("dashboard_empty")
        if did:
            return did
    if "dashboard_block_share" in requires:
        did = ctx.dashboard_by_fixture.get("dashboard_block_share")
        if did:
            return did
    if agent_id == "dashboard" and ctx.dashboard_id:
        return ctx.dashboard_id
    return None


# fixture_id -> depends on other fixture ids
FIXTURE_REQUIRES: dict[str, tuple[str, ...]] = {
    "agentlayer_self": (),
    "workspace_git": (),
    "workspace_agentlayer_git": (),
    "workspace_indexed": ("workspace_git",),
    "friend_pair": (),
    "dashboard_block_share": ("friend_pair",),
    "dashboard_empty": (),
    "gmail_secret": (),
    "ssc_secret": (),
}

# optional fixtures: skip scenario instead of failing the whole run
OPTIONAL_FIXTURES: frozenset[str] = frozenset(
    {"workspace_indexed", "gmail_secret", "ssc_secret"}
)


def agentlayer_bench_git_url() -> str:
    return (
        os.environ.get("AGENT_BENCH_AGENTLAYER_GIT_URL")
        or "https://github.com/fr4iser90/AgentLayer.git"
    ).strip()


def fetch_dashboard(client: E2EClient, dashboard_id: str) -> dict[str, Any]:
    payload = client.get_json(f"/v1/dashboards/{dashboard_id}")
    row = payload.get("dashboard") if isinstance(payload.get("dashboard"), dict) else payload
    return row if isinstance(row, dict) else {}


def find_dashboard_by_title(client: E2EClient, title: str) -> dict[str, Any] | None:
    payload = client.get_json("/v1/dashboards")
    rows = payload.get("dashboards") if isinstance(payload.get("dashboards"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("title") or "").strip() != title.strip():
            continue
        dash_id = str(row.get("id") or "").strip()
        if dash_id:
            return fetch_dashboard(client, dash_id)
    return None


def fetch_git_changes(
    client: E2EClient,
    workspace_id: str,
    *,
    path: str | None = None,
) -> dict[str, Any]:
    if path:
        return client.get_json(
            f"/v1/workspaces/{workspace_id}/git/changes",
            path=path,
        )
    return client.get_json(f"/v1/workspaces/{workspace_id}/git/changes")


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _incoming_pending(client: E2EClient) -> list[dict[str, Any]]:
    data = client.get_json("/v1/friends/requests/incoming")
    return [r for r in data.get("requests") or [] if isinstance(r, dict)]


def _list_user_secret_keys(client: E2EClient) -> set[str]:
    try:
        data = client.get_json("/v1/user/secrets")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            return set()
        raise
    services = data.get("services") if isinstance(data.get("services"), list) else []
    return {str(k).strip().lower() for k in services if str(k).strip()}


def _bench_admin_client(run_client: E2EClient) -> E2EClient:
    if run_client.role == "admin":
        return run_client
    admin_id = (os.environ.get("AGENT_BENCH_ADMIN_USER_ID") or "").strip()
    if admin_id:
        return E2EClient.for_user_id(uuid.UUID(admin_id))
    raise RuntimeError(
        "friend_pair requires admin run-as user or AGENT_BENCH_ADMIN_USER_ID for fixture setup"
    )


def _ensure_friends(admin_client: E2EClient, user_b: E2EClient) -> None:
    user_b_id = user_b.user_id
    friends = admin_client.get_json("/v1/friends").get("friends") or []
    if any(
        str(f.get("friend_user_id") or f.get("user_id") or "") == user_b_id
        for f in friends
        if isinstance(f, dict)
    ):
        return

    pending = _incoming_pending(user_b)
    if not pending:
        resp = admin_client.post_json_allow(
            "/v1/friends/request",
            {"email": user_b.email, "message": "Benchmark friend"},
            ok={200, 400},
        )
        if resp.status_code == 400 and "already friends" in resp.text.lower():
            return
        pending = _incoming_pending(user_b)

    if not pending:
        raise RuntimeError("User B has no incoming friend request after admin sent request")
    req_id = pending[0].get("id")
    assert req_id is not None
    user_b.post_json(f"/v1/friends/requests/{req_id}/accept", {})


def _setup_agentlayer_self(client: E2EClient, ctx: FixtureContext) -> None:
    ws_name = (
        os.environ.get("AGENT_BENCH_WORKSPACE_NAME") or AGENTLAYER_SELF_NAME
    ).strip()

    def _resolve() -> None:
        ws = find_workspace_by_name(client, ws_name)
        if not ws:
            raise RuntimeError(
                f"workspace {ws_name!r} not found — enable self-editing or set AGENT_BENCH_WORKSPACE_NAME"
            )
        ws_id = str(ws.get("id") or "") or None
        ctx.workspace_id = ws_id
        ctx.workspace_name = ws_name
        if ws_id:
            ctx.workspace_by_fixture["agentlayer_self"] = ws_id

    if client.role == "admin" and not operator_self_editing_enabled(client):
        raise RuntimeError(
            "agentlayer_self requires workspace_allow_self_editing for the benchmark run "
            "(harness enables it when this fixture is requested)"
        )
    _resolve()


def _setup_workspace_git(client: E2EClient, ctx: FixtureContext) -> None:
    ws_name = f"{ctx.prefix}git"
    git_url = (os.environ.get("AGENT_BENCH_GIT_URL") or git_clone_url()).strip()
    ws = ensure_git_workspace(client, name=ws_name, git_url=git_url)
    ws_id = str(ws.get("id") or "") or None
    ctx.workspace_id = ws_id
    ctx.workspace_name = ws_name
    ctx.git_remote_url = git_url
    ctx.indexed = False
    if ws_id:
        ctx.workspace_by_fixture["workspace_git"] = ws_id


def _setup_workspace_agentlayer_git(client: E2EClient, ctx: FixtureContext) -> None:
    ws_name = f"{ctx.prefix}agentlayer"
    git_url = agentlayer_bench_git_url()
    ws = ensure_git_workspace(client, name=ws_name, git_url=git_url)
    ws_id = str(ws.get("id") or "") or None
    ctx.workspace_id = ws_id
    ctx.workspace_name = ws_name
    ctx.git_remote_url = git_url
    ctx.indexed = False
    if ws_id:
        ctx.workspace_by_fixture["workspace_agentlayer_git"] = ws_id


def _setup_workspace_indexed(client: E2EClient, ctx: FixtureContext) -> None:
    """Run code index when ``workspace_indexed`` is in the benchmark fixture set (UI or CLI)."""
    if not ctx.workspace_id:
        ctx.skipped["workspace_indexed"] = "workspace_git not applied"
        return
    ws_id = ctx.workspace_id
    try:
        client.patch_json(
            f"/v1/workspaces/{ws_id}",
            {"semantic_index_enabled": True},
        )
    except httpx.HTTPError:
        pass
    kick = client.post_json(
        f"/v1/workspaces/{ws_id}/index",
        {"mode": "code", "max_files": 200},
    )
    if not kick.get("ok"):
        ctx.skipped["workspace_indexed"] = f"index kick failed: {kick}"
        return
    timeout_s = float(os.environ.get("AGENT_BENCH_INDEX_TIMEOUT_S") or "180")
    wait_index_idle(client, ws_id, timeout_s=timeout_s)
    ctx.indexed = True


def _setup_friend_pair(client: E2EClient, ctx: FixtureContext) -> None:
    admin = _bench_admin_client(client)
    friend_id = (os.environ.get("AGENT_BENCH_FRIEND_USER_ID") or "").strip()
    if friend_id:
        user_b = E2EClient.for_user_id(uuid.UUID(friend_id))
    else:
        user_b = ensure_user_b(admin)
    _ensure_friends(admin, user_b)
    ctx.user_b_id = user_b.user_id
    if user_b.http is not client.http:
        user_b.close()


def _setup_dashboard_block_share(client: E2EClient, ctx: FixtureContext) -> None:
    if not ctx.user_b_id:
        raise RuntimeError("dashboard_block_share requires friend_pair")
    title = f"{ctx.prefix}share"
    created = client.post_json(
        "/v1/dashboards",
        {
            "kind": "custom",
            "title": title,
            "data": {"shared_notes": "bench-visible", "private_notes": "bench-hidden"},
            "ui_layout": {
                "version": 2,
                "blocks": [
                    {
                        "id": "bench-md-shared",
                        "type": "markdown",
                        "grid": {"x": 0, "y": 0, "w": 12, "h": 4},
                        "props": {"dataPath": "shared_notes"},
                    },
                    {
                        "id": "bench-md-private",
                        "type": "markdown",
                        "grid": {"x": 0, "y": 4, "w": 12, "h": 4},
                        "props": {"dataPath": "private_notes"},
                    },
                ],
            },
        },
    )
    dash = created.get("dashboard") or created
    dash_id = str(dash.get("id") or "")
    if not dash_id:
        raise RuntimeError(f"dashboard create failed: {created}")
    ctx.dashboard_id = dash_id
    ctx.dashboard_by_fixture["dashboard_block_share"] = dash_id
    client.post_json(
        f"/v1/dashboards/{dash_id}/block-shares",
        {
            "block_id": "bench-md-shared",
            "grantee_user_id": ctx.user_b_id,
            "permission": "view",
        },
    )


def _setup_gmail_secret(client: E2EClient, ctx: FixtureContext) -> None:
    service_key = (os.environ.get("AGENT_BENCH_GMAIL_SERVICE_KEY") or "gmail").strip().lower()
    if service_key in _list_user_secret_keys(client):
        ctx.gmail_service_key = service_key
        return
    raw = (os.environ.get("AGENT_BENCH_GMAIL_SECRET") or "").strip()
    if not raw:
        ctx.skipped["gmail_secret"] = (
            "Configure gmail secret for run user (Settings → Secrets) or set AGENT_BENCH_GMAIL_SECRET"
        )
        return
    try:
        client.post_json(
            "/v1/user/secrets",
            {"service_key": service_key, "secret": raw},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            ctx.skipped["gmail_secret"] = "SECRETS_MASTER_KEY not configured on server"
            return
        raise
    ctx.gmail_service_key = service_key


def _setup_dashboard_empty(client: E2EClient, ctx: FixtureContext) -> None:
    title = f"{ctx.prefix}layout"
    created = client.post_json(
        "/v1/dashboards",
        {
            "kind": "custom",
            "title": title,
            "data": {},
            "ui_layout": {"version": 2, "blocks": []},
        },
    )
    dash = created.get("dashboard") or created
    dash_id = str(dash.get("id") or "")
    if not dash_id:
        raise RuntimeError(f"dashboard create failed: {created}")
    ctx.dashboard_id = dash_id
    ctx.dashboard_by_fixture["dashboard_empty"] = dash_id


def _setup_ssc_secret(client: E2EClient, ctx: FixtureContext) -> None:
    service_key = "ssc_api_key"
    if service_key in _list_user_secret_keys(client):
        return
    raw = (os.environ.get("AGENT_BENCH_SSC_SECRET") or os.environ.get("SSC_API_KEY") or "").strip()
    if not raw:
        ctx.skipped["ssc_secret"] = (
            "Configure ssc_api_key for run user (Settings → Secrets) or set AGENT_BENCH_SSC_SECRET"
        )
        return
    try:
        client.post_json(
            "/v1/user/secrets",
            {"service_key": service_key, "secret": raw},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            ctx.skipped["ssc_secret"] = "SECRETS_MASTER_KEY not configured on server"
            return
        raise


FIXTURE_SETUP: dict[str, FixtureFn] = {
    "agentlayer_self": _setup_agentlayer_self,
    "workspace_git": _setup_workspace_git,
    "workspace_agentlayer_git": _setup_workspace_agentlayer_git,
    "workspace_indexed": _setup_workspace_indexed,
    "friend_pair": _setup_friend_pair,
    "dashboard_block_share": _setup_dashboard_block_share,
    "dashboard_empty": _setup_dashboard_empty,
    "gmail_secret": _setup_gmail_secret,
    "ssc_secret": _setup_ssc_secret,
}


def _topo_sort(fixture_ids: set[str]) -> list[str]:
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(fid: str) -> None:
        if fid in visited:
            return
        if fid in visiting:
            raise ValueError(f"fixture dependency cycle at {fid}")
        visiting.add(fid)
        for dep in FIXTURE_REQUIRES.get(fid, ()):
            if dep in fixture_ids or dep in FIXTURE_SETUP:
                visit(dep)
                if dep not in fixture_ids:
                    fixture_ids.add(dep)
        visiting.remove(fid)
        visited.add(fid)
        ordered.append(fid)

    for fid in sorted(fixture_ids):
        visit(fid)
    return ordered


def collect_fixture_ids(
    scenario_requires: list[tuple[str, ...]],
    manifest_fixtures: list[str] | None = None,
) -> set[str]:
    ids: set[str] = set(manifest_fixtures or [])
    for req_tuple in scenario_requires:
        ids.update(req_tuple)
    return ids


def apply_fixtures(
    client: E2EClient,
    ctx: FixtureContext,
    fixture_ids: set[str],
) -> None:
    for fid in _topo_sort(set(fixture_ids)):
        if fid in ctx.applied or fid in ctx.skipped:
            continue
        if fid not in FIXTURE_SETUP:
            raise ValueError(f"unknown fixture: {fid}")
        for dep in FIXTURE_REQUIRES.get(fid, ()):
            if dep in ctx.skipped and fid not in OPTIONAL_FIXTURES:
                ctx.skipped[fid] = f"dependency {dep} skipped: {ctx.skipped[dep]}"
                break
            if dep in ctx.skipped and fid in OPTIONAL_FIXTURES:
                ctx.skipped[fid] = f"dependency {dep} skipped: {ctx.skipped[dep]}"
                break
        if fid in ctx.skipped:
            continue
        FIXTURE_SETUP[fid](client, ctx)
        if fid not in ctx.skipped:
            ctx.applied.add(fid)


def scenario_fixture_blocked(ctx: FixtureContext, requires: tuple[str, ...]) -> str | None:
    for fid in requires:
        if fid in ctx.skipped:
            if fid in OPTIONAL_FIXTURES:
                return f"optional fixture {fid}: {ctx.skipped[fid]}"
            return f"required fixture {fid}: {ctx.skipped[fid]}"
        if fid not in ctx.applied:
            return f"fixture {fid} not applied"
    return None
