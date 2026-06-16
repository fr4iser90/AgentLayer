"""Resolve effective benchmark harness settings per model profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.backend.infrastructure import benchmark_harness_store


@dataclass(frozen=True)
class EffectiveHarness:
    harness_preset: str
    max_tool_rounds_override: int | None
    scenario_timeout_sec: float | None
    capture_timeline: bool | None
    stream_llm: bool | None
    source: str
    override_id: str | None = None


def _row_fields(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "harness_preset": row.get("harness_preset"),
        "max_tool_rounds_override": row.get("max_tool_rounds_override"),
        "scenario_timeout_sec": row.get("scenario_timeout_sec"),
        "capture_timeline": row.get("capture_timeline"),
        "stream_llm": row.get("stream_llm"),
    }


def _pick(
    override: dict[str, Any],
    global_cfg: dict[str, Any],
    run_fallback: dict[str, Any],
    *,
    source: str,
    override_id: str | None = None,
) -> EffectiveHarness:
    preset = (
        override.get("harness_preset")
        or global_cfg.get("harness_preset")
        or run_fallback.get("harness_preset")
        or "observability"
    )
    preset = str(preset).strip().lower()
    if preset not in ("observability", "chat_parity"):
        preset = "observability"

    def _first(key: str) -> Any:
        for src in (override, global_cfg, run_fallback):
            val = src.get(key)
            if val is not None:
                return val
        return None

    return EffectiveHarness(
        harness_preset=preset,
        max_tool_rounds_override=_first("max_tool_rounds_override"),
        scenario_timeout_sec=_first("scenario_timeout_sec"),
        capture_timeline=_first("capture_timeline"),
        stream_llm=_first("stream_llm"),
        source=source,
        override_id=override_id,
    )


def _match_override(
    overrides: list[dict[str, Any]],
    *,
    catalog_owned_by: str,
    model: str,
) -> tuple[dict[str, Any] | None, str, str | None]:
    catalog = str(catalog_owned_by or "").strip()
    model_id = str(model or "").strip()
    exact: dict[str, Any] | None = None
    provider_only: dict[str, Any] | None = None
    for row in overrides:
        row_catalog = str(row.get("catalog_owned_by") or "").strip()
        row_model = str(row.get("model") or "").strip()
        if row_catalog != catalog:
            continue
        if row_model and row_model == model_id:
            exact = row
            break
        if not row_model and provider_only is None:
            provider_only = row
    if exact is not None:
        return exact, "model_override", str(exact.get("id") or "") or None
    if provider_only is not None:
        return provider_only, "provider_override", str(provider_only.get("id") or "") or None
    return None, "global", None


def load_matrix(tenant_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return benchmark_harness_store.get_global(tenant_id), benchmark_harness_store.list_overrides(tenant_id)


def resolve_for_profile(
    *,
    tenant_id: int,
    catalog_owned_by: str,
    model: str,
    run_harness_preset: str | None = None,
    run_max_tool_rounds_override: int | None = None,
    run_scenario_timeout_sec: float | None = None,
    use_matrix: bool = True,
    matrix: tuple[dict[str, Any], list[dict[str, Any]]] | None = None,
) -> EffectiveHarness:
    run_fallback = {
        "harness_preset": run_harness_preset,
        "max_tool_rounds_override": run_max_tool_rounds_override,
        "scenario_timeout_sec": run_scenario_timeout_sec,
        "capture_timeline": None,
        "stream_llm": None,
    }
    if not use_matrix:
        return _pick({}, {}, run_fallback, source="run_fallback")

    global_cfg, overrides = matrix if matrix is not None else load_matrix(tenant_id)
    matched, source, override_id = _match_override(
        overrides,
        catalog_owned_by=catalog_owned_by,
        model=model,
    )
    if matched is not None:
        return _pick(
            _row_fields(matched),
            _row_fields(global_cfg),
            run_fallback,
            source=source,
            override_id=override_id,
        )
    return _pick({}, _row_fields(global_cfg), run_fallback, source="global")
