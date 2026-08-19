"""Sub-agent uses a thread-safe cancel bridge (not the parent's asyncio.Event)."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend.infrastructure.agent_runtime import agent_registry_service as _agent_registry_service  # noqa: F401
from apps.backend.infrastructure.plugins import plugin_registry_service as _plugin_registry_service  # noqa: F401
from apps.backend.domain.agent_runtime.run_cancel import (
    register_parent_cancel,
    reset_parent_cancel_registry_for_tests,
    unregister_parent_cancel,
)


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    reset_parent_cancel_registry_for_tests()
    yield
    reset_parent_cancel_registry_for_tests()


def test_delegate_uses_subagent_cancel_event_not_parent_asyncio_event() -> None:
    from plugins.tools.platform.agents.delegate import delegate

    uid = uuid.uuid4()
    ws_id = uuid.uuid4()
    parent_cancel = asyncio.Event()
    parent_id = "parent-run"
    register_parent_cancel(parent_id)
    ctx = {
        "workspace": {"id": str(ws_id), "path": "/tmp/ws", "name": "w"},
        "user": type("U", (), {"id": uid})(),
        "agent_run_id": parent_id,
        "parent_effective_model": "__mock_ui_model__",
        "parent_model_catalog_owned_by": "__mock_ui_provider__",
        "cancel_event": parent_cancel,
    }

    async def fake_cc(body: dict, **kwargs: object) -> dict:
        ce = kwargs.get("cancel_event")
        assert ce is not None
        assert ce is not parent_cancel
        return {
            "choices": [{"message": {"content": "Plan summary from mock sub-agent."}, "finish_reason": "stop"}],
        }

    with patch("apps.backend.application.agent_runtime.runtime.embedded_subagent._chat_completion_handler", new=AsyncMock(side_effect=fake_cc)):
        with patch("apps.backend.domain.shared.identity.get_identity", return_value=(1, uid)):
            with patch(
                "apps.backend.infrastructure.agent_runtime.agent_artifacts_store.create_artifact",
                return_value={"id": uuid.uuid4()},
            ):
                out = delegate(
                    {
                        "run_subagent": True,
                        "agent_id": "research",
                        "prompt": "ping",
                        "description": "test",
                    },
                    context=ctx,
                )
    unregister_parent_cancel(parent_id)
    data = json.loads(out)
    assert data.get("ok") is True, data
