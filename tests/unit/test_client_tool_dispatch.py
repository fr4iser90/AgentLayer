"""ADR 0009 milestone 2: client tool dispatch, timeouts, caps, capability filter."""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

from apps.backend.application.agent_runtime.use_cases.chat_client_dispatch import (
    advertised_workspace_tools,
    cap_client_tool_result,
    dispatch_client_workspace_tool,
    filter_tools_for_client_workspace,
    wait_for_client_tool_result,
    workspace_is_client,
)
from apps.backend.application.agent_runtime.use_cases.chat_tool_execution import (
    execute_tool_with_agent_policy,
)


def _spec(name: str) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name}}


class TestFilter(unittest.TestCase):
    def test_drops_unadvertised_path_tools_and_keeps_the_rest(self) -> None:
        specs = [
            _spec("read_file"),
            _spec("retrieve_context"),
            _spec("list"),
            _spec("web_search"),
            _spec("bash"),
        ]
        kept = filter_tools_for_client_workspace(specs, advertised_workspace_tools(["read_file", "bash"]))
        names = [s["function"]["name"] for s in kept]
        self.assertEqual(names, ["read_file", "retrieve_context", "list", "web_search", "bash"])
        self.assertIn("retrieve_context", names)

    def test_empty_advertisement_drops_every_path_tool(self) -> None:
        specs = [_spec("read_file"), _spec("list"), _spec("memory_search")]
        kept = filter_tools_for_client_workspace(specs, frozenset())
        names = [s["function"]["name"] for s in kept]
        self.assertEqual(names, ["list", "memory_search"])


class TestWorkspaceFlag(unittest.TestCase):
    def test_only_client_mode_counts(self) -> None:
        self.assertTrue(
            workspace_is_client({"workspace": {"path": "/home/me/repo", "execution_mode": "client"}})
        )
        self.assertFalse(
            workspace_is_client({"workspace": {"path": "/data/ws", "execution_mode": "server"}})
        )
        self.assertFalse(workspace_is_client({}))


class TestCap(unittest.TestCase):
    def test_long_result_is_truncated_on_the_server(self) -> None:
        text = "x" * 5000
        out = cap_client_tool_result(text, max_chars=1000)
        self.assertLess(len(out), 1100)
        self.assertIn("truncated by server", out)


class TestWaitLoop(unittest.IsolatedAsyncioTestCase):
    async def test_matching_result_is_returned_and_unknown_ids_are_ignored(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        emitted: list[dict[str, Any]] = []

        async def emit(ev: dict[str, Any]) -> None:
            emitted.append(ev)

        async def produce() -> None:
            await queue.put({"type": "tool_result", "request_id": "other", "ok": True, "result": "nope"})
            await queue.put({"type": "permission_reply", "request_id": "rid-1", "reply": "once"})
            await queue.put(
                {"type": "tool_result", "request_id": "rid-1", "ok": True, "result": '{"ok": true, "content": "hi"}'}
            )

        asyncio.create_task(produce())
        out = await wait_for_client_tool_result(
            control_queue=queue,
            cancel_event=asyncio.Event(),
            event_emit=emit,
            agent_run_id="run",
            request_id="rid-1",
            tool_name="read_file",
            arguments={"path": "README.md"},
            round_i=0,
            handle_control=lambda m: False,
            timeout_sec=2.0,
            max_chars=8000,
        )
        self.assertIn("hi", out)
        self.assertEqual(emitted[0]["type"], "agent.tool_invoke")
        self.assertEqual(emitted[0]["request_id"], "rid-1")

    async def test_timeout_becomes_a_tool_error(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        out = await wait_for_client_tool_result(
            control_queue=queue,
            cancel_event=asyncio.Event(),
            event_emit=None,
            agent_run_id="run",
            request_id="rid",
            tool_name="read_file",
            arguments={},
            round_i=0,
            handle_control=lambda m: False,
            timeout_sec=0.05,
            max_chars=8000,
        )
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("timed out", payload["error"])

    async def test_unadvertised_dispatch_is_unsupported(self) -> None:
        out = await dispatch_client_workspace_tool(
            name="search",
            args={"query": "x"},
            tool_context={
                "workspace": {"path": "/home/me/repo", "execution_mode": "client"},
                "client_workspace_tools": {"read_file"},
            },
            control_queue=asyncio.Queue(),
            cancel_event=None,
            event_emit=None,
            agent_run_id="run",
            round_i=0,
            handle_control_dict=lambda m: False,
        )
        self.assertEqual(json.loads(out), {"ok": False, "error": "unsupported"})


class TestExecutePolicyFork(unittest.IsolatedAsyncioTestCase):
    async def test_client_workspace_dispatches_instead_of_opening_the_path(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        request_ids: list[str] = []

        async def emit(ev: dict[str, Any]) -> None:
            if ev.get("type") == "agent.tool_invoke":
                request_ids.append(str(ev.get("request_id")))
                await queue.put(
                    {
                        "type": "tool_result",
                        "request_id": ev.get("request_id"),
                        "ok": True,
                        "result": '{"ok": true, "content": "from-laptop"}',
                    }
                )

        out = await execute_tool_with_agent_policy(
            name="read_file",
            args={"path": "README.md"},
            messages=[],
            tool_context={
                "workspace": {
                    "id": "1",
                    "name": "laptop",
                    "path": "/does-not-exist-on-server",
                    "execution_mode": "client",
                },
                "client_workspace_tools": {"read_file"},
            },
            permission_ask=True,
            control_queue=queue,
            cancel_event=asyncio.Event(),
            event_emit=emit,
            agent_run_id="run",
            round_i=0,
            handle_control_dict=lambda m: False,
        )
        self.assertIn("from-laptop", out)
        self.assertEqual(len(request_ids), 1)
