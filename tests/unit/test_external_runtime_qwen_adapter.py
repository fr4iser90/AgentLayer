"""Tests for the Qwen Code adapter: availability, option mapping, events, cancel, timeout.

The SDK is optional in production and absent in CI, so every test injects a fake
``qwen_code_sdk`` module — exactly the lazy-import seam the adapter uses.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from pathlib import Path

from apps.backend.domain.agent_runtime.external_runtime import (
    ExternalRunRequest,
    available_external_runtimes,
    register_external_runtime,
    unregister_external_runtime,
)
from apps.backend.infrastructure.agent_runtime.external_runtimes import qwen_code
from apps.backend.infrastructure.agent_runtime.external_runtimes.qwen_code import QwenCodeRuntime
from apps.backend.infrastructure.platform.config import config

_MESSAGES = [
    {"type": "system", "subtype": "init", "session_id": "qwen-sess-1"},
    {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "Reading the repo. "},
                {"type": "tool_use", "id": "t1", "name": "edit_file", "input": {"path": "a.py"}},
            ]
        },
    },
    {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "patched"}]},
    },
    {
        "type": "result",
        "result": "Added type hints to a.py.",
        "is_error": False,
        "session_id": "qwen-sess-1",
        "usage": {"input_tokens": 120, "output_tokens": 34},
    },
]


class _FakeStream:
    """Stand-in for the SDK's ``Query`` object: async iterator + interrupt/close hooks."""

    def __init__(self, messages, *, first_delay: float = 0.0) -> None:
        self._messages = list(messages)
        self._index = 0
        self.first_delay = first_delay
        self.interrupt_calls = 0
        self.sync_close_calls = 0
        self.close_calls = 0
        self.options_seen: dict = {}

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> dict:
        if self.first_delay:
            await asyncio.sleep(self.first_delay)
        if self.interrupt_calls or self._index >= len(self._messages):
            raise StopAsyncIteration
        message = self._messages[self._index]
        self._index += 1
        return message

    def interrupt(self) -> None:
        self.interrupt_calls += 1

    def close(self) -> None:
        # The SDK exposes a sync close() on Query; the adapter must call it during cancel.
        self.sync_close_calls += 1

    async def aclose(self) -> None:
        self.close_calls += 1


def _install_fake_sdk(monkeypatch, stream: _FakeStream) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []

    def query(prompt: str, options: dict) -> _FakeStream:
        calls.append((prompt, options))
        stream.options_seen = options
        return stream

    module = types.ModuleType("qwen_code_sdk")
    module.query = query  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "qwen_code_sdk", module)
    return calls


def _request(tmp_path: Path, **overrides) -> ExternalRunRequest:
    base = {
        "task": "add type hints",
        "workspace_path": str(tmp_path),
        "agent_id": "coding_qwen",
        "runtime_id": "qwen_code",
        "model": "Qwen3.6-35B",
        "base_url": "https://llm.example/v1",
        "api_key": "sk-secret-value",
        "timeout_sec": 30,
        "conversation_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
    }
    base.update(overrides)
    return ExternalRunRequest(**base)


def _enable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "QWEN_RUNTIME_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_ALLOW_YOLO", False, raising=False)
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_HOME", str(tmp_path / "runtimes"), raising=False)
    monkeypatch.setattr(config, "QWEN_MODEL", None, raising=False)
    monkeypatch.setattr(config, "QWEN_PERMISSION_MODE", "auto-edit", raising=False)
    monkeypatch.setattr(config, "QWEN_EXCLUDE_TOOLS", (), raising=False)
    # A real file on disk: the adapter checks the resolved path, not just ``PATH``.
    fake_bin = tmp_path / "bin" / "qwen"
    fake_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_bin.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(qwen_code.shutil, "which", lambda name: str(fake_bin))


def test_available_reports_missing_binary(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(qwen_code.shutil, "which", lambda name: None)
    usable, reason = QwenCodeRuntime().available()
    assert usable is False
    assert "qwen binary not found" in reason


def test_available_reports_missing_sdk(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, "qwen_code_sdk", None)
    usable, reason = QwenCodeRuntime().available()
    assert usable is False
    assert "qwen-code-sdk not importable" in reason


def test_available_when_binary_and_sdk_present(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, "qwen_code_sdk", types.ModuleType("qwen_code_sdk"))
    assert QwenCodeRuntime().available() == (True, "")


def test_run_requires_provider_credentials(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    _install_fake_sdk(monkeypatch, _FakeStream(_MESSAGES))

    async def _drive() -> object:
        async def emit(_event) -> None:
            return None

        return await QwenCodeRuntime().run(
            _request(tmp_path, api_key=None), emit=emit, cancel_event=None
        )

    result = asyncio.run(_drive())
    assert result.ok is False
    assert "no OpenAI-compatible provider credentials" in (result.error or "")


def test_run_maps_options_events_and_result(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    stream = _FakeStream(_MESSAGES)
    calls = _install_fake_sdk(monkeypatch, stream)
    kinds: list[str] = []
    payload_seen: dict = {}

    async def _drive():
        async def emit(event) -> None:
            kinds.append(event.kind)
            if event.session_id:
                payload_seen["session_id"] = event.session_id

        return await QwenCodeRuntime().run(
            _request(tmp_path, max_turns=12, resume_session_id="qwen-sess-0", exclude_tools=("webFetch",)),
            emit=emit,
            cancel_event=asyncio.Event(),
        )

    result = asyncio.run(_drive())

    prompt, options = calls[0]
    assert prompt == "add type hints"
    assert options["cwd"] == str(tmp_path)
    assert options["model"] == "Qwen3.6-35B"
    assert options["permission_mode"] == "auto-edit"
    assert options["max_session_turns"] == 12
    assert options["resume"] == "qwen-sess-0"
    assert options["exclude_tools"] == ["webFetch"]
    assert options["env"]["OPENAI_BASE_URL"] == "https://llm.example/v1"

    assert kinds == ["status", "delta", "tool_call", "tool_result"]
    assert result.ok is True
    assert result.text == "Added type hints to a.py."
    assert result.session_id == "qwen-sess-1"
    assert result.usage == {"input_tokens": 120, "output_tokens": 34}
    assert stream.close_calls == 1


def test_run_writes_private_qwen_settings_for_provider_passthrough(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    _install_fake_sdk(monkeypatch, _FakeStream(_MESSAGES))
    request = _request(tmp_path)

    async def _drive() -> None:
        async def emit(_event) -> None:
            return None

        await QwenCodeRuntime().run(request, emit=emit, cancel_event=None)

    asyncio.run(_drive())

    settings_path = (
        tmp_path / "runtimes" / "qwen" / request.user_id / request.conversation_id / ".qwen" / "settings.json"
    )
    assert settings_path.is_file()
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["security"]["auth"]["selectedType"] == "openai"
    provider = settings["modelProviders"]["openai"][0]
    assert provider["id"] == "Qwen3.6-35B"
    assert provider["baseUrl"] == "https://llm.example/v1"
    assert provider["envKey"] == "OPENAI_API_KEY"
    assert settings["model"]["name"] == "Qwen3.6-35B"
    # The key itself lives in the child env only, never in the settings file.
    assert "sk-secret-value" not in settings_path.read_text(encoding="utf-8")


def test_child_env_is_curated_not_a_copy_of_the_backend(monkeypatch, tmp_path: Path, caplog) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SECRETS_MASTER_KEY", "master-key-must-not-leak")
    monkeypatch.setenv("PGPASSWORD", "db-pass-must-not-leak")
    _install_fake_sdk(monkeypatch, _FakeStream(_MESSAGES))

    env = qwen_code._child_env(
        _request(tmp_path, env={"GITHUB_TOKEN": "ghu-bound-secret"}),
        run_home=tmp_path / "home",
        api_key="sk-secret-value",
    )
    assert env["HOME"] == str(tmp_path / "home")
    assert env["OPENAI_API_KEY"] == "sk-secret-value"
    assert env["GITHUB_TOKEN"] == "ghu-bound-secret"
    assert "AGENT_SECRETS_MASTER_KEY" not in env
    assert "PGPASSWORD" not in env


def test_yolo_needs_the_operator_ceiling(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "QWEN_PERMISSION_MODE", "yolo", raising=False)
    stream = _FakeStream(_MESSAGES)
    calls = _install_fake_sdk(monkeypatch, stream)

    async def _drive() -> None:
        async def emit(_event) -> None:
            return None

        await QwenCodeRuntime().run(_request(tmp_path), emit=emit, cancel_event=None)

    asyncio.run(_drive())
    assert calls[0][1]["permission_mode"] == "auto-edit"

    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_ALLOW_YOLO", True, raising=False)
    calls.clear()
    asyncio.run(_drive())
    assert calls[0][1]["permission_mode"] == "yolo"


def test_catalog_advertises_the_mode_the_run_will_use(monkeypatch, tmp_path: Path) -> None:
    """A client offers or hides the entry from this number — advertising ``auto-edit``
    while the operator configured ``plan`` would misrepresent what the run may do."""
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "EXTERNAL_RUNTIME_ALLOW_YOLO", False, raising=False)
    monkeypatch.setattr(config, "QWEN_PERMISSION_MODE", "plan", raising=False)

    runtime = QwenCodeRuntime()
    register_external_runtime(runtime)
    try:
        assert runtime.default_permission_mode == "plan"
        catalog = next(row for row in available_external_runtimes() if row["id"] == QwenCodeRuntime.id)
        assert catalog["default_permission_mode"] == "plan"

        # The ceiling outranks the vendor default, in the catalog as well as in run().
        monkeypatch.setattr(config, "QWEN_PERMISSION_MODE", "yolo", raising=False)
        assert runtime.default_permission_mode == "auto-edit"
    finally:
        unregister_external_runtime(QwenCodeRuntime.id)


def test_cancel_event_stops_run(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    stream = _FakeStream(_MESSAGES)
    _install_fake_sdk(monkeypatch, stream)
    cancel = asyncio.Event()
    cancel.set()

    async def _drive():
        async def emit(_event) -> None:
            return None

        return await QwenCodeRuntime().run(_request(tmp_path), emit=emit, cancel_event=cancel)

    result = asyncio.run(_drive())
    assert result.ok is False
    assert result.error == "cancelled"


def test_watch_cancel_interrupts_then_closes(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    stream = _FakeStream(_MESSAGES)

    async def _drive() -> None:
        cancel = asyncio.Event()
        watcher = asyncio.create_task(qwen_code._watch_cancel(cancel, stream))
        cancel.set()
        await watcher

    asyncio.run(_drive())
    assert stream.interrupt_calls == 1
    assert stream.sync_close_calls == 1


def test_timeout_returns_error_instead_of_hanging(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    stream = _FakeStream(_MESSAGES, first_delay=2.0)
    _install_fake_sdk(monkeypatch, stream)

    async def _drive():
        async def emit(_event) -> None:
            return None

        return await QwenCodeRuntime().run(_request(tmp_path, timeout_sec=1), emit=emit, cancel_event=None)

    result = asyncio.run(_drive())
    assert result.ok is False
    assert "exceeded 1s" in (result.error or "")


def test_error_result_is_reported_with_text_from_vendor(monkeypatch, tmp_path: Path) -> None:
    _enable(monkeypatch, tmp_path)
    messages = [{"type": "result", "is_error": True, "error": {"message": "upstream 502"}, "result": ""}]
    _install_fake_sdk(monkeypatch, _FakeStream(messages))

    async def _drive():
        async def emit(_event) -> None:
            return None

        return await QwenCodeRuntime().run(_request(tmp_path), emit=emit, cancel_event=None)

    result = asyncio.run(_drive())
    assert result.ok is False
    assert "upstream 502" in (result.error or "")
