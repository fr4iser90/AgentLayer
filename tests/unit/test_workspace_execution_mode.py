"""ADR 0009 milestone 1: client workspaces are placed, not executed."""

from __future__ import annotations

import json
import unittest

from apps.backend.infrastructure.workspace.workspace_columns import (
    CLIENT_EXECUTION,
    SERVER_EXECUTION,
    normalize_execution_mode,
)
from apps.backend.infrastructure.workspace.workspace_execution import is_client_execution
from apps.backend.infrastructure.workspace.workspace_service import (
    WorkspaceCreateError,
    validate_client_workspace_path,
)
from plugins.tools.workspace.lib.common import (
    ClientWorkspaceExecutionError,
    workspace_binding_from_context,
    workspace_retrieval_flags,
)


class TestNormalize(unittest.TestCase):
    def test_only_client_is_client(self) -> None:
        self.assertEqual(normalize_execution_mode("client"), CLIENT_EXECUTION)
        self.assertEqual(normalize_execution_mode("CLIENT"), CLIENT_EXECUTION)
        self.assertEqual(normalize_execution_mode("server"), SERVER_EXECUTION)
        self.assertEqual(normalize_execution_mode("remote"), SERVER_EXECUTION)
        self.assertEqual(normalize_execution_mode(None), SERVER_EXECUTION)
        self.assertFalse(is_client_execution("server"))
        self.assertTrue(is_client_execution("client"))


class TestClientPath(unittest.TestCase):
    def test_accepts_posix_and_windows_absolutes(self) -> None:
        self.assertEqual(validate_client_workspace_path("  /home/me/repo  "), "/home/me/repo")
        self.assertEqual(validate_client_workspace_path("C:\\Users\\me\\repo"), "C:\\Users\\me\\repo")
        self.assertEqual(validate_client_workspace_path("\\\\nas\\share\\repo"), "\\\\nas\\share\\repo")

    def test_rejects_relative_and_empty(self) -> None:
        for bad in ("", "   ", "repo", "./repo", "../escape"):
            with self.assertRaises(WorkspaceCreateError, msg=bad):
                validate_client_workspace_path(bad)


class TestBinding(unittest.TestCase):
    def test_server_workspace_still_binds(self) -> None:
        ws = {"id": "1", "path": "/data/ws", "execution_mode": "server"}
        self.assertEqual(workspace_binding_from_context({"workspace": ws}), ws)

    def test_client_workspace_raises_before_any_path_is_opened(self) -> None:
        ws = {"id": "1", "name": "laptop", "path": "/home/me/repo", "execution_mode": "client"}
        with self.assertRaises(ClientWorkspaceExecutionError) as ctx:
            workspace_binding_from_context({"workspace": ws})
        self.assertIn("runs on the client", str(ctx.exception))
        self.assertIn("ADR 0009", str(ctx.exception))

    def test_client_without_a_path_still_raises(self) -> None:
        with self.assertRaises(ClientWorkspaceExecutionError):
            workspace_binding_from_context(
                {"workspace": {"id": "1", "execution_mode": "client"}}
            )

    def test_retrieval_flags_still_read_a_server_workspace(self) -> None:
        sem, ret = workspace_retrieval_flags(
            {
                "workspace": {
                    "id": "1",
                    "path": "/tmp/ws",
                    "semantic_index_enabled": False,
                    "retrieval_enabled": True,
                }
            }
        )
        self.assertFalse(sem)
        self.assertTrue(ret)

    def test_run_tool_turns_the_raise_into_a_json_error(self) -> None:
        from apps.backend.domain.plugin_system.tool_registry_runtime import run_tool

        class _Reg:
            _lock = __import__("threading").Lock()
            _handlers = {
                "coding_read_file": lambda args, context=None: workspace_binding_from_context(
                    context
                )
            }

        class _Deps:
            def log_tool_invocation(self, *a, **k):
                return None

        out = run_tool(
            _Reg(),
            _Deps(),
            "coding_read_file",
            {"path": "README.md"},
            context={
                "workspace": {
                    "id": "1",
                    "name": "laptop",
                    "path": "/home/me/repo",
                    "execution_mode": "client",
                }
            },
        )
        payload = json.loads(out)
        self.assertFalse(payload.get("ok"))
        self.assertIn("runs on the client", payload.get("error", ""))
