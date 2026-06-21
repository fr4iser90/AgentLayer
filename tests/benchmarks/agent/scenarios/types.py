"""Agent benchmark scenario types and prompt rendering."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path

from tests.benchmarks.agent.fixtures import FixtureContext
from tests.benchmarks.agent.scenarios._env import resolve_env_placeholders

_bench_run_prompt_locale: ContextVar[str | None] = ContextVar("bench_run_prompt_locale", default=None)
_bench_run_prompt_variant: ContextVar[str | None] = ContextVar("bench_run_prompt_variant", default=None)
_DEFAULT_PROMPT_VARIANT = "canonical"


@dataclass(frozen=True)
class AgentScenario:
    id: str
    tier: int
    rubric: str
    prompts: dict[str, str]
    prompt_variants: dict[str, dict[str, str]] | None = None
    agent_id: str = "general"
    execution: str = "chat"
    plain_completion: bool = False
    security_scan: bool = False
    requires: tuple[str, ...] = ()
    skip_without_env: str | None = None
    bench_workspace_suffix: str | None = None
    bench_dashboard_title_suffix: str | None = None
    attachments: tuple[str, ...] = ()
    source_dir: Path | None = None

    @property
    def locales(self) -> tuple[str, ...]:
        locales = set(self.prompts.keys())
        for rows in (self.prompt_variants or {}).values():
            locales.update(rows.keys())
        return tuple(sorted(locales))

    @property
    def variants(self) -> tuple[str, ...]:
        variants = {_DEFAULT_PROMPT_VARIANT}
        variants.update((self.prompt_variants or {}).keys())
        return tuple(sorted(variants))

    @property
    def prompt(self) -> str:
        """Resolved prompt for the active bench locale (backward compatible)."""
        return self.prompt_for_locale(resolve_prompt_locale(), variant=resolve_prompt_variant())

    def prompt_for_locale(
        self,
        locale: str | None = None,
        *,
        variant: str | None = None,
    ) -> str:
        loc = resolve_prompt_locale(locale)
        var = resolve_prompt_variant(variant)
        if var != _DEFAULT_PROMPT_VARIANT:
            variant_prompts = (self.prompt_variants or {}).get(var) or {}
            if loc in variant_prompts:
                return variant_prompts[loc]
            if "en" in variant_prompts:
                return variant_prompts["en"]
        return _prompt_from_locale_map(self.prompts, loc)


def _prompt_from_locale_map(prompts: dict[str, str], locale: str) -> str:
    if locale in prompts:
        return prompts[locale]
    if "en" in prompts:
        return prompts["en"]
    return next(iter(prompts.values()))


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


def bench_prompt_variant_from_env() -> str:
    raw = (
        os.environ.get("AGENT_BENCH_PROMPT_VARIANT")
        or os.environ.get("AGENT_BENCH_VARIANT")
        or _DEFAULT_PROMPT_VARIANT
    )
    return normalize_prompt_variant(raw)


def normalize_prompt_variant(raw: str | None) -> str:
    s = (str(raw or _DEFAULT_PROMPT_VARIANT)).strip().lower() or _DEFAULT_PROMPT_VARIANT
    t = "".join(c for c in s if c.isalnum() or c in "_-")[:32]
    return t or _DEFAULT_PROMPT_VARIANT


def bench_prompt_variant() -> str:
    """Active prompt variant: run config (ContextVar) -> env fallback (CLI only)."""
    return resolve_prompt_variant()


def resolve_prompt_locale(explicit: str | None = None) -> str:
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip().lower()
    ctx = _bench_run_prompt_locale.get()
    if ctx:
        return ctx
    return bench_prompt_locale_from_env()


def resolve_prompt_variant(explicit: str | None = None) -> str:
    if explicit is not None and str(explicit).strip():
        return normalize_prompt_variant(str(explicit))
    ctx = _bench_run_prompt_variant.get()
    if ctx:
        return ctx
    return bench_prompt_variant_from_env()


def bind_bench_run_prompt_locale(locale: str | None) -> Token[str | None]:
    return _bench_run_prompt_locale.set(resolve_prompt_locale(locale or "en"))


def reset_bench_run_prompt_locale(token: Token[str | None]) -> None:
    _bench_run_prompt_locale.reset(token)


def bind_bench_run_prompt_variant(variant: str | None) -> Token[str | None]:
    return _bench_run_prompt_variant.set(resolve_prompt_variant(variant))


def reset_bench_run_prompt_variant(token: Token[str | None]) -> None:
    _bench_run_prompt_variant.reset(token)


def render_scenario_prompt(
    scenario: AgentScenario,
    fixture_ctx: FixtureContext,
    *,
    locale: str | None = None,
    variant: str | None = None,
) -> str:
    template = resolve_env_placeholders(scenario.prompt_for_locale(locale, variant=variant))
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
