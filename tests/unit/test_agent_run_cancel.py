"""Parent run cancel propagates to embedded sub-agents via thread-safe registry."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend.infrastructure.agent_runtime import agent_registry_service as _agent_registry_service  # noqa: F401
from apps.backend.infrastructure.plugins import plugin_registry_service as _plugin_registry_service  # noqa: F401
from apps.backend.domain.agent_runtime.run_cancel import (
    parent_cancel_event,
    register_parent_cancel,
    reset_parent_cancel_registry_for_tests,
    signal_parent_cancel,
    unregister_parent_cancel,
)


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    reset_parent_cancel_registry_for_tests()
    yield
    reset_parent_cancel_registry_for_tests()


def test_signal_parent_cancel_sets_thread_event() -> None:
    register_parent_cancel("parent-1")
    ev = parent_cancel_event("parent-1")
    assert ev is not None
    assert not ev.is_set()
    signal_parent_cancel("parent-1")
    assert ev.is_set()
    unregister_parent_cancel("parent-1")
    assert parent_cancel_event("parent-1") is None


def test_root_cancel_propagates_to_nested_runs() -> None:
    from apps.backend.domain.agent_runtime.run_cancel import (
        link_run_to_cancel_root,
        root_cancel_event,
    )

    register_parent_cancel("root-run")
    link_run_to_cancel_root("child-run", "root-run")
    link_run_to_cancel_root("grandchild-run", "child-run")

    root_ev = root_cancel_event("root-run")
    child_ev = root_cancel_event("child-run")
    grand_ev = root_cancel_event("grandchild-run")
    assert root_ev is not None
    assert child_ev is root_ev
    assert grand_ev is root_ev
    assert not root_ev.is_set()

    signal_parent_cancel("root-run")
    assert root_ev.is_set()
    unregister_parent_cancel("root-run")


def test_delegate_subagent_receives_linked_cancel_event() -> None:
    from plugins.tools.platform.agents.delegate import delegate

    uid = uuid.uuid4()
    ws_id = uuid.uuid4()
    parent_id = "parent-run-abc"
    register_parent_cancel(parent_id)
    ctx = {
        "workspace": {"id": str(ws_id), "path": "/tmp/ws", "name": "w"},
        "user": type("U", (), {"id": uid})(),
        "agent_run_id": parent_id,
        "parent_effective_model": "__mock_ui_model__",
        "parent_model_catalog_owned_by": "__mock_ui_provider__",
        "cancel_event": asyncio.Event(),
    }
    seen_cancel: list[asyncio.Event | None] = []

    async def fake_cc(body: dict, **kwargs: object) -> dict:
        ce = kwargs.get("cancel_event")
        seen_cancel.append(ce if isinstance(ce, asyncio.Event) else None)
        if isinstance(ce, asyncio.Event):
            for _ in range(50):
                if ce.is_set():
                    return {"error": "cancelled", "choices": []}
                await asyncio.sleep(0.05)
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }

    with patch("apps.backend.application.agent_runtime.runtime.embedded_subagent._chat_completion_handler", new=AsyncMock(side_effect=fake_cc)):
        with patch("apps.backend.domain.shared.identity.get_identity", return_value=(1, uid)):
            with patch(
                "apps.backend.infrastructure.agent_runtime.agent_artifacts_store.create_artifact",
                return_value={"id": uuid.uuid4()},
            ):
                signal_parent_cancel(parent_id)
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
    assert seen_cancel and isinstance(seen_cancel[0], asyncio.Event)
    assert data.get("ok") is False or data.get("error")
