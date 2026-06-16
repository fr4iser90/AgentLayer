"""Rule-based benchmark failure pattern classification."""

from __future__ import annotations

from typing import Any


def classify_failure(result: dict[str, Any]) -> list[str]:
    """Return pattern ids for a single scenario attempt result dict."""
    patterns: list[str] = []
    if not isinstance(result, dict):
        return patterns

    passed = bool(result.get("passed"))
    if passed:
        return patterns

    err = str(result.get("error") or result.get("failure_reason") or "").lower()
    tools = result.get("tools_called") or result.get("tool_calls") or []
    tool_names = {
        str((t.get("name") if isinstance(t, dict) else t) or "").lower()
        for t in (tools if isinstance(tools, list) else [])
    }
    assistant = str(result.get("assistant_text") or result.get("final_text") or "").lower()

    if "timeout" in err or "timed out" in err:
        patterns.append("E_timeout")
    if "tool_choice" in err or "no tool" in err or "text_no_tools" in err:
        patterns.append("A1_no_tool_call")
    if not tool_names and not passed:
        patterns.append("A1_no_tool_call")
    if "catalog" in err or ("catalog" not in tool_names and "s1" in str(result.get("scenario_id") or "").lower()):
        if "catalog" not in tool_names:
            patterns.append("S1_no_catalog")
    if "delegate" in err and "delegate" not in tool_names:
        patterns.append("S4_no_delegate")
    if "max_tool_rounds" in err or "tool round" in err:
        patterns.append("E_max_rounds")
    if "permission" in err or "403" in err:
        patterns.append("E_permission")
    if "workspace" in err and "workspace.create" not in tool_names:
        patterns.append("C_no_workspace")
    if len(assistant) > 4000:
        patterns.append("A_verbose_text")
    if not patterns:
        patterns.append("unknown")
    return sorted(set(patterns))


def aggregate_patterns(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        for pid in classify_failure(row):
            counts[pid] = counts.get(pid, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
