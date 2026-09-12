"""Tests for the chat-turn seam: an agent with ``external_runtime`` bypasses the tool loop.

These drive ``maybe_run_external_runtime_turn`` — the only thing ``chat_completion`` calls
at its branch point — with a fake runtime, so the contract the caller relies on
(completion dict, streamed events, cancellation, audit, session resume) is pinned without
a vendor binary or a database.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from apps.backend.application.agent_runtime.use_cases import chat_external_runtime as ext
from apps.backend.application.agent_runtime.runtime.prompts import AgentChatCancelled
from apps.backend.domain.agent_runtime.external_runtime import (
    ExternalRunRequest,
    ExternalRunResult,
    ExternalRuntimeEvent,
)
from apps.backend.infrastructure.platform.config import config


class _StubRuntime:
    id = "stub_runtime"
    supports_resume = True
    supports_write = True
    default_permission_mode = "auto-edit"

    def __init__(self, result: ExternalRunResult) -> None:
        self.result = result
        self.requests: list[ExternalRunRequest] = []

    def available(self) -> tuple[bool, str]:
        return (True, "")

    async def run(self, request, *, emit, cancel_event=None) -> ExternalRunResult:
        self.requests.append(request)
        await emit(ExternalRuntimeEvent(kind="delta", text="working…"))
        await emit(ExternalRuntimeEvent(kind="tool_call", tool="write_file", args_preview="b.py"))
        await emit(ExternalRuntimeEvent(kind="tool_result", tool="write_file", text="written"))
        return self.result


def _wire(
    monkeypatch,
    tmp_path: Path,
    runtime: Any,
    *,
    stored: tuple[str | None, str | None] = (None, None),
    audit_calls: list[dict] | None = None,
    stored_writes: list[dict] | None = None,
) -> dict[str, Any]:
    """Point the use case at a fake runtime, provider, store and audit sink."""
    monkeypatch.setattr(ext, "external_runtime_id_for_agent", lambda agent_id: "stub_runtime")
    monkeypatch.setattr(ext, "resolve_external_runtime", lambda runtime_id: (runtime, ""))
    monkeypatch.setattr(
        ext,
        "_provider_for_turn",
        lambda **_kw: ("https://llm.example/v1", "sk-test", "Qwen3.6-35B", ""),
    )
    monkeypatch.setattr(ext, "_workspace_secret_env", lambda ws_path, user_id: {"BOUND_TOKEN": "s3cret"})

    from apps.backend.infrastructure.agent_runtime import conversation_external_session_store as store

    monkeypatch.setattr(store, "get_conversation_external_session", lambda user_id, cid: stored)
    if stored_writes is not None:

        def _write(user_id, cid, *, runtime, session_id):
            stored_writes.append({"runtime": runtime, "session_id": session_id})
            return True

        monkeypatch.setattr(store, "set_conversation_external_session", _write)

    from apps.backend.infrastructure.db import db

    if audit_calls is not None:
        monkeypatch.setattr(
            db,
            "log_tool_invocation",
            lambda tool_name, args, result_text, ok, *, agent_run_id=None: audit_calls.append(
                {"tool_name": tool_name, "args": args, "ok": ok}
            ),
        )
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_MAX_TURNS", 7, raising=False)
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_TIMEOUT_SEC", 1234, raising=False)

    return {"workspace": {"id": str(uuid.uuid4()), "path": str(tmp_path)}}


def _call(
    *,
    workspace: dict[str, Any],
    conversation_id: uuid.UUID | None = uuid.uuid4(),
    messages: list[dict[str, Any]] | None = None,
    event_sink: list[dict] | None = None,
    cancel_event: asyncio.Event | None = None,
):
    async def _emit(payload: dict) -> None:
        if event_sink is not None:
            event_sink.append(payload)

    async def _run():
        return await ext.maybe_run_external_runtime_turn(
            agent_id="coding_qwen",
            messages=messages
            or [
                {"role": "user", "content": "previous question"},
                {"role": "assistant", "content": "previous answer"},
                {"role": "user", "content": "add type hints to the module"},
            ],
            workspace=workspace,
            model="Qwen3.6-35B",
            profile_key="coding",
            catalog_owned_by="provider_1",
            agent_run_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            user_id=uuid.uuid4(),
            event_emit=_emit,
            cancel_event=cancel_event,
            agent_prompt="Do the work.",
        )

    return asyncio.run(_run())


def test_external_turn_returns_completion_and_streams_events(monkeypatch, tmp_path: Path) -> None:
    runtime = _StubRuntime(ExternalRunResult(ok=True, text="Done. Tests pass.", session_id="sess-1"))
    ctx = _wire(monkeypatch, tmp_path, runtime)
    events: list[dict] = []

    completion = _call(workspace=ctx["workspace"], event_sink=events)

    assert completion["object"] == "chat.completion"
    assert completion["choices"][0]["message"]["content"] == "Done. Tests pass."
    meta = completion["agentlayer_context"]
    assert meta["external_runtime"] == "stub_runtime"
    assert meta["external_ok"] is True
    assert meta["external_resumed"] is False

    types_emitted = [e["type"] for e in events]
    assert "agent.llm_delta" in types_emitted
    assert "agent.tool_start" in types_emitted and "agent.tool_done" in types_emitted
    # The client refreshes the git-diff panel on agent.done, so an external run must emit it.
    assert types_emitted[-1] == "agent.done"
    assert events[-1]["kind"] == "final_text"


def test_external_turn_passes_task_prompt_and_limits(monkeypatch, tmp_path: Path) -> None:
    runtime = _StubRuntime(ExternalRunResult(ok=True, text="ok"))
    ctx = _wire(monkeypatch, tmp_path, runtime)

    _call(workspace=ctx["workspace"])

    request = runtime.requests[0]
    assert request.runtime_id == "stub_runtime"
    assert request.model == "Qwen3.6-35B"
    assert request.base_url == "https://llm.example/v1"
    assert request.permission_mode == "auto-edit"
    assert request.max_turns == 7
    assert request.timeout_sec == 1234
    assert request.append_system_prompt == "Do the work."
    assert request.env == {"BOUND_TOKEN": "s3cret"}
    assert request.task.endswith("add type hints to the module")
    # First turn of a conversation carries the earlier discussion as context.
    assert "Conversation so far" in request.task


def test_external_turn_resumes_stored_vendor_session(monkeypatch, tmp_path: Path) -> None:
    runtime = _StubRuntime(ExternalRunResult(ok=True, text="ok", session_id="sess-9"))
    writes: list[dict] = []
    ctx = _wire(monkeypatch, tmp_path, runtime, stored=("stub_runtime", "sess-9"), stored_writes=writes)

    completion = _call(workspace=ctx["workspace"])

    assert runtime.requests[0].resume_session_id == "sess-9"
    assert runtime.requests[0].task == "add type hints to the module"
    assert completion["agentlayer_context"]["external_resumed"] is True
    assert writes == [{"runtime": "stub_runtime", "session_id": "sess-9"}]


def test_external_turn_audits_run_with_changed_files(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)

    class _WritingRuntime(_StubRuntime):
        async def run(self, request, *, emit, cancel_event=None):
            (Path(request.workspace_path) / "b.py").write_text("y = 2\n", encoding="utf-8")
            return await super().run(request, emit=emit, cancel_event=cancel_event)

    audits: list[dict] = []
    runtime = _WritingRuntime(ExternalRunResult(ok=True, text="added b.py"))
    ctx = _wire(monkeypatch, tmp_path / "unused", runtime, audit_calls=audits)
    ctx["workspace"] = {"id": str(uuid.uuid4()), "path": str(repo)}

    completion = _call(workspace=ctx["workspace"])

    assert audits and audits[0]["tool_name"] == "external_runtime.run"
    assert audits[0]["ok"] is True
    assert "b.py" in audits[0]["args"]["changed_files"]
    assert completion["agentlayer_context"]["external_changed_files"] == ["b.py"]
    assert completion["agentlayer_context"]["external_no_vcs"] is False


def test_cancelled_external_run_raises_chat_cancelled(monkeypatch, tmp_path: Path) -> None:
    runtime = _StubRuntime(ExternalRunResult(ok=False, error="cancelled"))
    ctx = _wire(monkeypatch, tmp_path, runtime)

    with pytest.raises(AgentChatCancelled):
        _call(workspace=ctx["workspace"])


def test_unavailable_runtime_fails_loudly_without_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ext, "external_runtime_id_for_agent", lambda agent_id: "stub_runtime")
    monkeypatch.setattr(ext, "resolve_external_runtime", lambda runtime_id: (None, "qwen binary not found"))
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_FALLBACK_INTERNAL", False, raising=False)

    with pytest.raises(ValueError, match="qwen binary not found"):
        _call(workspace={"id": str(uuid.uuid4()), "path": str(tmp_path)})


def test_unavailable_runtime_falls_back_when_operator_allows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ext, "external_runtime_id_for_agent", lambda agent_id: "stub_runtime")
    monkeypatch.setattr(ext, "resolve_external_runtime", lambda runtime_id: (None, "binary missing"))
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_FALLBACK_INTERNAL", True, raising=False)

    # ``None`` means "continue with AgentLayer's own planner loop".
    assert _call(workspace={"id": str(uuid.uuid4()), "path": str(tmp_path)}) is None


def test_agent_without_external_runtime_is_left_alone(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ext, "external_runtime_id_for_agent", lambda agent_id: None)

    assert _call(workspace={"id": str(uuid.uuid4()), "path": str(tmp_path)}) is None


def test_two_runs_in_one_conversation_are_refused(monkeypatch, tmp_path: Path) -> None:
    """Two vendor sessions editing one workspace at the same time would fight each other."""
    waiter = asyncio.Event()
    gate = asyncio.Event()

    class _HoldingRuntime(_StubRuntime):
        async def run(self, request, *, emit, cancel_event=None):
            self.requests.append(request)
            waiter.set()
            await gate.wait()
            return ExternalRunResult(ok=True, text="first")

    runtime = _HoldingRuntime(ExternalRunResult(ok=True, text="first"))
    ctx = _wire(monkeypatch, tmp_path, runtime)
    workspace = ctx["workspace"]
    cid = uuid.uuid4()

    def _turn(content: str):
        return ext.maybe_run_external_runtime_turn(
            agent_id="coding_qwen",
            messages=[{"role": "user", "content": content}],
            workspace=workspace,
            model="m",
            profile_key="coding",
            catalog_owned_by="provider_1",
            agent_run_id=str(uuid.uuid4()),
            conversation_id=cid,
            user_id=uuid.uuid4(),
            event_emit=None,
            cancel_event=None,
        )

    async def _scenario() -> None:
        first = asyncio.create_task(_turn("task one"))
        await asyncio.wait_for(waiter.wait(), timeout=5)

        with pytest.raises(ValueError, match="already has an external run in progress"):
            await _turn("task two")

        gate.set()
        assert (await first) is not None

    asyncio.run(_scenario())
