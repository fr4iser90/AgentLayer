"""Extract rich run metrics for agent LLM benchmarks (context, compaction, tools)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RunMetrics:
    """Full observability snapshot for one scenario × profile execution."""

    capture_mode: str = "http"
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    compaction_events: list[dict[str, Any]] = field(default_factory=list)
    context_update_count: int = 0
    compaction_count: int = 0
    loop_compaction_count: int = 0
    history_compaction_count: int = 0
    llm_round_count: int = 0
    tool_start_count: int = 0
    tool_done_count: int = 0
    tool_fail_count: int = 0
    subagent_start_count: int = 0
    tool_invocations: list[dict[str, Any]] = field(default_factory=list)
    agent_run: dict[str, Any] = field(default_factory=dict)
    timeline_summary: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    context_utilization_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _int_or_none(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def context_from_completion(data: dict[str, Any]) -> dict[str, Any]:
    ctx = data.get("agentlayer_context")
    if isinstance(ctx, dict):
        return dict(ctx)
    return {}


def usage_from_completion(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage")
    return dict(usage) if isinstance(usage, dict) else {}


def utilization_pct(context: dict[str, Any]) -> float | None:
    prompt = _int_or_none(context.get("provider_prompt_tokens"))
    budget = _int_or_none(context.get("budget_tokens")) or _int_or_none(
        context.get("context_window_tokens")
    )
    if prompt is None or not budget or budget <= 0:
        return None
    return round(min(100.0, (prompt / budget) * 100.0), 2)


def bench_ws_diagnostics(events: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Actionable failure context for benchmark UI (websocket timeline)."""
    rows = [e for e in (events or []) if isinstance(e, dict)]
    if not rows:
        return {}
    compaction_events, timeline, counts = summarize_ws_events(rows)
    ws_errors: list[dict[str, Any]] = []
    for ev in rows:
        typ = str(ev.get("type") or "")
        if typ in ("error", "agent.aborted") or ev.get("error"):
            ws_errors.append(
                {
                    "type": typ,
                    "detail": ev.get("detail") or ev.get("message"),
                    "http_status": ev.get("http_status"),
                }
            )
    return {
        "ws_event_count": len(rows),
        "ws_errors": ws_errors[-5:],
        "timeline_tail": timeline[-16:],
        "event_counts": counts,
        "compaction_count_live": len(compaction_events),
    }


def live_snapshot_from_ws_events(
    events: list[dict[str, Any]],
    *,
    elapsed_ms: float,
) -> dict[str, Any]:
    """Partial bench UI state from websocket timeline (in-flight scenario)."""
    _, timeline, counts = summarize_ws_events(events)
    tool_names: list[str] = []
    for row in timeline:
        if row.get("type") == "agent.tool_start":
            name = str(row.get("tool") or "").strip()
            if name:
                tool_names.append(name)
    last = timeline[-1] if timeline else {}
    last_type = str(last.get("type") or "")
    phase = "running"
    detail = ""
    if last_type == "agent.tool_start":
        phase = "tool"
        detail = str(last.get("tool") or "")
    elif last_type == "agent.tool_done":
        phase = "tool"
        detail = str(last.get("tool") or "")
    elif last_type == "agent.llm_round":
        phase = "llm"
        detail = f"round {last.get('round')}" if last.get("round") is not None else ""
    elif last_type == "agent.context_compacted":
        phase = "compact"
        detail = str(last.get("phase") or "")
    return {
        "phase": phase,
        "detail": detail,
        "llm_round_count": counts["llm_round_count"],
        "tool_call_count": counts["tool_done_count"],
        "tool_names": tool_names,
        "elapsed_ms": round(elapsed_ms, 1),
    }


def summarize_ws_events(events: list[dict[str, Any]]) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Return compaction_events, timeline_summary, counters."""
    compaction_events: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    counts = {
        "context_update_count": 0,
        "llm_round_count": 0,
        "tool_start_count": 0,
        "tool_done_count": 0,
        "tool_fail_count": 0,
        "subagent_start_count": 0,
    }

    for ev in events:
        if not isinstance(ev, dict):
            continue
        typ = str(ev.get("type") or "")
        if typ == "agent.context_update":
            counts["context_update_count"] += 1
            continue
        if typ == "agent.context_compacted":
            compaction_events.append(
                {
                    "phase": ev.get("phase"),
                    "reason": ev.get("reason"),
                    "round": ev.get("round"),
                    "provider_prompt_tokens": ev.get("provider_prompt_tokens"),
                    "soft_limit_tokens": ev.get("soft_limit_tokens"),
                    "context_window_tokens": ev.get("context_window_tokens"),
                    "tool_rounds_dropped": ev.get("tool_rounds_dropped"),
                    "summary_active": ev.get("summary_active"),
                    "context": ev.get("context") if isinstance(ev.get("context"), dict) else {},
                }
            )
            timeline.append({"type": typ, "phase": ev.get("phase"), "round": ev.get("round")})
            continue
        if typ == "agent.llm_round":
            counts["llm_round_count"] += 1
            timeline.append({"type": typ, "round": ev.get("round")})
            continue
        if typ == "agent.tool_start":
            counts["tool_start_count"] += 1
            timeline.append({"type": typ, "tool": ev.get("name") or ev.get("tool_name")})
            continue
        if typ == "agent.tool_done":
            counts["tool_done_count"] += 1
            ok = ev.get("ok")
            if ok is False:
                counts["tool_fail_count"] += 1
            timeline.append(
                {
                    "type": typ,
                    "tool": ev.get("name") or ev.get("tool_name"),
                    "ok": ok,
                }
            )
            continue
        if typ == "agent.subagent_start":
            counts["subagent_start_count"] += 1
            timeline.append({"type": typ, "agent_id": ev.get("agent_id")})

    return compaction_events, timeline, counts


def build_run_metrics(
    *,
    completion: dict[str, Any],
    ws_events: list[dict[str, Any]] | None,
    tool_invocations: list[dict[str, Any]],
    agent_run: dict[str, Any] | None,
    capture_mode: str,
) -> RunMetrics:
    ctx = context_from_completion(completion)
    usage = usage_from_completion(completion)
    prompt_t = _int_or_none(usage.get("prompt_tokens"))
    completion_t = _int_or_none(usage.get("completion_tokens"))
    total_t = _int_or_none(usage.get("total_tokens"))
    if total_t is None and prompt_t is not None and completion_t is not None:
        total_t = prompt_t + completion_t

    compaction_events: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    counts = {
        "context_update_count": 0,
        "llm_round_count": 0,
        "tool_start_count": 0,
        "tool_done_count": 0,
        "tool_fail_count": 0,
        "subagent_start_count": 0,
    }

    if ws_events:
        compaction_events, timeline, counts = summarize_ws_events(ws_events)
    elif ctx.get("compaction_applied") or ctx.get("loop_compaction_applied"):
        compaction_events.append(
            {
                "phase": "loop" if ctx.get("loop_compaction_applied") else "history",
                "reason": "final_snapshot",
                "round": None,
                "context": ctx,
            }
        )

    loop_n = sum(1 for e in compaction_events if e.get("phase") == "loop")
    hist_n = sum(1 for e in compaction_events if e.get("phase") == "history")
    if not compaction_events and ctx.get("loop_compaction_applied"):
        loop_n = 1
    if not compaction_events and ctx.get("compaction_applied") and not ctx.get("loop_compaction_applied"):
        hist_n = 1

    tool_fail = sum(
        1 for inv in tool_invocations if isinstance(inv, dict) and inv.get("ok") is False
    )
    if counts["tool_fail_count"]:
        tool_fail = max(tool_fail, counts["tool_fail_count"])

    inv_public = []
    for inv in tool_invocations:
        if not isinstance(inv, dict):
            continue
        inv_public.append(
            {
                "tool_name": inv.get("tool_name"),
                "ok": inv.get("ok"),
                "created_at": inv.get("created_at"),
                "result_excerpt": (str(inv.get("result_excerpt") or "")[:200] or None),
            }
        )

    run_row = dict(agent_run) if isinstance(agent_run, dict) else {}
    if run_row.get("token_usage") and isinstance(run_row["token_usage"], dict):
        tu = run_row["token_usage"]
        prompt_t = prompt_t or _int_or_none(tu.get("prompt_tokens"))
        completion_t = completion_t or _int_or_none(tu.get("completion_tokens"))
        total_t = total_t or _int_or_none(tu.get("total_tokens"))

    return RunMetrics(
        capture_mode=capture_mode,
        context_snapshot=ctx,
        compaction_events=compaction_events,
        context_update_count=counts["context_update_count"],
        compaction_count=len(compaction_events),
        loop_compaction_count=loop_n,
        history_compaction_count=hist_n,
        llm_round_count=counts["llm_round_count"],
        tool_start_count=counts["tool_start_count"],
        tool_done_count=counts["tool_done_count"],
        tool_fail_count=tool_fail,
        subagent_start_count=counts["subagent_start_count"],
        tool_invocations=inv_public,
        agent_run={
            k: run_row[k]
            for k in (
                "id",
                "status",
                "started_at",
                "finished_at",
                "token_usage",
                "error",
                "agent_id",
            )
            if k in run_row
        },
        timeline_summary=timeline[:200],
        prompt_tokens=prompt_t,
        completion_tokens=completion_t,
        total_tokens=total_t,
        context_utilization_pct=utilization_pct(ctx),
    )
