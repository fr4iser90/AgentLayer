"""Backward-compatible re-exports — scenarios live in ``scenarios/<id>/``."""

from tests.benchmarks.agent.scenarios.registry import (
    SCENARIO_BY_ID,
    available_prompt_locales,
    discover_scenarios,
    scenarios_for_tier,
)
from tests.benchmarks.agent.scenarios.types import (
    AgentScenario,
    bench_dashboard_title,
    bench_prompt_locale,
    bench_prompt_locale_from_env,
    bench_workspace_name,
    bind_bench_run_prompt_locale,
    render_scenario_prompt,
    reset_bench_run_prompt_locale,
    resolve_prompt_locale,
)

__all__ = [
    "AgentScenario",
    "SCENARIO_BY_ID",
    "available_prompt_locales",
    "bench_dashboard_title",
    "bench_prompt_locale",
    "bench_prompt_locale_from_env",
    "bench_workspace_name",
    "bind_bench_run_prompt_locale",
    "discover_scenarios",
    "render_scenario_prompt",
    "reset_bench_run_prompt_locale",
    "resolve_prompt_locale",
    "scenarios_for_tier",
]
