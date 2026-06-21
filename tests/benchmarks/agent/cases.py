"""Backward-compatible re-exports — scenarios live in ``scenarios/<id>/``."""

from tests.benchmarks.agent.scenarios.registry import (
    SCENARIO_BY_ID,
    available_prompt_locales,
    available_prompt_variants,
    discover_scenarios,
    scenarios_for_tier,
)
from tests.benchmarks.agent.scenarios.types import (
    AgentScenario,
    bench_dashboard_title,
    bench_prompt_locale,
    bench_prompt_locale_from_env,
    bench_prompt_variant,
    bench_prompt_variant_from_env,
    bench_workspace_name,
    bind_bench_run_prompt_locale,
    bind_bench_run_prompt_variant,
    normalize_prompt_variant,
    render_scenario_prompt,
    reset_bench_run_prompt_locale,
    reset_bench_run_prompt_variant,
    resolve_prompt_locale,
    resolve_prompt_variant,
)

__all__ = [
    "AgentScenario",
    "SCENARIO_BY_ID",
    "available_prompt_locales",
    "available_prompt_variants",
    "bench_dashboard_title",
    "bench_prompt_locale",
    "bench_prompt_locale_from_env",
    "bench_prompt_variant",
    "bench_prompt_variant_from_env",
    "bench_workspace_name",
    "bind_bench_run_prompt_locale",
    "bind_bench_run_prompt_variant",
    "discover_scenarios",
    "normalize_prompt_variant",
    "render_scenario_prompt",
    "reset_bench_run_prompt_locale",
    "reset_bench_run_prompt_variant",
    "resolve_prompt_locale",
    "resolve_prompt_variant",
    "scenarios_for_tier",
]
