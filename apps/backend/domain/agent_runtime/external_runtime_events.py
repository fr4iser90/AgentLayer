"""Translate normalized external-runtime events into AgentLayer chat events.

Pure mapping, so both consumers of an external runtime get identical UI behaviour:

* driven as the **primary** runtime of a conversation → payloads go straight to
  ``event_emit`` and the existing web client renders them;
* driven through ``delegate`` → ``domain/agent_runtime/subagent_events.py`` rewrites the
  same payloads into ``agent.subagent_step`` / ``agent.subagent_delta`` for the child card.

``step_label`` carries a monotonic sequence number on purpose: the client pairs tool
durations by tool *name* (``agentChatWsCore.ts`` ``toolStartTimes``, ``buildRunCards.ts``
``openTools``), so an external agent that calls ``shell`` five times would otherwise
overwrite its own rows.
"""

from __future__ import annotations

from typing import Any

from apps.backend.domain.agent_runtime.external_runtime import ExternalRuntimeEvent

_MAX_SUMMARY_CHARS = 240
_MAX_DISPLAY_CHARS = 2000


def _clip(text: str, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: max(0, limit - 1)].rstrip() + "…"


class ExternalEventTranslator:
    """Stateful so ``round`` and ``step_label`` stay stable across one run."""

    def __init__(self, agent_run_id: str) -> None:
        self.agent_run_id = agent_run_id
        self.round = 0
        self._seq = 0
        self._open_tool: str | None = None

    def translate(self, event: ExternalRuntimeEvent) -> list[dict[str, Any]]:
        kind = str(event.kind or "")
        if kind == "delta":
            if not event.text:
                return []
            return [
                {
                    "type": "agent.llm_delta",
                    "agent_run_id": self.agent_run_id,
                    "round": self.round,
                    "delta": event.text,
                }
            ]
        if kind == "tool_call":
            self._seq += 1
            name = str(event.tool or "tool").strip() or "tool"
            self._open_tool = name
            summary = _clip(event.args_preview or event.text or name, _MAX_SUMMARY_CHARS)
            return [
                {
                    "type": "agent.tool_start",
                    "agent_run_id": self.agent_run_id,
                    "round": self.round,
                    "name": name,
                    "summary": summary,
                    "step_label": f"{name} #{self._seq}",
                    "rejected": False,
                }
            ]
        if kind == "tool_result":
            name = str(event.tool or self._open_tool or "tool").strip() or "tool"
            out: list[dict[str, Any]] = [
                {
                    "type": "agent.tool_done",
                    "agent_run_id": self.agent_run_id,
                    "round": self.round,
                    "name": name,
                    "result_chars": len(event.text or ""),
                    "result_ok": bool(event.ok),
                }
            ]
            if not event.ok:
                out[0]["result_error"] = _clip(event.error or event.text or "failed", 500)
            elif event.text:
                out[0]["result_display"] = _clip(event.text, _MAX_DISPLAY_CHARS)
            self._open_tool = None
            self.round += 1
            return out
        # ``status``/``done``/``error`` are terminal or log-only: the caller turns them
        # into ``agent.done`` / the completion dict, and unknown WS types would render
        # as raw JSON lines in the client.
        return []


__all__ = ["ExternalEventTranslator"]
