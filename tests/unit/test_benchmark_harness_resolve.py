"""Unit tests for benchmark harness matrix resolution."""

from __future__ import annotations

from apps.backend.infrastructure.benchmark_harness_resolve import resolve_for_profile


def test_resolve_model_override_beats_global() -> None:
    global_cfg = {
        "harness_preset": "observability",
        "max_tool_rounds_override": 32,
        "scenario_timeout_sec": 600.0,
        "capture_timeline": True,
        "stream_llm": True,
    }
    overrides = [
        {
            "id": "ov-1",
            "catalog_owned_by": "llama_cpp",
            "model": "qwen2.5:3b",
            "harness_preset": "chat_parity",
            "max_tool_rounds_override": 8,
            "scenario_timeout_sec": 180.0,
            "capture_timeline": None,
            "stream_llm": None,
        }
    ]
    eff = resolve_for_profile(
        tenant_id=1,
        catalog_owned_by="llama_cpp",
        model="qwen2.5:3b",
        run_harness_preset="observability",
        matrix=(global_cfg, overrides),
    )
    assert eff.harness_preset == "chat_parity"
    assert eff.max_tool_rounds_override == 8
    assert eff.scenario_timeout_sec == 180.0
    assert eff.source == "model_override"
    assert eff.override_id == "ov-1"


def test_resolve_provider_override_when_no_exact_model() -> None:
    global_cfg = {"harness_preset": "observability", "max_tool_rounds_override": None}
    overrides = [
        {
            "id": "prov-1",
            "catalog_owned_by": "ollama",
            "model": None,
            "harness_preset": "chat_parity",
            "max_tool_rounds_override": 12,
            "scenario_timeout_sec": None,
            "capture_timeline": None,
            "stream_llm": None,
        }
    ]
    eff = resolve_for_profile(
        tenant_id=1,
        catalog_owned_by="ollama",
        model="llama3.2:1b",
        matrix=(global_cfg, overrides),
    )
    assert eff.harness_preset == "chat_parity"
    assert eff.max_tool_rounds_override == 12
    assert eff.source == "provider_override"


def test_resolve_run_fallback_when_matrix_disabled() -> None:
    eff = resolve_for_profile(
        tenant_id=1,
        catalog_owned_by="llama_cpp",
        model="big-model",
        run_harness_preset="chat_parity",
        run_max_tool_rounds_override=6,
        run_scenario_timeout_sec=90.0,
        use_matrix=False,
        matrix=(
            {"harness_preset": "observability", "max_tool_rounds_override": 99},
            [
                {
                    "id": "x",
                    "catalog_owned_by": "llama_cpp",
                    "model": "big-model",
                    "harness_preset": "observability",
                    "max_tool_rounds_override": 1,
                }
            ],
        ),
    )
    assert eff.harness_preset == "chat_parity"
    assert eff.max_tool_rounds_override == 6
    assert eff.scenario_timeout_sec == 90.0
    assert eff.source == "run_fallback"


def test_resolve_global_when_no_override_match() -> None:
    global_cfg = {
        "harness_preset": "observability",
        "max_tool_rounds_override": 24,
        "scenario_timeout_sec": 300.0,
    }
    eff = resolve_for_profile(
        tenant_id=1,
        catalog_owned_by="openai",
        model="gpt-4o",
        matrix=(global_cfg, []),
    )
    assert eff.harness_preset == "observability"
    assert eff.max_tool_rounds_override == 24
    assert eff.scenario_timeout_sec == 300.0
    assert eff.source == "global"
