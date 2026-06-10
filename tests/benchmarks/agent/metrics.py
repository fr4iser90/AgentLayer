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
    provider_cached_prompt_tokens: int | None = None
    context_utilization_pct: float | None = None
    provider_cache_prompt_disabled: bool | None = None

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


def usage_cached_prompt_tokens(usage: dict[str, Any] | None) -> int | None:
    """OpenAI-style ``usage.prompt_tokens_details.cached_tokens`` (provider KV/prompt cache)."""
    if not isinstance(usage, dict):
        return None
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        n = _int_or_none(details.get("cached_tokens"))
        if n is not None:
            return n
    for key in ("cached_tokens", "cache_read_input_tokens"):
        n = _int_or_none(usage.get(key))
        if n is not None:
            return n
    return None


def latest_context_from_ws_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    for ev in reversed(events):
        if not isinstance(ev, dict) or str(ev.get("type") or "") != "agent.context_update":
            continue
        ctx = ev.get("context")
        if isinstance(ctx, dict):
            return dict(ctx)
    return {}


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

    forwarded_tool_count: int | None = None
    routed_category: str | None = None
    llm_text_chars = 0
    llm_reasoning_chars = 0
    generation_preview = ""
    for ev in events:
        if not isinstance(ev, dict):
            continue
        typ = str(ev.get("type") or "")
        if typ == "agent.session":
            fwd = ev.get("forwarded_tools")
            if isinstance(fwd, list):
                forwarded_tool_count = len(fwd)
            rc = ev.get("routed_category")
            if isinstance(rc, str) and rc.strip():
                routed_category = rc.strip()
        elif typ == "agent.llm_delta":
            channel = str(ev.get("channel") or "").strip().lower()
            if channel == "reasoning":
                chunk = str(ev.get("reasoning_delta") or "")
                llm_reasoning_chars += len(chunk)
                if chunk:
                    generation_preview = (generation_preview + chunk)[-160:]
            else:
                chunk = str(ev.get("delta") or "")
                llm_text_chars += len(chunk)
                if chunk:
                    generation_preview = (generation_preview + chunk)[-160:]

    ctx_snap = latest_context_from_ws_events(events)
    last = timeline[-1] if timeline else {}
    last_type = str(last.get("type") or "")

    open_llm_round: int | None = None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        typ = str(ev.get("type") or "")
        if typ == "agent.llm_round_start":
            open_llm_round = _int_or_none(ev.get("round"))
        elif typ == "agent.llm_round":
            open_llm_round = None

    phase = "running"
    detail = ""
    if open_llm_round is not None:
        phase = "llm_generating"
        detail = f"round {open_llm_round}"
    elif last_type == "agent.tool_start":
        phase = "tool"
        detail = str(last.get("tool") or "")
    elif last_type == "agent.tool_done":
        phase = "tool"
        detail = str(last.get("tool") or "")
    elif last_type == "agent.llm_round":
        phase = "llm"
        detail = f"round {last.get('round')}" if last.get("round") is not None else ""
    elif last_type == "agent.session":
        phase = "session"
        if forwarded_tool_count is not None:
            detail = f"{forwarded_tool_count} tools"
        elif routed_category:
            detail = routed_category
    elif last_type == "agent.context_compacted":
        phase = "compact"
        detail = str(last.get("phase") or "")

    current_llm_round: int | None = open_llm_round
    if current_llm_round is None:
        for ev in reversed(events):
            if not isinstance(ev, dict):
                continue
            if str(ev.get("type") or "") == "agent.llm_round_start":
                current_llm_round = _int_or_none(ev.get("round"))
                break

    out: dict[str, Any] = {
        "phase": phase,
        "detail": detail,
        "llm_round_count": counts["llm_round_count"],
        "tool_call_count": counts["tool_done_count"],
        "tool_names": tool_names,
        "elapsed_ms": round(elapsed_ms, 1),
    }
    if current_llm_round is not None:
        out["current_llm_round"] = current_llm_round
    if forwarded_tool_count is not None:
        out["forwarded_tool_count"] = forwarded_tool_count
    if routed_category:
        out["routed_category"] = routed_category
    if llm_text_chars > 0:
        out["llm_text_chars"] = llm_text_chars
    if llm_reasoning_chars > 0:
        out["llm_reasoning_chars"] = llm_reasoning_chars
    if generation_preview.strip():
        out["generation_preview"] = generation_preview.strip()
    ppt = _int_or_none(ctx_snap.get("provider_prompt_tokens"))
    if ppt is not None:
        out["provider_prompt_tokens"] = ppt
    cwin = _int_or_none(ctx_snap.get("context_window_tokens"))
    if cwin is not None:
        out["context_window_tokens"] = cwin
    return out


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
        if typ == "agent.llm_round_start":
            timeline.append({"type": typ, "round": ev.get("round")})
            continue
        if typ == "agent.llm_delta":
            timeline.append(
                {
                    "type": typ,
                    "round": ev.get("round"),
                    "channel": ev.get("channel"),
                }
            )
            continue
        if typ == "agent.session":
            fwd = ev.get("forwarded_tools")
            timeline.append(
                {
                    "type": typ,
                    "forward_count": len(fwd) if isinstance(fwd, list) else None,
                    "routed_category": ev.get("routed_category"),
                }
            )
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
    provider_cache_prompt_disabled: bool | None = None,
) -> RunMetrics:
    ctx = context_from_completion(completion)
    usage = usage_from_completion(completion)
    prompt_t = _int_or_none(usage.get("prompt_tokens"))
    completion_t = _int_or_none(usage.get("completion_tokens"))
    total_t = _int_or_none(usage.get("total_tokens"))
    cached_prompt_t = usage_cached_prompt_tokens(usage)
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
        provider_cached_prompt_tokens=cached_prompt_t,
        context_utilization_pct=utilization_pct(ctx),
        provider_cache_prompt_disabled=provider_cache_prompt_disabled,
    )
