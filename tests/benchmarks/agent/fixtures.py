"""Benchmark fixture setup — infra only (secrets, friends, platform gates). Agent does product work via tools."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from tests.e2e.support.helpers import (
    AGENTLAYER_SELF_NAME,
    E2EClient,
    ensure_user_b,
    find_workspace_by_name,
    operator_self_editing_enabled,
)

FixtureFn = Callable[[E2EClient, "FixtureContext"], None]


@dataclass
class FixtureContext:
    run_id: str
    prefix: str
    workspace_id: str | None = None
    workspace_name: str | None = None
    indexed: bool = False
    user_b_id: str | None = None
    user_b_email: str | None = None
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
    """Only agentlayer-self is pre-bound; other workspaces are created by the agent."""
    if "agentlayer_self" in requires:
        return ctx.workspace_id
    return None


# fixture_id -> depends on other fixture ids
FIXTURE_REQUIRES: dict[str, tuple[str, ...]] = {
    "agentlayer_self": (),
    "friend_pair": (),
    "gmail_secret": (),
    "ssc_secret": (),
}

# optional fixtures: skip scenario instead of failing the whole run
OPTIONAL_FIXTURES: frozenset[str] = frozenset({"gmail_secret", "ssc_secret"})


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
    file_path: str | None = None,
) -> dict[str, Any]:
    url = f"/v1/workspaces/{workspace_id}/git/changes"
    if file_path:
        resp = client.http.get(url, params={"path": file_path})
        resp.raise_for_status()
        data = resp.json()
        assert isinstance(data, dict)
        return data
    return client.get_json(url)


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
        ctx.workspace_id = str(ws.get("id") or "") or None
        ctx.workspace_name = ws_name

    if client.role == "admin" and not operator_self_editing_enabled(client):
        raise RuntimeError(
            "agentlayer_self requires workspace_allow_self_editing for the benchmark run "
            "(harness enables it when this fixture is requested)"
        )
    _resolve()


def _setup_friend_pair(client: E2EClient, ctx: FixtureContext) -> None:
    admin = _bench_admin_client(client)
    friend_id = (os.environ.get("AGENT_BENCH_FRIEND_USER_ID") or "").strip()
    if friend_id:
        user_b = E2EClient.for_user_id(uuid.UUID(friend_id))
    else:
        user_b = ensure_user_b(admin)
    _ensure_friends(admin, user_b)
    ctx.user_b_id = user_b.user_id
    ctx.user_b_email = user_b.email
    if user_b.http is not client.http:
        user_b.close()


def _setup_gmail_secret(client: E2EClient, ctx: FixtureContext) -> None:
    service_key = (os.environ.get("AGENT_BENCH_GMAIL_SERVICE_KEY") or "gmail").strip().lower()
    if service_key in _list_user_secret_keys(client):
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
    "friend_pair": _setup_friend_pair,
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
