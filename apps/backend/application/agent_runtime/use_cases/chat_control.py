from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.runtime.prompts import AgentChatCancelled
from apps.backend.domain.agent_runtime.tool_catalog import _tools_for_chat_request
from apps.backend.domain.agent_runtime.tool_schema import _registry_tool_spec_by_registered_name
from apps.backend.domain.agent_runtime.tool_catalog import _tool_spec_name

logger = logging.getLogger(__name__)


class ChatControlQueue:
    def __init__(
        self,
        *,
        messages: list[dict[str, Any]],
        tools_for_request: list[Any],
        tools_full_schema: bool,
        control_queue: asyncio.Queue | None,
        cancel_event: asyncio.Event | None,
        event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
        agent_run_id: str,
        max_tool_rounds_eff: int,
    ) -> None:
        self.messages = messages
        self.tools_for_request = tools_for_request
        self.tools_full_schema = tools_full_schema
        self.control_queue = control_queue
        self.cancel_event = cancel_event
        self.event_emit = event_emit
        self.agent_run_id = agent_run_id
        self.max_tool_rounds_eff = max_tool_rounds_eff

    def merge_add_tools_from_message(self, names: list[Any]) -> None:
        existing = {
            x for x in (_tool_spec_name(s) for s in self.tools_for_request) if x
        }
        for raw in names:
            nn = str(raw).strip()
            if not nn or nn in existing:
                continue
            if nn in config.AGENT_TOOLS_DENYLIST:
                continue
            sp = _registry_tool_spec_by_registered_name(nn)
            if not sp:
                continue
            slim = _tools_for_chat_request([sp], full_schema=self.tools_full_schema)
            if slim:
                self.tools_for_request.append(slim[0])
                existing.add(nn)

    def handle_control_dict(self, m: dict[str, Any]) -> bool:
        """Apply cancel/add_tools. Returns True if cancel was requested."""
        t = m.get("type")
        if t == "cancel" and self.cancel_event is not None:
            self.cancel_event.set()
            from apps.backend.domain.agent_runtime.run_cancel import signal_parent_cancel

            signal_parent_cancel(self.agent_run_id)
            return True
        if t == "add_tools":
            raw_names = m.get("names")
            nlist = raw_names if isinstance(raw_names, list) else []
            self.merge_add_tools_from_message(nlist)
        return False

    async def drain(self) -> None:
        if self.control_queue is None:
            return
        while True:
            try:
                m = self.control_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not isinstance(m, dict):
                continue
            if m.get("type") == "continue_step":
                logger.debug("discarding stray continue_step (not in agent.step_wait)")
                continue
            if m.get("type") == "permission_reply":
                logger.debug("discarding stray permission_reply (not waiting for permission)")
                continue
            if m.get("type") == "secret_saved" and m.get("ok") is True:
                sk = str(m.get("service_key") or "").strip().lower()
                if sk:
                    self.messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"[User saved secret via UI] service_key={sk} — "
                                "do not ask for this key again; retry the integration tool that failed."
                            ),
                        }
                    )
                continue
            self.handle_control_dict(m)

    async def wait_for_continue_step_after_round(self, completed_round: int) -> None:
        if self.control_queue is None:
            return
        if self.event_emit:
            await self.event_emit(
                {
                    "type": "agent.step_wait",
                    "agent_run_id": self.agent_run_id,
                    "after_round": completed_round,
                    "next_round": completed_round + 1,
                    "max_rounds": self.max_tool_rounds_eff,
                    "detail": (
                        "Send a frame {\"type\":\"continue_step\"} to start the next LLM round. "
                        "You may send {\"type\":\"add_tools\",\"names\":[\"...\"]} before that."
                    ),
                }
            )
        while True:
            m = await self.control_queue.get()
            if not isinstance(m, dict):
                continue
            if m.get("type") == "permission_reply":
                logger.debug("discarding permission_reply during step_wait")
                continue
            if m.get("type") == "continue_step":
                await self.drain()
                if self.cancel_event is not None and self.cancel_event.is_set():
                    if self.event_emit:
                        await self.event_emit(
                            {
                                "type": "agent.cancelled",
                                "agent_run_id": self.agent_run_id,
                                "phase": "step_wait",
                                "round": completed_round + 1,
                            }
                        )
                    raise AgentChatCancelled()
                return
            if self.handle_control_dict(m):
                if self.event_emit:
                    await self.event_emit(
                        {
                            "type": "agent.cancelled",
                            "agent_run_id": self.agent_run_id,
                            "phase": "step_wait",
                            "round": completed_round + 1,
                        }
                    )
                raise AgentChatCancelled()


__all__ = ["ChatControlQueue"]
