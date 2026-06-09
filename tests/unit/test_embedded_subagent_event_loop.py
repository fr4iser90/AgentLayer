"""Sub-agent must not reuse the parent asyncio cancel_event (different event loop)."""

from __future__ import annotations

import asyncio
import json
import unittest
import uuid
from unittest.mock import AsyncMock, patch


class TestEmbeddedSubagentEventLoop(unittest.TestCase):
    def test_delegate_ignores_parent_cancel_event(self) -> None:
        from plugins.tools.platform.agents.delegate import delegate

        uid = uuid.uuid4()
        ws_id = uuid.uuid4()
        parent_cancel = asyncio.Event()
        ctx = {
            "workspace": {"id": str(ws_id), "path": "/tmp/ws", "name": "w"},
            "user": type("U", (), {"id": uid})(),
            "agent_run_id": "parent-run",
            "parent_effective_model": "__mock_ui_model__",
            "parent_model_catalog_owned_by": "__mock_ui_provider__",
            "cancel_event": parent_cancel,
        }

        async def fake_cc(body: dict, **kwargs: object) -> dict:
            self.assertIsNone(kwargs.get("cancel_event"))
            return {
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"},
                ]
            }

        with patch("apps.backend.domain.agent.chat_completion", new=AsyncMock(side_effect=fake_cc)):
            with patch("apps.backend.domain.identity.get_identity", return_value=(1, uid)):
                with patch(
                    "apps.backend.infrastructure.agent_artifacts_store.create_artifact",
                    return_value={"id": uuid.uuid4()},
                ):
                    out = delegate(
                        {
                            "run_subagent": True,
                            "agent_id": "coding_plan",
                            "prompt": "ping",
                            "description": "test",
                        },
                        context=ctx,
                    )

        data = json.loads(out)
        self.assertTrue(data.get("ok"), msg=data)
