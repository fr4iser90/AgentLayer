"""Tests for per-directory scenario registry."""

from __future__ import annotations

from tests.benchmarks.agent.cases import (
    SCENARIO_BY_ID,
    bench_prompt_locale,
    bind_bench_run_prompt_variant,
    bind_bench_run_prompt_locale,
    render_scenario_prompt,
    reset_bench_run_prompt_locale,
    reset_bench_run_prompt_variant,
)
from tests.benchmarks.agent.fixtures import FixtureContext
from tests.benchmarks.agent.scenarios.registry import discover_scenarios
from tests.benchmarks.agent.catalog import catalog_payload


def test_discover_all_nineteen_scenarios():
    scenarios = discover_scenarios()
    assert len(scenarios) == 19
    assert set(SCENARIO_BY_ID) == {s.id for s in scenarios}


def test_each_scenario_has_en_and_de_prompts():
    for sc in SCENARIO_BY_ID.values():
        assert "en" in sc.prompts, sc.id
        assert "de" in sc.prompts, sc.id
        assert sc.source_dir is not None
        assert (sc.source_dir / "meta.yaml").is_file()
        assert (sc.source_dir / "prompt.en.md").is_file()
        assert (sc.source_dir / "prompt.de.md").is_file()


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
        assert "Frankreich" in out
        assert "Hauptstadt" in out
    finally:
        reset_bench_run_prompt_locale(token)


def test_realistic_prompt_variant_falls_back_to_canonical():
    locale_token = bind_bench_run_prompt_locale("en")
    variant_token = bind_bench_run_prompt_variant("realistic")
    try:
        sc = SCENARIO_BY_ID["S1_tool_catalog"]
        ctx = FixtureContext(run_id="r1", prefix="bench-r1-")
        out = render_scenario_prompt(sc, ctx)
        assert out == sc.prompts["en"]
    finally:
        reset_bench_run_prompt_variant(variant_token)
        reset_bench_run_prompt_locale(locale_token)


def test_catalog_exposes_prompt_variants():
    payload = catalog_payload()
    assert "canonical" in payload["available_prompt_variants"]
    assert "realistic" in payload["available_prompt_variants"]
    first = payload["scenarios"][0]
    assert "prompts_by_variant" in first
    assert "canonical" in first["prompts_by_variant"]


def test_bench_prompt_locale_defaults_to_en():
    assert bench_prompt_locale() == "en"


def test_s2_uses_plain_completion():
    sc = SCENARIO_BY_ID["S2_simple_chat"]
    assert sc.plain_completion is True


def test_s4_delegate_math_tier_two():
    sc = SCENARIO_BY_ID["S4_delegate_math"]
    assert sc.tier == 2
    assert sc.plain_completion is False
