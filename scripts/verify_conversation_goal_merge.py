#!/usr/bin/env python3
"""Verify the conversation goal/todo layer is shared by every capable agent.

Checks that the coding agents expose the goal/todo tools instead of the old process-global
``todo``, that the chat runtime snapshot carries the per-conversation state, that the
retired HTTP endpoints are really gone, and that the system block built from that state
names the current goal and todos.

Goal creation and todo writes are agent tool calls, so they have no HTTP surface — the only
endpoint left is the goal transition the user drives from the goal bar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from apps.backend.domain.agent_runtime.conversation_goal import (  # noqa: E402
    conversation_goal_prompt_block,
)
from tests.e2e.support.helpers import admin_credentials, base_url, load_e2e_env  # noqa: E402

GOAL_TOOLS = {"goal_get", "goal_create", "goal_update"}
TODO_TOOLS = {"todo_write", "todo_read"}
PLAN_TOOLS = {"plan_mode_set", "exit_plan_mode"}

# agent_id -> tools it must expose
EXPECTED: dict[str, set[str]] = {
    "general": GOAL_TOOLS | TODO_TOOLS | PLAN_TOOLS,
    "coding": GOAL_TOOLS | TODO_TOOLS | PLAN_TOOLS,
    "coding_plan": GOAL_TOOLS | TODO_TOOLS | PLAN_TOOLS,
    "security_auditor": GOAL_TOOLS | TODO_TOOLS,
}

# Retired with the /v1/session/harness prefix; the UI never called them.
RETIRED = (
    ("GET", "/v1/session/harness"),
    ("POST", "/v1/session/harness/goal"),
    ("PATCH", "/v1/session/harness/goal"),
    ("PUT", "/v1/session/harness/todos"),
    ("GET", "/v1/session/runtime"),
)


def _login(client: httpx.Client) -> dict[str, str]:
    email, password = admin_credentials()
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _check_agents(client: httpx.Client, headers: dict[str, str]) -> list[str]:
    failures: list[str] = []
    rows = client.get("/v1/agents", headers=headers).json()
    by_id = {str(a.get("id")): a for a in rows if isinstance(a, dict)}
    for agent_id, expected in EXPECTED.items():
        agent = by_id.get(agent_id)
        if agent is None:
            failures.append(f"{agent_id}: agent not in catalog")
            continue
        # The catalog exposes the declared allowlist; tool_names is the resolved runtime set.
        names = set(agent.get("tool_allowlist") or []) | set(agent.get("tool_names") or [])
        missing = sorted(expected - names)
        if missing:
            failures.append(f"{agent_id}: missing goal/todo tools {missing}")
        if "todo" in names:
            failures.append(f"{agent_id}: still exposes the removed process-global `todo` tool")
    return failures


def _conversation_id(client: httpx.Client, headers: dict[str, str]) -> str:
    r = client.post(
        "/v1/user/conversations",
        headers=headers,
        json={"title": "conversation goal check", "agent_id": "coding", "messages": []},
    )
    r.raise_for_status()
    cid = str(((r.json() or {}).get("conversation") or {}).get("id") or "").strip()
    if not cid:
        raise SystemExit(f"could not create conversation: {r.text[:200]}")
    return cid


def _check_retired_endpoints(client: httpx.Client, headers: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for method, path in RETIRED:
        r = client.request(method, path, headers=headers, json={})
        if r.status_code not in (404, 405):
            failures.append(f"{method} {path} still answers {r.status_code}, expected 404/405")
    return failures


def _check_runtime_snapshot(
    client: httpx.Client, headers: dict[str, str], conv_id: str
) -> list[str]:
    failures: list[str] = []
    r = client.get("/v1/chat/runtime", headers=headers, params={"conversation_id": conv_id})
    if r.status_code != 200:
        return [f"GET /v1/chat/runtime failed: {r.status_code} {r.text[:200]}"]
    payload = r.json() or {}
    if "conversation_goal" not in payload:
        failures.append(f"runtime snapshot has no conversation_goal key: {sorted(payload)}")
        return failures
    state = payload.get("conversation_goal") or {}
    if state.get("goal") is not None:
        failures.append(f"fresh conversation already has a goal: {state.get('goal')!r}")
    if state.get("todos") != []:
        failures.append(f"fresh conversation already has todos: {state.get('todos')!r}")
    return failures


def _check_goal_endpoint_routed(
    client: httpx.Client, headers: dict[str, str], conv_id: str
) -> list[str]:
    """The goal bar's only endpoint: reachable, and rejecting an unknown goal cleanly."""
    r = client.patch(
        f"/v1/user/conversations/{conv_id}/goal",
        headers=headers,
        json={"goal_id": "does-not-exist", "revision": 1, "action": "pause"},
    )
    if r.status_code not in (400, 404, 409):
        return [
            f"PATCH /v1/user/conversations/{{id}}/goal returned {r.status_code} "
            f"for an unknown goal, expected a 4xx: {r.text[:200]}"
        ]
    return []


def _check_prompt_block() -> list[str]:
    failures: list[str] = []
    objective = "Verify the conversation goal layer"
    goal = {"id": "g_1", "revision": 3, "objective": objective, "phase": "active"}
    todos = [
        {"content": "Read the goal code", "status": "completed"},
        {"content": "Wire the prompt block", "status": "in_progress"},
        {"content": "Verify live", "status": "pending"},
    ]
    block = conversation_goal_prompt_block(
        tool_names=sorted(GOAL_TOOLS | TODO_TOOLS | PLAN_TOOLS),
        goal=goal,
        todos=todos,
        plan_mode=False,
    )
    for needle in (objective, "- [>] Wire the prompt block", "- [x] Read the goal code"):
        if needle not in block:
            failures.append(f"prompt block missing {needle!r}")
    if "goal_id=g_1" not in block:
        failures.append("prompt block missing goal_id for optimistic locking")
    return failures


def main() -> int:
    load_e2e_env()
    with httpx.Client(base_url=base_url(), timeout=60.0) as client:
        headers = _login(client)
        conv_id = _conversation_id(client, headers)
        failures = _check_agents(client, headers)
        failures += _check_retired_endpoints(client, headers)
        failures += _check_runtime_snapshot(client, headers, conv_id)
        failures += _check_goal_endpoint_routed(client, headers, conv_id)
    failures += _check_prompt_block()

    if failures:
        print("FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK — goal/todo tools shared, state in /v1/chat/runtime, retired routes gone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
