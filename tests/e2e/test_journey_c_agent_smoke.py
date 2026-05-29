"""Journey C — run-card persistence and optional WebSocket agent smoke (mock LLM)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest

from tests.e2e.helpers import (
    AGENTLAYER_SELF_NAME,
    E2EClient,
    env_truthy,
    find_workspace_by_name,
    sample_agent_log_v2,
    temporary_self_editing_enabled,
    ws_url,
)

pytestmark = pytest.mark.e2e


def test_conversation_run_card_agent_log_v2_roundtrip(admin_client: E2EClient) -> None:
    agent_log = sample_agent_log_v2()
    created = admin_client.post_json(
        "/v1/user/conversations",
        {
            "title": "E2E run cards",
            "mode": "agent",
            "model": "e2e",
            "agent_log": agent_log,
        },
    )
    conv = created.get("conversation") or created
    conv_id = str(conv.get("id") or "")
    assert conv_id

    loaded = admin_client.get_json(f"/v1/user/conversations/{conv_id}")
    row = loaded.get("conversation") or loaded
    stored = row.get("agent_log")
    assert isinstance(stored, dict)
    assert stored.get("v") == 2
    kinds = [e.get("kind") for e in stored.get("current") or [] if isinstance(e, dict)]
    assert "subagent_start" in kinds
    assert "subagent_done" in kinds


async def _collect_ws_events(
    token: str,
    chat_body: dict[str, Any],
    *,
    timeout_s: float = 90.0,
) -> list[dict[str, Any]]:
    import websockets

    events: list[dict[str, Any]] = []
    uri = ws_url(token)
    async with websockets.connect(uri, open_timeout=15, close_timeout=5) as ws:
        await ws.send(json.dumps({"type": "chat", "body": chat_body}))
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
            except asyncio.TimeoutError:
                break
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict):
                events.append(ev)
                if ev.get("type") in ("chat.completion", "agent.done", "error"):
                    if ev.get("type") == "error":
                        break
                    if ev.get("type") == "chat.completion" or ev.get("type") == "agent.done":
                        break
    return events


@pytest.mark.nightly
def test_websocket_agent_tool_smoke(admin_client: E2EClient) -> None:
    if not env_truthy("AGENT_E2E_MOCK_LLM"):
        pytest.skip("Set AGENT_E2E_MOCK_LLM=1 on the running server and in test env")

    if admin_client.role != "admin":
        pytest.skip("admin login required to toggle workspace_allow_self_editing for E2E")

    with temporary_self_editing_enabled(admin_client):
        ws = find_workspace_by_name(admin_client, AGENTLAYER_SELF_NAME)
        if not ws:
            pytest.skip("agentlayer-self workspace not available for coding tool smoke")

        chat_body: dict[str, Any] = {
            "model": "e2e-mock",
            "messages": [{"role": "user", "content": "List the workspace root directory."}],
            "agent_id": "general",
            "workspace_id": str(ws["id"]),
            "agent_max_tool_rounds": 3,
            "agent_unattended": True,
        }

        events = asyncio.run(_collect_ws_events(admin_client.token, chat_body, timeout_s=120.0))

    types = [e.get("type") for e in events]
    assert "agent.session" in types or "chat.completion" in types or "agent.tool_start" in types, types
    assert any(
        t in types
        for t in ("agent.tool_start", "agent.tool_done", "agent.done", "chat.completion")
    ), f"expected agent activity events, got: {types}"

    if any(e.get("type") == "error" for e in events):
        details = [e.get("detail") for e in events if e.get("type") == "error"]
        pytest.fail(f"WebSocket chat error: {details}")
