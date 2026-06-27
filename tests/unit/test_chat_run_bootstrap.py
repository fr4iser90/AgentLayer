from __future__ import annotations

import asyncio
import importlib
import uuid

import pytest

from apps.backend.application.agent_runtime.use_cases.chat_run_bootstrap import bootstrap_chat_run
from apps.backend.domain.shared.identity import get_benchmark_run_id, reset_workspace
from apps.backend.domain.tools.invocation_context import reset_agent_run_id, reset_agent_task_id

chat_completion_mod = importlib.import_module(
    "apps.backend.application.agent_runtime.use_cases.chat_completion"
)


def _base_bootstrap_kwargs(**overrides):
    kwargs = {
        "body": {"messages": [{"role": "user", "content": "hello"}]},
        "agent_id": None,
        "embedded_subagent": False,
        "bearer_user_role": None,
        "agent_storage_images": [],
        "pre_run_id": None,
        "parent_agent_run_id": None,
        "cancel_event": None,
        "event_emit": None,
        "agent_unattended": False,
        "agent_delegate_mode": None,
        "delegate_allowed_paths": None,
        "delegate_required_branch": None,
        "handoff_collector": None,
        "active_task_body": None,
        "agent_require_workspace_verify": False,
    }
    kwargs.update(overrides)
    return kwargs


def _cleanup_bootstrap(result) -> None:
    reset_workspace(result.workspace_token)
    reset_agent_run_id(result.run_ctx_token)
    reset_agent_task_id(result.task_ctx_token)


def test_chat_completion_does_not_forward_benchmark_run_id(monkeypatch) -> None:
    seen_body: dict[str, object] = {}
    bench_run_id = uuid.uuid4()

    async def fake_bootstrap_chat_run(**kwargs):
        seen_body.update(kwargs["body"])
        assert get_benchmark_run_id() == bench_run_id
        raise RuntimeError("stop-after-bootstrap-args")

    monkeypatch.setattr(chat_completion_mod, "bootstrap_chat_run", fake_bootstrap_chat_run)

    body = {
        "messages": [{"role": "user", "content": "hi"}],
        "benchmark_run_id": str(bench_run_id),
    }
    with pytest.raises(RuntimeError, match="stop-after-bootstrap-args"):
        asyncio.run(chat_completion_mod.chat_completion(body))

    assert "benchmark_run_id" not in seen_body
    assert get_benchmark_run_id() is None


def test_bootstrap_chat_run_normal_chat_has_no_benchmark_token() -> None:
    async def run() -> None:
        result = await bootstrap_chat_run(**_base_bootstrap_kwargs())
        try:
            assert result.bench_run_ctx_token is None
            assert "benchmark_run_id" not in result.tool_context
            assert result.parent_cancel_bridge_task is None
            assert result.tool_context["embedded_subagent"] is False
        finally:
            _cleanup_bootstrap(result)

    asyncio.run(run())


def test_bootstrap_chat_run_event_and_image_context(monkeypatch) -> None:
    token = object()
    captured_notifier = {}

    def fake_bind_llm_wait_notifier(callback):
        captured_notifier["callback"] = callback
        return token

    monkeypatch.setattr(
        "apps.backend.application.agent_runtime.use_cases.chat_run_bootstrap.bind_llm_wait_notifier",
        fake_bind_llm_wait_notifier,
    )

    emitted: list[dict[str, object]] = []

    async def event_emit(event: dict[str, object]) -> None:
        emitted.append(event)

    async def run() -> None:
        result = await bootstrap_chat_run(
            **_base_bootstrap_kwargs(
                event_emit=event_emit,
                agent_storage_images=[{"file_id": "img-1", "mime": "image/png"}],
            )
        )
        try:
            assert result.llm_wait_token is token
            assert result.tool_context["agent_storage_images_uploaded"] == 0
            assert result.tool_context["agent_storage_images_pending"] == [
                {"file_id": "img-1", "mime": "image/png"}
            ]
            assert callable(result.tool_context["agent_subagent_notify"])
            assert callable(result.tool_context["deferred_wait_notify"])
            assert callable(captured_notifier["callback"])
        finally:
            _cleanup_bootstrap(result)

    asyncio.run(run())

    assert emitted == []
