"""Load one benchmark scenario per directory under ``scenarios/<id>/``."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.benchmarks.agent.scenarios.types import AgentScenario

SCENARIOS_DIR = Path(__file__).resolve().parent


def _load_meta(meta_path: Path) -> dict:
    raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{meta_path}: meta.yaml must be a mapping")
    return raw


def _load_prompts(scenario_dir: Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    prompts: dict[str, str] = {}
    variants: dict[str, dict[str, str]] = {}
    for path in sorted(scenario_dir.glob("prompt.*.md")):
        parts = path.stem.split(".")
        if len(parts) not in (2, 3) or parts[0] != "prompt":
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        if len(parts) == 2:
            locale = parts[1].strip().lower()
            if locale:
                prompts[locale] = text
            continue
        variant = parts[1].strip().lower()
        locale = parts[2].strip().lower()
        if variant and locale:
            variants.setdefault(variant, {})[locale] = text
    if not prompts:
        raise ValueError(f"{scenario_dir}: at least one prompt.<locale>.md is required")
    return prompts, variants


def load_scenario_dir(scenario_dir: Path) -> AgentScenario:
    meta_path = scenario_dir / "meta.yaml"
    if not meta_path.is_file():
        raise ValueError(f"{scenario_dir}: missing meta.yaml")

    meta = _load_meta(meta_path)
    scenario_id = str(meta.get("id") or scenario_dir.name).strip()
    if scenario_id != scenario_dir.name:
        raise ValueError(
            f"{scenario_dir}: meta id {scenario_id!r} must match directory name {scenario_dir.name!r}"
        )

    requires_raw = meta.get("requires") or []
    if isinstance(requires_raw, str):
        requires = (requires_raw.strip(),) if requires_raw.strip() else ()
    elif isinstance(requires_raw, list):
        requires = tuple(str(x).strip() for x in requires_raw if str(x).strip())
    else:
        requires = ()
    prompts, prompt_variants = _load_prompts(scenario_dir)
    attachments_raw = meta.get("attachments") or []
    if isinstance(attachments_raw, str):
        attachments = (attachments_raw.strip(),) if attachments_raw.strip() else ()
    elif isinstance(attachments_raw, list):
        attachments = tuple(str(x).strip() for x in attachments_raw if str(x).strip())
    else:
        attachments = ()

    return AgentScenario(
        id=scenario_id,
        tier=int(meta.get("tier") or 1),
        rubric=str(meta.get("rubric") or "").strip(),
        prompts=prompts,
        prompt_variants=prompt_variants,
        agent_id=str(meta.get("agent_id") or "general").strip() or "general",
        execution=str(meta.get("execution") or "chat").strip() or "chat",
        plain_completion=bool(meta.get("plain_completion", False)),
        security_scan=bool(meta.get("security_scan", False)),
        requires=requires,
        skip_without_env=(
            str(meta["skip_without_env"]).strip() if meta.get("skip_without_env") else None
        ),
        bench_workspace_suffix=(
            str(meta["bench_workspace_suffix"]).strip()
            if meta.get("bench_workspace_suffix")
            else None
        ),
        bench_dashboard_title_suffix=(
            str(meta["bench_dashboard_title_suffix"]).strip()
            if meta.get("bench_dashboard_title_suffix")
            else None
        ),
        attachments=attachments,
        source_dir=scenario_dir,
    )


def discover_scenarios(*, root: Path | None = None) -> list[AgentScenario]:
    base = root or SCENARIOS_DIR
    out: list[AgentScenario] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "meta.yaml").is_file():
            continue
        out.append(load_scenario_dir(child))
    if not out:
        raise RuntimeError(f"no scenarios found under {base}")
    ids = [s.id for s in out]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate scenario ids in registry")
    return out


_ALL = discover_scenarios()
SCENARIO_BY_ID = {s.id: s for s in _ALL}


def available_prompt_locales() -> tuple[str, ...]:
    locales: set[str] = set()
    for sc in _ALL:
        locales.update(sc.locales)
    return tuple(sorted(locales)) or ("en",)


def available_prompt_variants() -> tuple[str, ...]:
    variants: set[str] = {"canonical", "realistic"}
    for sc in _ALL:
        variants.update(sc.variants)
    return tuple(sorted(variants)) or ("canonical",)


def scenarios_for_tier(max_tier: int) -> list[AgentScenario]:
    from tests.benchmarks.agent.scenarios.types import scenarios_for_tier as _tier

    return _tier(_ALL, max_tier)
