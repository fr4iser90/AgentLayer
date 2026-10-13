"""Map embedded sub-agent events to the parent WebSocket."""

from __future__ import annotations

from typing import Any


def _forward_subagent_tool_event(
    notify: Any,
    *,
    sub_run_id: str,
    agent_id: str,
    ev: dict[str, Any],
) -> None:
    """Map embedded sub-agent events to the parent WS."""
    if not callable(notify):
        return
    typ = ev.get("type")
    if typ in ("agent.deferred_wait", "agent.llm_slot_wait"):
        payload = dict(ev)
        payload.setdefault("type", typ)
        payload["subagent_run_id"] = sub_run_id
        payload["agent_id"] = agent_id
        notify(payload)
        return
    if typ == "agent.llm_delta":
        channel = str(ev.get("channel") or "").strip().lower()
        reasoning = ev.get("reasoning_delta")
        delta = ev.get("delta")
        text = ""
        if channel == "reasoning" or (isinstance(reasoning, str) and reasoning):
            text = str(reasoning or delta or "")
            out_type = "agent.subagent_reasoning"
        else:
            text = str(delta or "")
            out_type = "agent.subagent_delta"
        if not text:
            return
        notify(
            {
                "type": out_type,
                "subagent_run_id": sub_run_id,
                "agent_id": agent_id,
                "delta": text,
            }
        )
        return
    if typ not in ("agent.tool_start", "agent.tool_done"):
        return
    payload: dict[str, Any] = {
        "type": "agent.subagent_step",
        "subagent_run_id": sub_run_id,
        "agent_id": agent_id,
        "phase": "start" if typ == "agent.tool_start" else "done",
        "tool": ev.get("name"),
        "round": ev.get("round"),
    }
    if typ == "agent.tool_start":
        summary = ev.get("summary")
        if isinstance(summary, str) and summary.strip():
            payload["summary"] = summary.strip()
        step_label = ev.get("step_label")
        if isinstance(step_label, str) and step_label.strip():
            payload["step_label"] = step_label.strip()
        label = ev.get("label")
        if isinstance(label, str) and label.strip():
            payload["label"] = label.strip()
    else:
        result_ok = ev.get("result_ok")
        if result_ok is True:
            payload["ok"] = True
        elif result_ok is False:
            payload["ok"] = False
        result_error = ev.get("result_error")
        if isinstance(result_error, str) and result_error.strip():
            payload["error"] = result_error.strip()[:500]
        result_display = ev.get("result_display")
        if isinstance(result_display, str) and result_display.strip():
            payload["result_display"] = result_display.strip()[:4000]
        result_chars = ev.get("result_chars")
        if result_chars is not None:
            try:
                payload["result_chars"] = int(result_chars)
            except (TypeError, ValueError):
                pass
    notify(payload)


__all__ = ["_forward_subagent_tool_event"]
