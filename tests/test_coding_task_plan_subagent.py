"""Smoke tests for ``coding_task`` default mode and ``run_plan_subagent`` (mocked ``chat_completion``)."""

from __future__ import annotations

import json
import unittest
import uuid
from unittest.mock import AsyncMock, patch


class TestCodingTaskPlanSubagent(unittest.TestCase):
    def test_plan_subagent_requires_prompt(self) -> None:
        from plugins.tools.capabilities.coding.coding_task import coding_task

        out = coding_task({"run_plan_subagent": True, "description": "x"}, context=None)
        data = json.loads(out)
        self.assertFalse(data.get("ok"))
        self.assertIn("prompt", (data.get("error") or "").lower())

    def test_default_mode_registers_task(self) -> None:
        from plugins.tools.capabilities.coding.coding_task import coding_task

        out = coding_task(
            {"description": "Smoke task", "prompt": "Do the thing"},
            context=None,
        )
        data = json.loads(out)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("status"), "pending")
        self.assertIn("task_id", data)

    def test_plan_subagent_invokes_chat_completion_with_coding_plan(self) -> None:
        from plugins.tools.capabilities.coding.coding_task import coding_task

        uid = uuid.uuid4()
        ws_id = uuid.uuid4()
        ctx = {
            "workspace": {"id": str(ws_id), "path": "/tmp/ws", "name": "w"},
            "user": type("U", (), {"id": uid})(),
            "agent_run_id": "parent-run-abc",
            "parent_effective_model": "__mock_ui_model__",
            "parent_model_catalog_owned_by": "__mock_ui_provider__",
        }

        bodies: list[dict] = []

        async def fake_cc(body: dict, **kwargs: object) -> dict:
            bodies.append(dict(body))
            return {
                "choices": [
                    {
                        "message": {"content": "Plan summary from mock."},
                        "finish_reason": "stop",
                    }
                ]
            }

        with patch("apps.backend.domain.agent.chat_completion", new=AsyncMock(side_effect=fake_cc)):
            with patch("apps.backend.domain.identity.get_identity", return_value=(1, uid)):
                with patch(
                    "apps.backend.infrastructure.agent_artifacts_store.create_artifact",
                    return_value={"id": uuid.uuid4()},
                ):
                    with patch(
                        "apps.backend.infrastructure.agent_runs_store.insert_run_start_resilient",
                        return_value=({"id": uuid.uuid4()}, []),
                    ):
                        with patch(
                            "apps.backend.infrastructure.agent_runs_store.finish_run",
                            return_value=True,
                        ):
                            out = coding_task(
                                {
                                    "run_plan_subagent": True,
                                    "prompt": "List entrypoints",
                                    "description": "plan",
                                },
                                context=ctx,
                            )

        data = json.loads(out)
        self.assertTrue(data.get("ok"), msg=data)
        self.assertEqual(data.get("mode"), "embedded_subagent")
        self.assertEqual(data.get("agent_id"), "coding_plan")
        self.assertIn("Plan summary", data.get("assistant_excerpt") or "")

        self.assertEqual(len(bodies), 1)
        b0 = bodies[0]
        self.assertEqual(b0.get("agent_id"), "coding_plan")
        self.assertEqual(b0.get("workspace_id"), str(ws_id))
        from apps.backend.core import config

        self.assertEqual(b0.get("agent_max_tool_rounds"), config.SUBAGENT_MAX_TOOL_ROUNDS)
        self.assertEqual(b0.get("agent_parent_run_id"), "parent-run-abc")
        self.assertEqual(
            b0.get("agent_tool_name_allowlist"),
            [
                "coding_list_dir",
                "coding_read_file",
                "coding_glob",
                "retrieve_context",
                "coding_search",
                "coding_git_read",
                "coding_semantic_search",
                "coding_symbols",
                "coding_lsp",
                "project_explain",
            ],
        )
        msgs = b0.get("messages") or []
        self.assertTrue(msgs)
        self.assertEqual(msgs[0].get("role"), "user")
        self.assertIn("List entrypoints", str(msgs[0].get("content") or ""))

    def test_plan_subagent_identity_fallback_from_context_user(self) -> None:
        """When ``get_identity`` has no user_id, ``context['user'].id`` + ``user_tenant_id`` is used."""
        from plugins.tools.capabilities.coding.coding_task import coding_task

        uid = uuid.uuid4()
        ws_id = uuid.uuid4()
        ctx = {
            "workspace": {"id": str(ws_id), "path": "/tmp/ws", "name": "w"},
            "user": type("U", (), {"id": uid})(),
            "parent_effective_model": "__mock_ui_model__",
            "parent_model_catalog_owned_by": "__mock_ui_provider__",
        }

        async def fake_cc(body: dict, **kwargs: object) -> dict:
            return {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
            }

        with patch("apps.backend.domain.agent.chat_completion", new=AsyncMock(side_effect=fake_cc)):
            with patch("apps.backend.domain.identity.get_identity", return_value=(1, None)):
                with patch(
                    "apps.backend.infrastructure.db.db.user_tenant_id",
                    return_value=42,
                ):
                    with patch(
                        "apps.backend.infrastructure.agent_artifacts_store.create_artifact",
                        return_value={"id": uuid.uuid4()},
                    ):
                        with patch(
                            "apps.backend.infrastructure.agent_runs_store.insert_run_start_resilient",
                            return_value=({"id": uuid.uuid4()}, []),
                        ):
                            with patch(
                                "apps.backend.infrastructure.agent_runs_store.finish_run",
                                return_value=True,
                            ):
                                out = coding_task(
                                    {
                                        "run_plan_subagent": True,
                                        "prompt": "x",
                                        "description": "d",
                                    },
                                    context=ctx,
                                )

        data = json.loads(out)
        self.assertTrue(data.get("ok"), msg=data)


if __name__ == "__main__":
    unittest.main()
