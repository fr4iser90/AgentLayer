"""DB-backed task-intent overlays for small-model tool routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.backend.infrastructure.agent_runtime import agent_config_effective


@dataclass(frozen=True)
class TaskIntentMatch:
    intent_id: str
    categories: frozenset[str]
    tools: frozenset[str]
    hint: str


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _string_set(value: Any, *, dotted: bool = False) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    out: set[str] = set()
    for item in value:
        raw = _normalize_text(item)
        if not raw:
            continue
        if dotted:
            raw = raw.replace(" ", "")
        out.add(raw)
    return frozenset(out)


def _intent_rows(*, tenant_id: int | None = None) -> list[dict[str, Any]]:
    val, _src = agent_config_effective.effective_value(
        "tool_routing.task_intent_overlay",
        tenant_id=tenant_id,
    )
    if not isinstance(val, dict):
        return []
    rows = val.get("intents")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def task_intent_overlay_enabled(*, tenant_id: int | None = None) -> bool:
    return agent_config_effective.effective_bool(
        "tool_routing.task_intent_overlay_enabled",
        tenant_id=tenant_id,
        default=False,
    )


def task_intent_strict_tools(*, tenant_id: int | None = None) -> bool:
    return agent_config_effective.effective_bool(
        "tool_routing.task_intent_strict_tools",
        tenant_id=tenant_id,
        default=True,
    )


def match_task_intents(text: str, *, tenant_id: int | None = None) -> list[TaskIntentMatch]:
    if not task_intent_overlay_enabled(tenant_id=tenant_id):
        return []
    low = _normalize_text(text)
    if not low:
        return []

    matches: list[TaskIntentMatch] = []
    for row in _intent_rows(tenant_id=tenant_id):
        triggers = _string_set(row.get("triggers"))
        if not triggers or not any(trigger in low for trigger in triggers):
            continue
        intent_id = _normalize_text(row.get("id")) or "task_intent"
        categories = _string_set(row.get("categories"))
        tools = _string_set(row.get("tools"), dotted=True)
        hint = str(row.get("hint") or "").strip()
        matches.append(
            TaskIntentMatch(
                intent_id=intent_id,
                categories=categories,
                tools=tools,
                hint=hint,
            )
        )
    return matches


def categories_for_matches(matches: list[TaskIntentMatch]) -> frozenset[str]:
    out: set[str] = set()
    for match in matches:
        out.update(match.categories)
    return frozenset(out)


def tools_for_matches(matches: list[TaskIntentMatch]) -> frozenset[str]:
    out: set[str] = set()
    for match in matches:
        out.update(match.tools)
    return frozenset(out)


def hints_for_matches(matches: list[TaskIntentMatch]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for match in matches:
        if match.hint and match.hint not in seen:
            seen.add(match.hint)
            out.append(match.hint)
    return out

