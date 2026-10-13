"""Tests for the external agent runtime port: registry, permission clamp, event mapping."""

from __future__ import annotations

import asyncio

from apps.backend.domain.agent_runtime.external_runtime import (
    ExternalRunRequest,
    ExternalRunResult,
    ExternalRuntimeEvent,
    available_external_runtimes,
    clamp_permission_mode,
    register_external_runtime,
    resolve_external_runtime,
    unregister_external_runtime,
)
from apps.backend.domain.agent_runtime.external_runtime_events import ExternalEventTranslator


class _FakeRuntime:
    id = "fake_runtime"
    supports_resume = False
    supports_write = True
    default_permission_mode = "auto-edit"

    def __init__(self, *, usable: bool = True, reason: str = "") -> None:
        self.usable = usable
        self.reason = reason
        self.requests: list[ExternalRunRequest] = []

    def available(self) -> tuple[bool, str]:
        return (self.usable, self.reason)

    async def run(self, request, *, emit, cancel_event=None) -> ExternalRunResult:
        self.requests.append(request)
        await emit(ExternalRuntimeEvent(kind="delta", text="hello"))
        return ExternalRunResult(ok=True, text="hello", session_id="s-1")


def test_resolve_unknown_runtime_explains_registry() -> None:
    runtime, reason = resolve_external_runtime("nope")
    assert runtime is None
    assert "unknown external_runtime" in reason


def test_resolve_empty_runtime_id() -> None:
    runtime, reason = resolve_external_runtime("")
    assert runtime is None
    assert "no external_runtime declared" in reason


def test_resolve_unavailable_runtime_returns_reason() -> None:
    runtime = _FakeRuntime(usable=False, reason="binary missing")
    register_external_runtime(runtime)
    try:
        got, reason = resolve_external_runtime("fake_runtime")
        assert got is None
        assert "binary missing" in reason
    finally:
        unregister_external_runtime("fake_runtime")


def test_catalog_lists_runtimes_without_raising() -> None:
    class _Broken:
        id = "broken_runtime"
        supports_resume = False
        supports_write = False
        default_permission_mode = "plan"

        def available(self) -> tuple[bool, str]:
            raise RuntimeError("probe exploded")

        async def run(self, request, *, emit, cancel_event=None) -> ExternalRunResult:
            return ExternalRunResult(ok=False)

    register_external_runtime(_Broken())
    register_external_runtime(_FakeRuntime())
    try:
        catalog = {row["id"]: row for row in available_external_runtimes()}
        assert catalog["fake_runtime"]["available"] is True
        # A broken probe must degrade to unavailable, never propagate.
        assert catalog["broken_runtime"]["available"] is False
        assert "probe exploded" in catalog["broken_runtime"]["reason"]
    finally:
        unregister_external_runtime("broken_runtime")
        unregister_external_runtime("fake_runtime")


def test_permission_mode_never_exceeds_ceiling() -> None:
    assert clamp_permission_mode("yolo", "auto-edit") == "auto-edit"
    assert clamp_permission_mode("auto-edit", "yolo") == "auto-edit"
    assert clamp_permission_mode("plan", "auto-edit") == "plan"
    assert clamp_permission_mode("nonsense", "yolo") == "auto-edit"


def test_translator_maps_delta_and_tool_pair() -> None:
    tr = ExternalEventTranslator("run-1")
    assert tr.translate(ExternalRuntimeEvent(kind="delta", text="working")) == [
        {"type": "agent.llm_delta", "agent_run_id": "run-1", "round": 0, "delta": "working"}
    ]
    start = tr.translate(ExternalRuntimeEvent(kind="tool_call", tool="edit", args_preview='{"path":"a.py"}'))
    assert start[0]["type"] == "agent.tool_start"
    assert start[0]["name"] == "edit"
    assert start[0]["step_label"] == "edit #1"
    assert start[0]["summary"] == '{"path":"a.py"}'

    done = tr.translate(ExternalRuntimeEvent(kind="tool_result", tool="edit", text="ok", ok=True))
    assert done[0]["type"] == "agent.tool_done"
    assert done[0]["result_ok"] is True
    assert done[0]["result_display"] == "ok"
    assert tr.round == 1


def test_translator_labels_are_unique_per_call_for_duration_pairing() -> None:
    # The client pairs tool durations by tool *name*, so repeated calls need distinct labels.
    tr = ExternalEventTranslator("run-1")
    labels = []
    for _ in range(3):
        labels.append(tr.translate(ExternalRuntimeEvent(kind="tool_call", tool="shell"))[0]["step_label"])
        tr.translate(ExternalRuntimeEvent(kind="tool_result", tool="shell", text="ok"))
    assert labels == ["shell #1", "shell #2", "shell #3"]
    assert len(set(labels)) == 3


def test_translator_marks_failed_tool_result() -> None:
    tr = ExternalEventTranslator("run-1")
    tr.translate(ExternalRuntimeEvent(kind="tool_call", tool="shell"))
    done = tr.translate(ExternalRuntimeEvent(kind="tool_result", tool="shell", text="boom", ok=False))
    assert done[0]["result_ok"] is False
    assert "boom" in done[0]["result_error"]


def test_translator_ignores_log_only_kinds() -> None:
    tr = ExternalEventTranslator("run-1")
    assert tr.translate(ExternalRuntimeEvent(kind="status", text="session started")) == []
    assert tr.translate(ExternalRuntimeEvent(kind="done", text="finished")) == []
    assert tr.translate(ExternalRuntimeEvent(kind="error", error="nope")) == []
    assert tr.translate(ExternalRuntimeEvent(kind="delta", text="")) == []


def test_registered_runtime_is_drivable_through_the_port() -> None:
    runtime = _FakeRuntime()
    register_external_runtime(runtime)

    async def _drive() -> tuple[ExternalRunResult, list[str]]:
        got, reason = resolve_external_runtime("fake_runtime")
        assert got is runtime and reason == ""
        seen: list[str] = []

        async def emit(event: ExternalRuntimeEvent) -> None:
            seen.append(event.kind)

        result = await got.run(
            ExternalRunRequest(task="do it", workspace_path="/tmp", agent_id="a", runtime_id="fake_runtime"),
            emit=emit,
            cancel_event=asyncio.Event(),
        )
        return result, seen

    try:
        result, kinds = asyncio.run(_drive())
        assert result.ok and result.text == "hello" and result.session_id == "s-1"
        assert kinds == ["delta"]
        assert runtime.requests[0].task == "do it"
    finally:
        unregister_external_runtime("fake_runtime")
