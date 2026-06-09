"""Unit tests for AGENT_BENCH_LLM_* profile parsing."""

from __future__ import annotations

import os

import pytest

from tests.benchmarks.agent.bench_profiles import parse_profiles_from_env, profile_labels_filter


def test_parse_profiles_from_env_numbered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_BENCH_LLM_1_BASE_URL", "http://10.0.0.5:11434")
    monkeypatch.setenv("AGENT_BENCH_LLM_1_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("AGENT_BENCH_LLM_1_LABEL", "ollama-remote")
    monkeypatch.setenv("AGENT_BENCH_LLM_1_API_KEY", "secret")
    monkeypatch.setenv("AGENT_BENCH_LLM_1_API_HEADER_NAME", "X-API-KEY")
    monkeypatch.delenv("AGENT_BENCH_LLM_2_BASE_URL", raising=False)
    monkeypatch.delenv("AGENT_BENCH_LLM_2_CATALOG", raising=False)
    rows = parse_profiles_from_env()
    assert len(rows) == 1
    assert rows[0].base_url == "http://10.0.0.5:11434"
    assert rows[0].api_key == "secret"
    assert rows[0].api_header_name == "X-API-KEY"
    assert rows[0].slot == 1


def test_profile_by_env_slot_and_admin_serialize(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.benchmarks.agent.bench_profiles import (
        profile_by_env_slot,
        serialize_env_profiles_for_admin,
    )

    monkeypatch.setenv("AGENT_BENCH_LLM_1_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("AGENT_BENCH_LLM_1_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("AGENT_BENCH_LLM_1_LABEL", "ollama-local")
    serialized = serialize_env_profiles_for_admin()
    assert len(serialized) == 1
    assert serialized[0]["slot"] == 1
    assert serialized[0]["label"] == "ollama-local"
    assert serialized[0]["api_key_configured"] is False
    assert "api_key" not in serialized[0]
    prof = profile_by_env_slot(1)
    assert prof is not None
    assert prof.label == "ollama-local"
    assert profile_by_env_slot(99) is None


def test_profile_labels_filter() -> None:
    os.environ["AGENT_BENCH_PROFILES"] = "a, b"
    try:
        assert profile_labels_filter() == ["a", "b"]
    finally:
        os.environ.pop("AGENT_BENCH_PROFILES", None)
