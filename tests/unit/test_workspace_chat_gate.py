"""Tests for workspace fail-closed gate before chat tool loop."""

from __future__ import annotations

import unittest
import uuid

from apps.backend.application.agent_runtime.runtime.prompts import WorkspaceAccessDenied
from apps.backend.application.agent_runtime.runtime.io import _raise_if_workspace_inaccessible


class TestWorkspaceChatGate(unittest.TestCase):
    def test_raises_when_workspace_id_sent_but_not_resolved(self) -> None:
        uid = uuid.uuid4()
        wid = str(uuid.uuid4())
        with self.assertRaises(WorkspaceAccessDenied) as ctx:
            _raise_if_workspace_inaccessible(
                workspace_id=wid,
                user_id=uid,
                workspace=None,
                agent_id="coding",
            )
        self.assertIn("not available", str(ctx.exception))

    def test_ok_when_workspace_resolved(self) -> None:
        uid = uuid.uuid4()
        wid = str(uuid.uuid4())
        ws = {"id": wid, "path": "/tmp/x"}
        _raise_if_workspace_inaccessible(
            workspace_id=wid,
            user_id=uid,
            workspace=ws,
            agent_id="coding",
        )

    def test_coding_plan_requires_workspace(self) -> None:
        with self.assertRaises(WorkspaceAccessDenied) as ctx:
            _raise_if_workspace_inaccessible(
                workspace_id=None,
                user_id=uuid.uuid4(),
                workspace=None,
                agent_id="coding_plan",
            )
        self.assertIn("coding_plan", str(ctx.exception))

    def test_security_auditor_requires_workspace(self) -> None:
        with self.assertRaises(WorkspaceAccessDenied) as ctx:
            _raise_if_workspace_inaccessible(
                workspace_id=None,
                user_id=uuid.uuid4(),
                workspace=None,
                agent_id="security_auditor",
            )
        self.assertIn("security_auditor", str(ctx.exception))

    def test_whitespace_workspace_id_treated_as_missing(self) -> None:
        _raise_if_workspace_inaccessible(
            workspace_id="   ",
            user_id=uuid.uuid4(),
            workspace=None,
            agent_id="coding",
        )


if __name__ == "__main__":
    unittest.main()
