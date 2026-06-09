"""Tests for ``workspace_verify`` (DB ``verify_command`` on workspace dict)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plugins.tools.workspace.shell.workspace_verify import workspace_verify
from apps.backend.domain.agent import _format_workspace_verify_recap


class _User:
    def __init__(self, uid: str) -> None:
        self.id = uid


class TestCodingWorkspaceVerify(unittest.TestCase):
    def test_runs_verify_command_from_workspace_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = {
                "user": _User("00000000-0000-0000-0000-000000000099"),
                "agent_run_id": "run-test",
                "workspace": {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "path": str(root),
                    "verify_command": "echo VERIFY_OK",
                },
            }
            out = workspace_verify({}, context=ctx)
            data = json.loads(out)
            self.assertTrue(data.get("ok"), msg=data)
            self.assertEqual(data.get("exit_code"), 0)
            self.assertIn("VERIFY_OK", data.get("output") or "")

    def test_missing_verify_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = {
                "user": _User("00000000-0000-0000-0000-000000000099"),
                "workspace": {"id": "00000000-0000-0000-0000-000000000002", "path": tmp},
            }
            out = workspace_verify({}, context=ctx)
            data = json.loads(out)
            self.assertFalse(data.get("ok"))
            self.assertIn("not set", (data.get("error") or "").lower())

    def test_blocked_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = {
                "user": _User("00000000-0000-0000-0000-000000000099"),
                "workspace": {
                    "id": "00000000-0000-0000-0000-000000000003",
                    "path": str(root),
                    "verify_command": "rm -rf /",
                },
            }
            out = workspace_verify({}, context=ctx)
            data = json.loads(out)
            self.assertFalse(data.get("ok"))
            self.assertIn("blocked", (data.get("error") or "").lower())

    def test_format_recap_from_tool_json(self) -> None:
        raw = json.dumps(
            {
                "ok": True,
                "exit_code": 0,
                "verify_command": "echo hi",
                "output": "hi\n",
            }
        )
        recap = _format_workspace_verify_recap(raw)
        self.assertIsNotNone(recap)
        assert recap is not None
        self.assertIn("[Workspace verify recap]", recap)
        self.assertIn("exit_code: 0", recap)


if __name__ == "__main__":
    unittest.main()
