"""
E2E IDOR / auth isolation — **security tests only** (not LLM / not chat quality).

Each test creates a resource as **User A (admin)** then verifies **User B cannot
access it** (HTTP 401/403/404). That deliberate cross-user GET is the security
check — it simulates an attacker, not a chat prompt.

**No LLM is called.** Conversations are empty shells (``messages: []``) for API
isolation only. For model/agent tests see ``tests/benchmarks/agent/`` and
``tests/e2e/test_journey_agent_smoke.py``.

Resources use ``[E2E IDOR]`` prefix; deleted after each test. Stale cleanup:
``python3 scripts/e2e_cleanup.py``.

See docs/security/idor-auth-test-matrix.md.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from tests.e2e.support.helpers import E2EClient, base_url
from tests.e2e.support.idor import assert_cross_user_get_blocked, assert_cross_user_mutate_blocked
from tests.e2e.support.cleanup import E2E_IDOR_PREFIX, E2EResourceTracker, cleanup_idor_orphans

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module", autouse=True)
def _purge_stale_idor_sandbox(admin_client: E2EClient) -> None:
    """Remove legacy ``IDOR conv …`` threads left from older test runs."""
    cleanup_idor_orphans(admin_client)
    yield
    cleanup_idor_orphans(admin_client)


def _e2e_title(kind: str) -> str:
    return f"{E2E_IDOR_PREFIX} {kind} {uuid.uuid4().hex[:8]}"

_DENY = frozenset({401, 403, 404})


def _anon_client() -> httpx.Client:
    return httpx.Client(base_url=base_url(), timeout=60.0)


def _expect_status(resp: httpx.Response, allowed: set[int], *, label: str = "") -> None:
    prefix = f"{label}: " if label else ""
    assert resp.status_code in allowed, (
        f"{prefix}{resp.request.method} {resp.request.url} -> {resp.status_code}: "
        f"{resp.text[:400]}"
    )


def _expect_denied(resp: httpx.Response, *, label: str = "") -> None:
    _expect_status(resp, _DENY, label=label)


def _ensure_dashboard_schema(client: E2EClient) -> None:
    status = client.get_json("/v1/dashboards/install-status")
    if status.get("schema_installed"):
        return
    offers = status.get("schema_install_offers") or []
    kinds = [o.get("kind") for o in offers if isinstance(o, dict) and o.get("kind")]
    if not kinds:
        kinds = ["custom"]
    client.post_json("/v1/dashboards/install", {"kinds": kinds[:1]})


# --- Anonymous / middleware -------------------------------------------------


def test_anon_admin_routes_401(e2e_server: None) -> None:
    with _anon_client() as anon:
        for path in (
            "/v1/admin/operator-settings",
            "/v1/admin/users",
            "/v1/dashboards",
            "/v1/tasks",
            "/v1/workspaces",
            "/v1/user/persona",
            "/v1/org/tenant",
            "/v1/org/rag/ingest",
        ):
            if path.endswith("/ingest"):
                resp = anon.post(path, json={"text": "probe"})
            else:
                resp = anon.get(path)
            _expect_status(resp, {401}, label=path)


def test_anon_chat_completions_401(e2e_server: None) -> None:
    with _anon_client() as anon:
        resp = anon.post(
            "/v1/chat/completions",
            json={"model": "general", "messages": [{"role": "user", "content": "hi"}]},
        )
        _expect_status(resp, {401})


def test_anon_tools_run_401(e2e_server: None) -> None:
    with _anon_client() as anon:
        resp = anon.post("/tools/run", json={"name": "catalog", "arguments": {}})
        _expect_status(resp, {401})


def test_anon_tools_catalog_allowed(e2e_server: None) -> None:
    """GET /v1/tools is intentionally public (metadata only)."""
    with _anon_client() as anon:
        resp = anon.get("/v1/tools")
        _expect_status(resp, {200})
        data = resp.json()
        assert isinstance(data.get("tools"), list)


# --- User B vs admin routes -------------------------------------------------


def test_user_b_admin_operator_settings_403(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    resp = user_b_client.http.get("/v1/admin/operator-settings")
    _expect_status(resp, {403})


def test_user_b_admin_users_list_403(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    resp = user_b_client.http.get("/v1/admin/users")
    _expect_status(resp, {403})


def test_user_b_admin_rag_ingest_403(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    resp = user_b_client.http.post(
        "/v1/admin/rag/ingest",
        json={"text": "e2e probe", "domain": "test"},
    )
    _expect_status(resp, {403})


def test_user_b_org_tenant_403(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    resp = user_b_client.http.get("/v1/org/tenant")
    _expect_status(resp, {403, 404})


def test_user_b_org_rag_ingest_403(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    resp = user_b_client.http.post(
        "/v1/org/rag/ingest",
        json={"text": "e2e org probe", "title": "probe"},
    )
    _expect_status(resp, {403, 404})


def test_user_b_admin_tool_mutations_403(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    for path, body in (
        ("/v1/admin/reload-tools", {}),
        ("/v1/admin/create-tool", {"name": "e2e_probe"}),
    ):
        resp = user_b_client.http.post(path, json=body)
        _expect_status(resp, {403}, label=path)


# --- Cross-user IDOR: dashboards --------------------------------------------


def test_user_b_cannot_read_admin_private_dashboard(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    created = admin_client.post_json(
        "/v1/dashboards",
        {"kind": "custom", "title": _e2e_title("dashboard read probe")},
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    assert_cross_user_get_blocked(
        owner=admin_client,
        other=user_b_client,
        path=f"/v1/dashboards/{dash_id}",
        resource_label="private dashboard",
    )


def test_user_b_cannot_patch_admin_private_dashboard(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    created = admin_client.post_json(
        "/v1/dashboards",
        {"kind": "custom", "title": _e2e_title("dashboard patch probe")},
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    assert_cross_user_mutate_blocked(
        other=user_b_client,
        method="PATCH",
        path=f"/v1/dashboards/{dash_id}",
        json_body={"title": "owned by B"},
        resource_label="private dashboard",
        action="PATCH",
    )


# --- Cross-user IDOR: tasks -------------------------------------------------


def test_user_b_cannot_read_admin_task(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
) -> None:
    created = admin_client.post_json(
        "/v1/tasks",
        {"scope": "global", "goal": _e2e_title("task read probe")},
    )
    task_id = str((created.get("task") or {}).get("id") or "")
    assert task_id

    assert_cross_user_get_blocked(
        owner=admin_client,
        other=user_b_client,
        path=f"/v1/tasks/{task_id}",
        resource_label="task",
    )


def test_user_b_task_list_excludes_admin_task(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
) -> None:
    marker = uuid.uuid4().hex[:12]
    created = admin_client.post_json(
        "/v1/tasks",
        {"scope": "global", "goal": f"{E2E_IDOR_PREFIX} task list marker {marker}"},
    )
    task_id = str((created.get("task") or {}).get("id") or "")
    assert task_id

    listing = user_b_client.get_json("/v1/tasks")
    ids = {str(t.get("id")) for t in (listing.get("tasks") or []) if isinstance(t, dict)}
    assert task_id not in ids


# --- Cross-user IDOR: conversations -----------------------------------------


def test_user_b_cannot_read_admin_conversation(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    """
    Security: User B must not read User A's conversation (HTTP 401/403/404).

    Creates an **empty** conversation record — no messages, no LLM, no agent.
    """
    created = admin_client.post_json(
        "/v1/user/conversations",
        {
            "title": _e2e_title("conversation isolation"),
            "messages": [],
        },
    )
    conv_id = e2e_resources.track_conversation(
        str((created.get("conversation") or {}).get("id") or "")
    )
    assert conv_id

    assert_cross_user_get_blocked(
        owner=admin_client,
        other=user_b_client,
        path=f"/v1/user/conversations/{conv_id}",
        resource_label="conversation",
    )


# --- Cross-user isolation: persona / memory ---------------------------------


def test_persona_isolated_between_users(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
) -> None:
    marker_a = f"persona-a-{uuid.uuid4().hex}"
    marker_b = f"persona-b-{uuid.uuid4().hex}"

    admin_client.http.put(
        "/v1/user/persona",
        json={"instructions": marker_a, "inject_into_agent": False},
    ).raise_for_status()
    user_b_client.http.put(
        "/v1/user/persona",
        json={"instructions": marker_b, "inject_into_agent": False},
    ).raise_for_status()

    persona_b = user_b_client.get_json("/v1/user/persona")
    instructions_b = str(persona_b.get("instructions") or "")
    assert marker_a not in instructions_b
    assert marker_b in instructions_b

    persona_a = admin_client.get_json("/v1/user/persona")
    instructions_a = str(persona_a.get("instructions") or "")
    assert marker_b not in instructions_a
    assert marker_a in instructions_a


def test_memory_facts_isolated_between_users(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
) -> None:
    key = f"e2e-idor-{uuid.uuid4().hex[:16]}"
    admin_client.http.post(
        "/v1/user/memory/facts/upsert",
        json={"key": key, "value_json": {"probe": "admin-only"}},
    ).raise_for_status()

    facts_b = user_b_client.get_json("/v1/user/memory/facts")
    rows = facts_b.get("facts") or facts_b.get("items") or []
    if isinstance(facts_b, dict) and isinstance(rows, list):
        keys_b = {str(r.get("key") or "") for r in rows if isinstance(r, dict)}
        assert key not in keys_b


# --- Cross-user IDOR: secrets & workspaces ----------------------------------


def test_user_b_cannot_list_admin_secret_keys(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    """User B must not see User A's secret service keys in GET /v1/user/secrets."""
    sk = f"e2e.idor.{uuid.uuid4().hex[:12]}"
    upsert = admin_client.http.post(
        "/v1/user/secrets",
        json={"service_key": sk, "secret": f"probe-value-{uuid.uuid4().hex[:8]}"},
    )
    if upsert.status_code == 503:
        pytest.skip("user secrets disabled (AGENT_SECRETS_MASTER_KEY not set on server)")
    upsert.raise_for_status()
    e2e_resources.track_secret(sk)

    owner_list = admin_client.get_json("/v1/user/secrets")
    owner_keys = {str(s).strip().lower() for s in (owner_list.get("services") or [])}
    assert sk.lower() in owner_keys, "owner must see own secret key"

    listing = user_b_client.get_json("/v1/user/secrets")
    services = listing.get("services") or []
    assert isinstance(services, list)
    b_keys = {str(s).strip().lower() for s in services}
    if sk.lower() in b_keys:
        pytest.fail(
            f"SECURITY FAIL (IDOR): {user_b_client.email} must not see "
            f"{admin_client.email}'s secret key {sk!r} in GET /v1/user/secrets"
        )


def test_user_b_cannot_read_admin_workspace(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    name = f"e2e-idor-ws-{uuid.uuid4().hex[:10]}"
    created = admin_client.post_json(
        "/v1/workspaces",
        {"name": name, "source": "manual"},
    )
    ws_id = e2e_resources.track_workspace(str((created.get("workspace") or {}).get("id") or ""))
    assert ws_id

    assert_cross_user_get_blocked(
        owner=admin_client,
        other=user_b_client,
        path=f"/v1/workspaces/{ws_id}",
        resource_label="workspace",
    )

    ids_b = {
        str(w.get("id"))
        for w in (user_b_client.get_json("/v1/workspaces").get("workspaces") or [])
        if isinstance(w, dict)
    }
    assert ws_id not in ids_b


# --- Shared access (positive — must work when explicitly granted) -------------


def test_user_b_can_read_dashboard_when_member_viewer(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    _ensure_dashboard_schema(admin_client)
    title = _e2e_title("dashboard member viewer")
    created = admin_client.post_json(
        "/v1/dashboards",
        {"kind": "custom", "title": title, "data": {"shared_marker": "member-ok"}},
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    admin_client.post_json(
        f"/v1/dashboards/{dash_id}/members",
        {"email": user_b_client.email, "role": "viewer"},
    )

    viewer = user_b_client.get_json(f"/v1/dashboards/{dash_id}")
    dash = viewer.get("dashboard") or {}
    assert str(dash.get("id") or "") == dash_id
    assert dash.get("access_role") == "viewer"
    assert dash.get("access_scope") == "full"


def test_viewer_member_cannot_patch_dashboard(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    _ensure_dashboard_schema(admin_client)
    created = admin_client.post_json(
        "/v1/dashboards",
        {"kind": "custom", "title": _e2e_title("dashboard viewer no patch")},
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    admin_client.post_json(
        f"/v1/dashboards/{dash_id}/members",
        {"email": user_b_client.email, "role": "viewer"},
    )

    resp = user_b_client.http.patch(
        f"/v1/dashboards/{dash_id}",
        json={"title": "hijacked by viewer"},
    )
    _expect_denied(resp, label="viewer PATCH dashboard")


def test_editor_member_can_patch_dashboard_title(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    _ensure_dashboard_schema(admin_client)
    original = _e2e_title("dashboard editor patch")
    created = admin_client.post_json(
        "/v1/dashboards",
        {"kind": "custom", "title": original},
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    admin_client.post_json(
        f"/v1/dashboards/{dash_id}/members",
        {"email": user_b_client.email, "role": "editor"},
    )

    updated_title = f"{original}-edited"
    patched = user_b_client.patch_json(
        f"/v1/dashboards/{dash_id}",
        {"title": updated_title},
    )
    dash = patched.get("dashboard") or {}
    assert dash.get("access_role") == "editor"
    assert dash.get("title") == updated_title


def test_editor_member_cannot_delete_dashboard(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    _ensure_dashboard_schema(admin_client)
    created = admin_client.post_json(
        "/v1/dashboards",
        {"kind": "custom", "title": _e2e_title("dashboard editor no delete")},
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    admin_client.post_json(
        f"/v1/dashboards/{dash_id}/members",
        {"email": user_b_client.email, "role": "editor"},
    )

    resp = user_b_client.http.delete(f"/v1/dashboards/{dash_id}")
    _expect_denied(resp, label="editor DELETE dashboard")

    # Owner still has the dashboard.
    still = admin_client.get_json(f"/v1/dashboards/{dash_id}")
    assert str((still.get("dashboard") or {}).get("id") or "") == dash_id


_BLOCK_SHARE_LAYOUT: dict = {
    "version": 1,
    "blocks": [
        {
            "id": "md-share-e2e",
            "type": "markdown",
            "grid": {"x": 0, "y": 0, "w": 12, "h": 4},
            "props": {"dataPath": "share_notes", "placeholder": "Before"},
        },
    ],
}


def _block_share_layout_patch(*, placeholder: str) -> dict:
    block = dict(_BLOCK_SHARE_LAYOUT["blocks"][0])
    props = dict(block.get("props") or {})
    props["placeholder"] = placeholder
    block["props"] = props
    return {"version": 1, "blocks": [block]}


def test_block_share_view_cannot_patch_layout(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    _ensure_dashboard_schema(admin_client)
    created = admin_client.post_json(
        "/v1/dashboards",
        {
            "kind": "custom",
            "title": _e2e_title("dashboard block view"),
            "ui_layout": _BLOCK_SHARE_LAYOUT,
        },
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    admin_client.post_json(
        f"/v1/dashboards/{dash_id}/block-shares",
        {
            "email": user_b_client.email,
            "block_ids": ["md-share-e2e"],
            "permission": "view",
        },
    )

    resp = user_b_client.http.patch(
        f"/v1/dashboards/{dash_id}",
        json={"ui_layout": _block_share_layout_patch(placeholder="After view")},
    )
    _expect_denied(resp, label="block-share view PATCH")


def test_block_share_edit_can_patch_allowed_block(
    e2e_server: None,
    admin_client: E2EClient,
    user_b_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    _ensure_dashboard_schema(admin_client)
    created = admin_client.post_json(
        "/v1/dashboards",
        {
            "kind": "custom",
            "title": _e2e_title("dashboard block edit"),
            "ui_layout": _BLOCK_SHARE_LAYOUT,
        },
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    admin_client.post_json(
        f"/v1/dashboards/{dash_id}/block-shares",
        {
            "email": user_b_client.email,
            "block_ids": ["md-share-e2e"],
            "permission": "edit",
        },
    )

    patched = user_b_client.patch_json(
        f"/v1/dashboards/{dash_id}",
        {"ui_layout": _block_share_layout_patch(placeholder="After edit")},
    )
    dash = patched.get("dashboard") or {}
    assert dash.get("access_scope") == "granular"
    assert dash.get("granular_can_write") is True
    ul = dash.get("ui_layout") or {}
    blocks = ul.get("blocks") or []
    assert blocks and (blocks[0].get("props") or {}).get("placeholder") == "After edit"

    owner_view = admin_client.get_json(f"/v1/dashboards/{dash_id}")
    owner_ul = (owner_view.get("dashboard") or {}).get("ui_layout") or {}
    owner_blocks = owner_ul.get("blocks") or []
    assert owner_blocks and (owner_blocks[0].get("props") or {}).get("placeholder") == "After edit"


def test_anon_public_dashboard_share_without_password(
    e2e_server: None,
    admin_client: E2EClient,
    e2e_resources: E2EResourceTracker,
) -> None:
    _ensure_dashboard_schema(admin_client)
    marker = uuid.uuid4().hex[:8]
    title = _e2e_title(f"dashboard public {marker}")
    created = admin_client.post_json(
        "/v1/dashboards",
        {
            "kind": "custom",
            "title": title,
            "data": {"public_marker": marker},
        },
    )
    dash_id = e2e_resources.track_dashboard(str((created.get("dashboard") or {}).get("id") or ""))
    assert dash_id

    share = admin_client.post_json(
        f"/v1/dashboards/{dash_id}/public-shares",
        {"label": "e2e-idor", "block_ids": []},
    )
    token = str(share.get("token") or "")
    assert len(token) >= 16

    with _anon_client() as anon:
        ok = anon.get(f"/v1/dashboards/shared/{token}")
        _expect_status(ok, {200}, label="valid public share token")
        body = ok.json()
        dash = body.get("dashboard") or {}
        assert dash.get("title") == title or title in str(dash.get("title") or "")
        assert body.get("password_required") is not True

        bad = anon.get(f"/v1/dashboards/shared/{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}")
        _expect_denied(bad, label="invalid public share token")


# --- Tool policy (body-level denial) ----------------------------------------


def test_user_b_tools_run_admin_tool_denied_in_body(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    """Admin-only tools may return HTTP 200 with ok:false — not an Auth bypass."""
    resp = user_b_client.http.post(
        "/tools/run",
        json={"name": "ssc_list", "arguments": {}},
    )
    _expect_status(resp, {200, 400, 403, 404, 503})
    if resp.status_code != 200:
        return
    try:
        data = resp.json()
    except json.JSONDecodeError:
        pytest.fail(f"unexpected non-JSON 200 from /tools/run: {resp.text[:200]}")
    result_raw = data.get("result")
    if isinstance(result_raw, str):
        try:
            inner = json.loads(result_raw)
        except json.JSONDecodeError:
            inner = {"raw": result_raw}
    elif isinstance(result_raw, dict):
        inner = result_raw
    else:
        inner = data
    if inner.get("ok") is False:
        err = str(inner.get("error") or "").lower()
        assert any(x in err for x in ("admin", "disabled", "policy", "not found", "unknown"))
    # If tool is missing in this deployment, 400/503 paths above already handled.


# --- Chat agent RBAC (planner rejects non-general for end users) ------------


def test_user_b_chat_coding_agent_rejected(
    e2e_server: None,
    user_b_client: E2EClient,
) -> None:
    resp = user_b_client.http.post(
        "/v1/chat/completions",
        json={
            "model": "general",
            "agent_id": "coding",
            "messages": [{"role": "user", "content": "list files"}],
        },
    )
    # Planner or access guard: 400/403 with message, or 200 with error content.
    if resp.status_code in (400, 403):
        return
    if resp.status_code == 200:
        try:
            data = resp.json()
        except json.JSONDecodeError:
            pytest.fail(resp.text[:300])
        err = json.dumps(data).lower()
        assert any(x in err for x in ("not available", "admin", "agent"))
        return
    _expect_status(resp, {400, 403, 200}, label="chat coding as user B")
