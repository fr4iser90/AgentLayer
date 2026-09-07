"""Translate ``agent.*`` websocket events into display lines.

Deliberately free of Textual imports: this is the part worth unit-testing, and the event
contract (documented in ``apps/backend/api/chat/controllers/chat_websocket.py``) is the only
thing that can silently break the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TOOL_GLYPH = "\u23fa"  # ⏺
OK_MARK = "\u2713"  # ✓
FAIL_MARK = "\u2717"  # ✗
DOT = " \u00b7 "
TODO_MARKS = {"completed": "\u2713", "in_progress": "\u25b6", "pending": "\u25cb"}
TODO_MARK_FALLBACK = "\u25cb"


@dataclass(frozen=True)
class Line:
    """One rendered row. ``key`` lets a later event rewrite the row it belongs to."""

    kind: str
    text: str
    depth: int = 0
    key: str | None = None


@dataclass(frozen=True)
class PermissionRequest:
    request_id: str
    tool_name: str
    args_preview: str
    round: int | None = None


@dataclass
class Update:
    """Everything one event changes. Fields left at their default mean "unchanged"."""

    lines: list[Line] = field(default_factory=list)
    delta: str = ""
    reasoning_delta: str = ""
    strip_changed: bool = False
    permission: PermissionRequest | None = None
    completion: dict[str, Any] | None = None
    finished: bool = False
    error: str | None = None
    wait_hint: str | None = None
    clear_wait_hint: bool = False


class TurnState:
    """Carries across events what a later one needs from an earlier one."""

    def __init__(self) -> None:
        self.tool_labels: dict[str, str] = {}
        self.goal: dict[str, Any] | None = None
        self.todos: list[dict[str, Any]] = []
        self.counts: dict[str, int] = {}
        self.plan_mode: bool = False
        self.answer: str = ""
        self.reasoning: str = ""

    def reset_turn(self) -> None:
        self.tool_labels.clear()
        self.answer = ""
        self.reasoning = ""


def _s(msg: dict[str, Any], key: str) -> str:
    v = msg.get(key)
    return v.strip() if isinstance(v, str) else ""


def _raw(msg: dict[str, Any], key: str) -> str:
    """Like ``_s`` but keeps whitespace — required for streamed token deltas."""
    v = msg.get(key)
    return v if isinstance(v, str) else ""


def _i(msg: dict[str, Any], key: str) -> int | None:
    v = msg.get(key)
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def tool_label(msg: dict[str, Any]) -> str:
    """Mirror the WebUI: prefer the backend's ``step_label``, then ``label``, then the name."""
    return (
        _s(msg, "step_label")
        or _s(msg, "label")
        or (_s(msg, "name") or _s(msg, "tool") or "tool").replace("_", " ")
    )


def format_duration(ms: float | None) -> str:
    if ms is None or ms < 0:
        return ""
    if ms < 1000:
        return f"{int(ms)} ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f} s"
    return f"{ms / 60_000:.1f} min"


def _tool_key(msg: dict[str, Any], *, prefix: str = "tool") -> str:
    name = _s(msg, "name") or _s(msg, "tool") or "tool"
    rnd = _i(msg, "round")
    return f"{prefix}:{name}:{rnd if rnd is not None else '-'}"


def _tool_start_line(msg: dict[str, Any], state: TurnState, *, depth: int = 0) -> Line:
    key = _tool_key(msg)
    label = tool_label(msg)
    state.tool_labels[key] = label
    summary = _s(msg, "summary")
    text = f"{TOOL_GLYPH} {label}"
    if summary and summary.lower() not in label.lower():
        text = f"{text} — {summary}"
    return Line(kind="tool_start", text=text, depth=depth, key=key)


def _tool_done_line(msg: dict[str, Any], state: TurnState, *, depth: int = 0) -> Line:
    key = _tool_key(msg)
    label = state.tool_labels.get(key) or tool_label(msg)
    ok = msg.get("result_ok")
    if ok is None:
        ok = msg.get("ok")
    error = _s(msg, "result_error") or _s(msg, "error")
    parts: list[str] = []
    if ok is False:
        parts.append(f"failed: {error}" if error else "failed")
    chars = _i(msg, "result_chars")
    if chars:
        parts.append(f"{chars} chars")
    dur = format_duration(_i(msg, "duration_ms"))
    if dur:
        parts.append(dur)
    mark = FAIL_MARK if ok is False else OK_MARK
    tail = f"  {mark} {DOT.join(parts)}" if parts else f"  {mark}"
    return Line(
        kind="tool_error" if ok is False else "tool_done",
        text=f"{TOOL_GLYPH} {label}{tail}",
        depth=depth,
        key=key,
    )


def _rejected_line(msg: dict[str, Any]) -> Line | None:
    """The model sent arguments the schema refused — a strong signal it is guessing."""
    if not msg.get("rejected"):
        return None
    validation = msg.get("validation")
    detail = ""
    if isinstance(validation, dict):
        bits = [f"{k}: {v}" for k, v in list(validation.items())[:3]]
        detail = "; ".join(str(b) for b in bits)
    elif isinstance(validation, str):
        detail = validation.strip()
    name = _s(msg, "name") or "tool"
    return Line(kind="warn", text=f"! {name} rejected{f' — {detail}' if detail else ''}")


def goal_strip(state: TurnState) -> list[str]:
    """Two rows: the objective with its phase, and the todos with a done count."""
    goal = state.goal if isinstance(state.goal, dict) else None
    if goal:
        phase = str(goal.get("phase") or "").strip() or "active"
        objective = str(goal.get("objective") or "").strip() or "(no objective)"
        rounds = goal.get("rounds_started")
        max_rounds = goal.get("max_goal_rounds")
        meta = f"{phase}"
        if isinstance(rounds, int) and isinstance(max_rounds, int) and max_rounds:
            meta = f"{phase}, round {rounds}/{max_rounds}"
        blocked = str(goal.get("blocked_reason") or "").strip()
        if blocked:
            meta = f"{meta} — {blocked}"
        top = f"Goal  {objective}   [{meta}]"
    else:
        top = "Goal  —"
    if state.plan_mode:
        top = f"{top}   [plan mode]"

    todos = state.todos or []
    if not todos:
        return [top, "Todos  —"]
    counts = state.counts or {}
    done = counts.get("completed")
    if not isinstance(done, int):
        done = sum(1 for t in todos if str(t.get("status")) == "completed")
    items = "   ".join(
        TODO_MARKS.get(str(t.get("status")), TODO_MARK_FALLBACK)
        + " "
        + str(t.get("content") or "").strip()
        for t in todos[:6]
    )
    more = f"   (+{len(todos) - 6})" if len(todos) > 6 else ""
    return [top, f"Todos {done}/{len(todos)}   {items}{more}"]


def interpret(msg: dict[str, Any], state: TurnState) -> Update:
    """Map one server event onto display changes. Unknown types are ignored on purpose."""
    typ = msg.get("type")
    if not isinstance(typ, str):
        return Update()

    if typ == "pong":
        return Update()

    if typ == "error":
        detail = _s(msg, "detail") or "agent error"
        return Update(lines=[Line("error", f"Error: {detail}")], finished=True, error=detail)

    if typ == "chat.completion":
        if msg.get("error"):
            detail = _s(msg, "detail") or "turn failed"
            return Update(lines=[Line("error", f"Error: {detail}")], finished=True, error=detail)
        data = msg.get("data") if isinstance(msg.get("data"), dict) else None
        return Update(completion=data, finished=True, clear_wait_hint=True)

    if typ == "agent.session":
        # The event is named after the run, but all it carries is the resolved model.
        model = _s(msg, "effective_model")
        how = _s(msg, "model_resolution")
        bits = " ".join(x for x in (model, f"({how})" if how else "") if x)
        return Update(lines=[Line("info", f"model  {bits}")] if bits else [])

    if typ == "agent.llm_round_start":
        rnd = _i(msg, "round")
        return Update(
            lines=[Line("dim", f"round {rnd or '?'}")],
            clear_wait_hint=True,
        )

    if typ == "agent.llm_delta":
        # Never strip a delta: chunk boundaries fall inside and between words, so trimming
        # each one glues the answer together ("TheTUIclient…").
        channel = _s(msg, "channel")
        reasoning = _raw(msg, "reasoning_delta")
        if channel == "reasoning" or reasoning:
            return Update(reasoning_delta=reasoning or _raw(msg, "delta"), clear_wait_hint=True)
        return Update(delta=_raw(msg, "delta"), clear_wait_hint=True)

    if typ == "agent.llm_round":
        return Update(clear_wait_hint=True)

    if typ == "agent.tool_start":
        lines = [_tool_start_line(msg, state)]
        rejected = _rejected_line(msg)
        if rejected:
            lines.append(rejected)
        return Update(lines=lines, clear_wait_hint=True)

    if typ == "agent.tool_done":
        return Update(lines=[_tool_done_line(msg, state)])

    if typ == "agent.subagent_start":
        agent_id = _s(msg, "agent_id") or "agent"
        detail = _s(msg, "detail")
        text = f"{TOOL_GLYPH} delegate \u2192 {agent_id}"
        if detail:
            text = f"{text}: {detail}"
        return Update(lines=[Line("sub_start", text, key=f"sub:{_s(msg, 'subagent_run_id')}")])

    if typ == "agent.subagent_step":
        phase = _s(msg, "phase")
        if phase == "start":
            return Update(lines=[_tool_start_line(msg, state, depth=1)])
        return Update(lines=[_tool_done_line(msg, state, depth=1)])

    if typ == "agent.subagent_done":
        agent_id = _s(msg, "agent_id") or "agent"
        ok = msg.get("ok")
        detail = _s(msg, "detail")
        mark = OK_MARK if ok is not False else FAIL_MARK
        text = f"\u2514 {agent_id} {mark}"
        if detail:
            text = f"{text} {detail}"
        return Update(lines=[Line("sub_done", text, depth=1)])

    if typ == "agent.goal":
        goal = msg.get("goal")
        state.goal = goal if isinstance(goal, dict) else None
        objective = ""
        if isinstance(goal, dict):
            objective = str(goal.get("objective") or "").strip()[:120]
        event = _s(msg, "goal_event") or "update"
        return Update(
            lines=[Line("goal", f"goal {event}: {objective}" if objective else f"goal {event}")],
            strip_changed=True,
        )

    if typ == "agent.todos":
        todos = msg.get("todos")
        state.todos = [t for t in todos if isinstance(t, dict)] if isinstance(todos, list) else []
        counts = msg.get("counts")
        state.counts = counts if isinstance(counts, dict) else {}
        return Update(
            lines=[Line("goal", f"todos updated ({len(state.todos)})")],
            strip_changed=True,
        )

    if typ == "agent.plan_mode":
        state.plan_mode = bool(msg.get("plan_mode"))
        return Update(
            lines=[Line("goal", f"plan mode {'on' if state.plan_mode else 'off'}")],
            strip_changed=True,
        )

    if typ == "agent.goal_round":
        rnd = _i(msg, "round")
        mx = _i(msg, "max_goal_rounds")
        if msg.get("continue"):
            text = f"goal round {rnd or '?'}/{mx or '?'} — continuing"
        else:
            text = f"goal round stopped ({_s(msg, 'reason') or 'done'})"
        return Update(lines=[Line("goal", text)], strip_changed=True)

    if typ == "agent.permission_ask":
        return Update(
            permission=PermissionRequest(
                request_id=_s(msg, "request_id"),
                tool_name=_s(msg, "tool_name") or "tool",
                args_preview=_s(msg, "args_preview"),
                round=_i(msg, "round"),
            )
        )

    if typ == "agent.secret_prompt":
        service = _s(msg, "service_key") or "a service"
        return Update(
            lines=[Line("warn", f"! {service} needs a secret — save it in the WebUI, then retry")]
        )

    if typ == "agent.llm_slot_wait":
        waited = _i(msg, "waited_sec") or 0
        ahead = _i(msg, "queue_ahead") or 0
        hint = f"waiting for an LLM slot ({waited}s"
        hint += f", {ahead} ahead)" if ahead else ")"
        return Update(wait_hint=hint)

    if typ == "agent.deferred_wait":
        if _s(msg, "phase") == "ended":
            return Update(clear_wait_hint=True)
        waited = _i(msg, "waited_sec") or 0
        return Update(wait_hint=f"waiting on a deferred task ({waited}s)")

    if typ == "agent.step_wait":
        return Update(
            lines=[Line("warn", "paused (step mode) — /continue to resume")],
            wait_hint="paused between rounds",
        )

    if typ == "agent.context_compacted":
        return Update(lines=[Line("dim", f"context compacted ({_s(msg, 'reason') or 'limit'})")])

    if typ == "agent.context_update":
        return Update()

    if typ in ("agent.cancelled", "agent.aborted"):
        detail = _s(msg, "detail") or "cancelled"
        return Update(lines=[Line("warn", f"cancelled: {detail}")], clear_wait_hint=True)

    if typ == "agent.done":
        return Update(clear_wait_hint=True)

    return Update()


def answer_from_completion(data: Any) -> str:
    """Pull the assistant text out of an OpenAI-shaped completion."""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        # Some providers return content as a list of parts.
        if isinstance(content, list):
            return "".join(
                str(p.get("text") or "") for p in content if isinstance(p, dict)
            ).strip()
    text = first.get("text")
    return text.strip() if isinstance(text, str) else ""
