"""Bounded AGENTS.md / CLAUDE.md workspace instruction injection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.backend.infrastructure.workspace.workspace_agent_instructions import (
    agent_receives_workspace_instructions,
    build_workspace_agent_instructions_snippet,
    slice_instructions_for_agent,
)


class TestWorkspaceAgentInstructions(unittest.TestCase):
    def test_empty_without_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snip = build_workspace_agent_instructions_snippet(
                {"path": tmp, "name": "demo"}, agent_id="coding"
            )
        self.assertEqual(snip, "")

    def test_injects_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# Project\nUse npm test.\n", encoding="utf-8")
            snip = build_workspace_agent_instructions_snippet(
                {"path": str(root), "name": "demo"}, agent_id="coding"
            )
        self.assertIn("[Workspace instructions]", snip)
        self.assertIn("AGENTS.md", snip)
        self.assertIn("Use npm test.", snip)
        self.assertIn("do **not** override", snip)

    def test_general_receives_injection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("shared map\n", encoding="utf-8")
            snip = build_workspace_agent_instructions_snippet(
                {"path": str(root), "name": "demo"}, agent_id="general"
            )
        self.assertIn("shared map", snip)

    def test_math_does_not_receive_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("secret sauce\n", encoding="utf-8")
            snip = build_workspace_agent_instructions_snippet(
                {"path": str(root), "name": "demo"}, agent_id="math"
            )
        self.assertEqual(snip, "")
        self.assertFalse(agent_receives_workspace_instructions("math"))
        self.assertTrue(agent_receives_workspace_instructions("general"))

    def test_dedupes_identical_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "# Same\n"
            (root / "AGENTS.md").write_text(body, encoding="utf-8")
            (root / "CLAUDE.md").write_text(body, encoding="utf-8")
            snip = build_workspace_agent_instructions_snippet(
                {"path": str(root), "name": "demo"}, agent_id="coding"
            )
        self.assertEqual(snip.count("### Instructions from:"), 1)
        self.assertIn("AGENTS.md", snip)

    def test_local_overlay_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("base rules\n", encoding="utf-8")
            (root / "AGENTS.local.md").write_text("local only\n", encoding="utf-8")
            snip = build_workspace_agent_instructions_snippet(
                {"path": str(root), "name": "demo"}, agent_id="coding"
            )
        self.assertIn("AGENTS.md", snip)
        self.assertIn("AGENTS.local.md", snip)
        self.assertIn("local only", snip)

    def test_budget_omits_broader_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("B" * 2000 + "\n", encoding="utf-8")
            (root / "AGENTS.local.md").write_text("local-priority\n", encoding="utf-8")
            with patch(
                "apps.backend.infrastructure.platform.config.WORKSPACE_AGENT_INSTRUCTIONS_MAX_BYTES",
                800,
            ):
                snip = build_workspace_agent_instructions_snippet(
                    {"path": str(root), "name": "demo"}, agent_id="coding"
                )
        self.assertIn("local-priority", snip)
        self.assertIn("omitted AGENTS.md", snip)

    def test_skips_client_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("x\n", encoding="utf-8")
            snip = build_workspace_agent_instructions_snippet(
                {
                    "path": str(root),
                    "name": "demo",
                    "execution_mode": "client",
                },
                agent_id="coding",
            )
        self.assertEqual(snip, "")

    def test_disabled_by_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("x\n", encoding="utf-8")
            with patch(
                "apps.backend.infrastructure.platform.config.WORKSPACE_AGENT_INSTRUCTIONS_ENABLED",
                False,
            ):
                snip = build_workspace_agent_instructions_snippet(
                    {"path": str(root), "name": "demo"}, agent_id="coding"
                )
        self.assertEqual(snip, "")


class TestSliceInstructionsForAgent(unittest.TestCase):
    def test_no_sections_returns_full(self) -> None:
        text = "# Project\nDo the thing.\n"
        self.assertEqual(slice_instructions_for_agent(text, "coding"), text)

    def test_filters_for_sections(self) -> None:
        text = (
            "# Map\nshared line\n\n"
            "## For: general\nroute to coding\n\n"
            "## For: coding, coding_plan\nrun loga3 fetch\n\n"
            "## For: all\nalways here\n"
        )
        coding = slice_instructions_for_agent(text, "coding")
        general = slice_instructions_for_agent(text, "general")
        self.assertIn("shared line", coding)
        self.assertIn("run loga3 fetch", coding)
        self.assertIn("always here", coding)
        self.assertNotIn("route to coding", coding)
        self.assertIn("shared line", general)
        self.assertIn("route to coding", general)
        self.assertNotIn("run loga3 fetch", general)
        self.assertIn("always here", general)

    def test_html_comment_marker(self) -> None:
        text = "# Intro\n\n<!-- agent: coding -->\ncli only\n"
        self.assertIn("cli only", slice_instructions_for_agent(text, "coding"))
        self.assertNotIn("cli only", slice_instructions_for_agent(text, "general"))
        self.assertIn("Intro", slice_instructions_for_agent(text, "general"))


class TestAgentOverlayFile(unittest.TestCase):
    def test_loads_dot_agentlayer_agents_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("shared\n", encoding="utf-8")
            overlay = root / ".agentlayer" / "agents"
            overlay.mkdir(parents=True)
            (overlay / "general.md").write_text("general only tip\n", encoding="utf-8")
            snip_g = build_workspace_agent_instructions_snippet(
                {"path": str(root), "name": "demo"}, agent_id="general"
            )
            snip_c = build_workspace_agent_instructions_snippet(
                {"path": str(root), "name": "demo"}, agent_id="coding"
            )
        self.assertIn("general only tip", snip_g)
        self.assertNotIn("general only tip", snip_c)


if __name__ == "__main__":
    unittest.main()
