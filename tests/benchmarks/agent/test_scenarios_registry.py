"""Tests for per-directory scenario registry."""

from __future__ import annotations

from tests.benchmarks.agent.cases import (
    SCENARIO_BY_ID,
    bench_prompt_locale,
    bind_bench_run_prompt_locale,
    render_scenario_prompt,
    reset_bench_run_prompt_locale,
)
from tests.benchmarks.agent.fixtures import FixtureContext
from tests.benchmarks.agent.scenarios.registry import discover_scenarios


def test_discover_all_fourteen_scenarios():
    scenarios = discover_scenarios()
    assert len(scenarios) == 14
    assert set(SCENARIO_BY_ID) == {s.id for s in scenarios}


def test_each_scenario_has_en_and_de_prompts():
    for sc in SCENARIO_BY_ID.values():
        assert "en" in sc.prompts, sc.id
        assert "de" in sc.prompts, sc.id
        assert sc.source_dir is not None
        assert (sc.source_dir / "meta.yaml").is_file()


def test_render_scenario_prompt_replaces_prefix():
    token = bind_bench_run_prompt_locale("en")
    try:
        sc = SCENARIO_BY_ID["C1_bench_marker_file"]
        ctx = FixtureContext(run_id="r1", prefix="bench-r1-")
        out = render_scenario_prompt(sc, ctx)
        assert "bench-r1-coding" in out
        assert "{prefix}" not in out
    finally:
        reset_bench_run_prompt_locale(token)


def test_render_scenario_prompt_german_locale():
    token = bind_bench_run_prompt_locale("de")
    try:
        sc = SCENARIO_BY_ID["S2_simple_chat"]
        ctx = FixtureContext(run_id="r1", prefix="bench-r1-")
        out = render_scenario_prompt(sc, ctx)
        assert "17 + 25" in out
        assert "numerischen" in out
    finally:
        reset_bench_run_prompt_locale(token)


def test_bench_prompt_locale_defaults_to_en():
    assert bench_prompt_locale() == "en"
