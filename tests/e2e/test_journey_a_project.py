"""Journey A — project workspace: agentlayer-self, git clone, task binding."""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.helpers import (
    AGENTLAYER_SELF_NAME,
    E2E_GIT_WORKSPACE_NAME,
    E2EClient,
    env_truthy,
    ensure_git_workspace,
    find_workspace_by_name,
    git_clone_url,
    temporary_self_editing_enabled,
    wait_index_idle,
)

pytestmark = pytest.mark.e2e


def test_agentlayer_self_listed(admin_client: E2EClient) -> None:
    if admin_client.role != "admin":
        pytest.skip("admin login required to toggle workspace_allow_self_editing for E2E")

    with temporary_self_editing_enabled(admin_client):
        data = admin_client.get_json("/v1/workspaces")
        names = [
            (w.get("name") or "").strip()
            for w in data.get("workspaces") or []
            if isinstance(w, dict)
        ]
        if AGENTLAYER_SELF_NAME not in names:
            pytest.skip(
                "agentlayer-self not listed after enabling self-editing "
                "(git seed missing under /workspace/AgentLayer or /app in the running container)"
            )
        self_ws = find_workspace_by_name(admin_client, AGENTLAYER_SELF_NAME)
        assert self_ws is not None
        assert self_ws.get("id")


def test_cannot_create_reserved_self_workspace_name(admin_client: E2EClient) -> None:
    import httpx

    with pytest.raises(httpx.HTTPStatusError) as exc:
        admin_client.post_json(
            "/v1/workspaces",
            {"name": AGENTLAYER_SELF_NAME, "source": "manual"},
        )
    assert exc.value.response.status_code == 400


def test_git_workspace_and_task_binding(admin_client: E2EClient) -> None:
    git_url = git_clone_url()
    ws = ensure_git_workspace(admin_client, name=E2E_GIT_WORKSPACE_NAME, git_url=git_url)
    ws_id = str(ws["id"])
    assert ws.get("name") == E2E_GIT_WORKSPACE_NAME

    task = admin_client.post_json(
        "/v1/tasks",
        {
            "scope": "workspace",
            "goal": "E2E journey A — verify task API wiring",
            "workspace_id": ws_id,
            "status": "draft",
        },
    )
    task_row = task.get("task") or {}
    task_id = str(task_row.get("id") or "")
    assert task_id

    conv = admin_client.post_json(
        "/v1/user/conversations",
        {
            "title": "E2E journey A",
            "mode": "agent",
            "model": "e2e",
            "workspace_id": ws_id,
        },
    )
    conv_id = str((conv.get("conversation") or conv).get("id") or conv.get("id") or "")
    if not conv_id:
        conv_id = str(conv.get("id") or "")
    assert conv_id

    bound = admin_client.patch_json(
        f"/v1/user/conversations/{conv_id}/active-task",
        {"active_task_id": task_id},
    )
    assert bound.get("ok") is True
    assert str(bound.get("active_task_id") or "") == task_id

    listed = admin_client.get_json("/v1/tasks", workspace_id=ws_id)
    tasks = listed.get("tasks") or []
    assert any(str(t.get("id")) == task_id for t in tasks if isinstance(t, dict))


@pytest.mark.nightly
def test_optional_workspace_reindex(admin_client: E2EClient) -> None:
    if not env_truthy("AGENT_E2E_RUN_INDEX"):
        pytest.skip("Set AGENT_E2E_RUN_INDEX=1 to run semantic index E2E")

    ws = find_workspace_by_name(admin_client, E2E_GIT_WORKSPACE_NAME)
    if not ws:
        ws = ensure_git_workspace(admin_client, name=E2E_GIT_WORKSPACE_NAME, git_url=git_clone_url())
    ws_id = str(ws["id"])

    try:
        admin_client.patch_json(
            f"/v1/workspaces/{ws_id}",
            {"semantic_index_enabled": True},
        )
    except Exception:
        pass

    kick = admin_client.post_json(f"/v1/workspaces/{ws_id}/index", {"mode": "code", "max_files": 200})
    assert kick.get("ok") is True
    assert kick.get("started") or kick.get("already_running")

    status = wait_index_idle(admin_client, ws_id, timeout_s=180.0)
    assert status
