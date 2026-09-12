"""Tests for the guard rails around an external coding run: workspace, provider, prompt.

An external runtime writes into the user's workspace with no per-call approval, so the
path confinement, the provider hand-off and the task construction are the safety layer.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.backend.application.agent_runtime.use_cases import chat_external_runtime as ext
from apps.backend.infrastructure.platform.config import config


def test_missing_workspace_is_refused() -> None:
    path, error = ext._workspace_path_for_run(None)
    assert path is None
    assert "requires a bound workspace" in (error or "")


def test_workspace_without_server_path_is_refused() -> None:
    path, error = ext._workspace_path_for_run({"id": str(uuid.uuid4())})
    assert path is None
    assert "no server-side path" in (error or "")


def test_client_execution_workspace_is_refused(monkeypatch) -> None:
    from apps.backend.infrastructure.workspace import workspace_execution

    monkeypatch.setattr(workspace_execution, "is_client_execution", lambda raw: True)
    path, error = ext._workspace_path_for_run({"id": str(uuid.uuid4()), "path": "/tmp/whatever"})
    assert path is None
    assert "executes on the client" in (error or "")


def test_workspace_outside_coding_root_is_refused(monkeypatch, tmp_path: Path) -> None:
    inside = tmp_path / "work" / "repo"
    inside.mkdir(parents=True)
    monkeypatch.setattr(config, "CODING_ROOT", tmp_path / "other_root", raising=False)
    path, error = ext._workspace_path_for_run({"id": str(uuid.uuid4()), "path": str(inside)})
    assert path is None
    assert "outside AGENT_CODING_ROOT" in (error or "")


def test_workspace_under_coding_root_is_accepted(monkeypatch, tmp_path: Path) -> None:
    inside = tmp_path / "work" / "repo"
    inside.mkdir(parents=True)
    monkeypatch.setattr(config, "CODING_ROOT", tmp_path / "work", raising=False)
    path, error = ext._workspace_path_for_run({"id": str(uuid.uuid4()), "path": str(inside)})
    assert error is None
    assert path is not None and path.exists()


def test_blocked_path_prefix_is_refused(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "repo").mkdir()
    monkeypatch.setattr(config, "CODING_ROOT", None, raising=False)
    monkeypatch.setattr(config, "CODING_PATH_BLOCKLIST", frozenset({str(tmp_path)}), raising=False)
    path, error = ext._workspace_path_for_run({"id": str(uuid.uuid4()), "path": str(tmp_path / "repo")})
    assert path is None
    assert "blocked for external runtimes" in (error or "")


def test_missing_directory_is_refused(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "CODING_ROOT", None, raising=False)
    monkeypatch.setattr(config, "CODING_PATH_BLOCKLIST", frozenset(), raising=False)
    path, error = ext._workspace_path_for_run({"id": str(uuid.uuid4()), "path": str(tmp_path / "gone")})
    assert path is None
    assert "does not exist" in (error or "")


def _patch_providers(monkeypatch, specs, *, spec_by_id=None) -> None:
    from apps.backend.infrastructure.providers import model_catalog_providers as mcp_mod

    monkeypatch.setattr(mcp_mod, "list_provider_specs", lambda: list(specs))
    monkeypatch.setattr(mcp_mod, "get_provider_spec", lambda pid: (spec_by_id or {}).get(pid))
    monkeypatch.setattr(
        mcp_mod, "resolve_model_for_provider", lambda spec, pk, is_override, raw: "profile-model"
    )


def test_no_provider_configured_is_refused(monkeypatch) -> None:
    _patch_providers(monkeypatch, [])
    base, key, model, error = ext._provider_for_turn(
        catalog_owned_by=None, profile_key="coding", model_resolved=None
    )
    assert error and "no OpenAI-compatible LLM provider" in error
    assert base is None and key is None and model is None


def test_multiple_providers_need_an_explicit_owner(monkeypatch) -> None:
    specs = [
        SimpleNamespace(base_url="https://a.example", api_key="ka"),
        SimpleNamespace(base_url="https://b.example", api_key="kb"),
    ]
    _patch_providers(monkeypatch, specs)
    base, key, model, error = ext._provider_for_turn(
        catalog_owned_by=None, profile_key="coding", model_resolved="m"
    )
    assert base is None
    assert error and "agent_model_catalog_owned_by" in error


def test_provider_without_key_is_refused(monkeypatch) -> None:
    specs = [SimpleNamespace(base_url="https://a.example", api_key="")]
    _patch_providers(monkeypatch, specs)
    _base, _key, _model, error = ext._provider_for_turn(
        catalog_owned_by=None, profile_key="coding", model_resolved="m"
    )
    assert error and "no API key" in error


def test_selected_provider_is_passed_with_openai_v1_base(monkeypatch) -> None:
    chosen = SimpleNamespace(base_url="https://gw.example/v1", api_key="k-selected")
    other = SimpleNamespace(base_url="https://b.example", api_key="kb")
    _patch_providers(monkeypatch, [other, chosen], spec_by_id={"provider_1": chosen})
    monkeypatch.setattr(config, "QWEN_MODEL", None, raising=False)

    base, key, model, error = ext._provider_for_turn(
        catalog_owned_by="provider_1", profile_key="coding", model_resolved="resolved-model"
    )
    assert error == ""
    # Qwen wants the OpenAI-compatible root, which is ``{base}/v1``.
    assert base == "https://gw.example/v1"
    assert key == "k-selected"
    assert model == "resolved-model"


def test_explicit_runtime_model_overrides_the_turn_model(monkeypatch) -> None:
    chosen = SimpleNamespace(base_url="https://gw.example", api_key="k")
    _patch_providers(monkeypatch, [], spec_by_id={"provider_1": chosen})
    monkeypatch.setattr(config, "QWEN_MODEL", "coder-large", raising=False)

    _base, _key, model, error = ext._provider_for_turn(
        catalog_owned_by="provider_1", profile_key="coding", model_resolved="resolved-model"
    )
    assert error == ""
    assert model == "coder-large"


def test_task_is_plain_request_when_session_resumes() -> None:
    messages = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "now rename the module"},
    ]
    assert ext._build_task(messages, resumed=True) == "now rename the module"


def test_first_task_carries_recent_history_as_context() -> None:
    messages = [
        {"role": "user", "content": "how is the repo structured?"},
        {"role": "assistant", "content": "It has apps/ and plugins/."},
        {"role": "user", "content": "add a doc"},
    ]
    task = ext._build_task(messages, resumed=False)
    assert "Conversation so far" in task
    assert "assistant: It has apps/ and plugins/." in task
    assert task.endswith("Current request:\nadd a doc")


def test_task_ignores_tool_messages_and_clips_length() -> None:
    messages = [
        {"role": "tool", "content": "huge tool output " * 100},
        {"role": "user", "content": "x" * 40_000},
    ]
    task = ext._build_task(messages, resumed=True)
    assert len(task) <= ext._MAX_TASK_CHARS
    assert "huge tool output" not in task


def test_change_summary_states_when_there_is_no_repository() -> None:
    assert "No git repository" in ext._change_summary({"no_vcs": True}, [])


def test_change_summary_lists_touched_paths() -> None:
    summary = ext._change_summary({"no_vcs": False, "diff_stat": " 1 file changed"}, ["a.py"])
    assert "1 path(s) touched: a.py" in summary
    assert "1 file changed" in summary
