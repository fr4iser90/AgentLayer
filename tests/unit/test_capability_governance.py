"""Unit tests for capability gate (ADR 0003)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from apps.backend.domain.plugin_system import capability_governance as cg
from apps.backend.domain.tool_invocation_context import (
    bind_capability_confirmed,
    reset_capability_confirmed,
)


class TestCapabilityGovernance(unittest.TestCase):
    def test_parse_user_capability_confirm(self) -> None:
        self.assertEqual(cg.parse_user_capability_confirm(None), frozenset())
        self.assertEqual(
            cg.parse_user_capability_confirm("A, B"),
            frozenset({"a", "b"}),
        )
        self.assertEqual(
            cg.parse_user_capability_confirm(["X", "y"]),
            frozenset({"x", "y"}),
        )

    @patch.dict(
        os.environ,
        {
            "AGENT_CAPABILITY_GATE_ALLOW": "",
            "AGENT_CAPABILITY_GATE_BLOCK": "secrets.user",
            "AGENT_CAPABILITY_GATE_CONFIRM": "",
        },
        clear=False,
    )
    def test_block_hits_declared_capability(self) -> None:
        meta = {"capabilities": ("secrets.user",)}
        err = cg.capability_gate_error_json("t", meta)
        self.assertIsNotNone(err)
        data = json.loads(err or "{}")
        self.assertEqual(data.get("code"), "capability_blocked")

    @patch.dict(
        os.environ,
        {
            "AGENT_CAPABILITY_GATE_ALLOW": "weather.observe",
            "AGENT_CAPABILITY_GATE_BLOCK": "",
            "AGENT_CAPABILITY_GATE_CONFIRM": "",
        },
        clear=False,
    )
    def test_allow_denies_unclassified(self) -> None:
        meta = {"capabilities": ()}
        err = cg.capability_gate_error_json("t", meta)
        self.assertIsNotNone(err)
        data = json.loads(err or "{}")
        self.assertEqual(data.get("code"), "capability_unclassified")

    @patch.dict(
        os.environ,
        {
            "AGENT_CAPABILITY_GATE_ALLOW": "weather.observe",
            "AGENT_CAPABILITY_GATE_BLOCK": "",
            "AGENT_CAPABILITY_GATE_CONFIRM": "",
        },
        clear=False,
    )
    def test_allow_passes_intersection(self) -> None:
        meta = {"capabilities": ("weather.observe",)}
        self.assertIsNone(cg.capability_gate_error_json("t", meta))

    @patch.dict(
        os.environ,
        {
            "AGENT_CAPABILITY_GATE_ALLOW": "",
            "AGENT_CAPABILITY_GATE_BLOCK": "",
            "AGENT_CAPABILITY_GATE_CONFIRM": "dashboard.files",
        },
        clear=False,
    )
    def test_confirm_requires_user_set(self) -> None:
        meta = {"capabilities": ("dashboard.files",)}
        err = cg.capability_gate_error_json("t", meta)
        self.assertIsNotNone(err)
        data = json.loads(err or "{}")
        self.assertEqual(data.get("code"), "capability_confirm_required")

        tok = bind_capability_confirmed(frozenset({"dashboard.files"}))
        try:
            self.assertIsNone(cg.capability_gate_error_json("t", meta))
        finally:
            reset_capability_confirmed(tok)

    @patch.dict(
        os.environ,
        {
            "AGENT_CAPABILITY_GATE_ALLOW": "",
            "AGENT_CAPABILITY_GATE_BLOCK": "",
            "AGENT_CAPABILITY_GATE_CONFIRM": "",
        },
        clear=False,
    )
    def test_all_empty_env_short_circuits(self) -> None:
        meta = {"capabilities": ("anything",)}
        self.assertIsNone(cg.capability_gate_error_json("t", meta))


if __name__ == "__main__":
    unittest.main()
