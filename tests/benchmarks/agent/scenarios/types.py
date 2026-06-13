"""Agent benchmark scenario types and prompt rendering."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path

from tests.benchmarks.agent.fixtures import FixtureContext
from tests.benchmarks.agent.scenarios._env import resolve_env_placeholders

_bench_run_prompt_locale: ContextVar[str | None] = ContextVar("bench_run_prompt_locale", default=None)


@dataclass(frozen=True)
class AgentScenario:
    id: str
    tier: int
    rubric: str
    prompts: dict[str, str]
    agent_id: str = "general"
    execution: str = "chat"
    plain_completion: bool = False
    security_scan: bool = False
    requires: tuple[str, ...] = ()
    skip_without_env: str | None = None
    bench_workspace_suffix: str | None = None
    bench_dashboard_title_suffix: str | None = None
    source_dir: Path | None = None

    @property
    def locales(self) -> tuple[str, ...]:
        return tuple(sorted(self.prompts.keys()))

    @property
    def prompt(self) -> str:
        """Resolved prompt for the active bench locale (backward compatible)."""
        return self.prompt_for_locale(resolve_prompt_locale())

    def prompt_for_locale(self, locale: str | None = None) -> str:
        loc = resolve_prompt_locale(locale)
        if loc in self.prompts:
            return self.prompts[loc]
        if "en" in self.prompts:
            return self.prompts["en"]
        return next(iter(self.prompts.values()))


def bench_prompt_locale_from_env() -> str:
    raw = (
        os.environ.get("AGENT_BENCH_PROMPT_LOCALE")
        or os.environ.get("AGENT_BENCH_LOCALE")
        or "en"
    )
    return (raw or "en").strip().lower() or "en"


def bench_prompt_locale() -> str:
    """Active prompt locale: run config (ContextVar) → env fallback (CLI only)."""
    return resolve_prompt_locale()


def resolve_prompt_locale(explicit: str | None = None) -> str:
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip().lower()
    ctx = _bench_run_prompt_locale.get()
    if ctx:
        return ctx
    return bench_prompt_locale_from_env()


def bind_bench_run_prompt_locale(locale: str | None) -> Token[str | None]:
    return _bench_run_prompt_locale.set(resolve_prompt_locale(locale or "en"))


def reset_bench_run_prompt_locale(token: Token[str | None]) -> None:
    _bench_run_prompt_locale.reset(token)


def render_scenario_prompt(
    scenario: AgentScenario,
    fixture_ctx: FixtureContext,
    *,
    locale: str | None = None,
) -> str:
    template = resolve_env_placeholders(scenario.prompt_for_locale(locale))
    if "{" not in template:
        return template
    try:
        return template.format(
            prefix=fixture_ctx.prefix,
            friend_email=fixture_ctx.user_b_email or "",
        )
    except KeyError:
        return template


def bench_workspace_name(scenario: AgentScenario, prefix: str) -> str | None:
    suffix = (scenario.bench_workspace_suffix or "").strip()
    if not suffix:
        return None
    return f"{prefix}{suffix}"


def bench_dashboard_title(scenario: AgentScenario, prefix: str) -> str | None:
    suffix = (scenario.bench_dashboard_title_suffix or "").strip()
    if not suffix:
        return None
    return f"{prefix}{suffix}"


def scenarios_for_tier(scenarios: list[AgentScenario], max_tier: int) -> list[AgentScenario]:
    tier = max(1, int(max_tier))
    return [s for s in scenarios if s.tier <= tier]
