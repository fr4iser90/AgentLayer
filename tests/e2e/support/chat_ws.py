"""WebSocket chat helpers for E2E agent tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from tests.e2e.support.helpers import ws_url


async def collect_ws_chat_events(
    token: str,
    chat_body: dict[str, Any],
    *,
    timeout_s: float = 180.0,
) -> list[dict[str, Any]]:
    import websockets

    events: list[dict[str, Any]] = []
    uri = ws_url(token)
    async with websockets.connect(uri, open_timeout=15, close_timeout=5) as ws:
        await ws.send(json.dumps({"type": "chat", "body": chat_body}))
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
            except asyncio.TimeoutError:
                break
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            events.append(ev)
            if ev.get("type") == "error":
                break
            if ev.get("type") in ("chat.completion", "agent.done"):
                break
    return events


def ws_events_as_text(events: list[dict[str, Any]]) -> str:
    """Flatten all WS event payloads to one string (includes user prompt — prefer ``agent_leak_scan_text``)."""
    return json.dumps(events, ensure_ascii=False, default=str)


def _messages_from_completion_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return out
    for key in ("messages",):
        raw = data.get(key)
        if isinstance(raw, list):
            out.extend(m for m in raw if isinstance(m, dict))
    choice0 = (data.get("choices") or [None])[0]
    if isinstance(choice0, dict):
        msg = choice0.get("message")
        if isinstance(msg, dict):
            out.append(msg)
    return out


def agent_leak_scan_text(events: list[dict[str, Any]]) -> str:
    """
    Text from assistant / tool / LLM deltas only — excludes the red-team user prompt
    (which intentionally mentions the probe key name).
    """
    parts: list[str] = []
    for ev in events:
        typ = ev.get("type")
        if typ == "agent.llm_delta":
            parts.append(str(ev.get("delta") or ""))
            parts.append(str(ev.get("reasoning_delta") or ""))
        elif typ == "agent.tool_done":
            parts.append(str(ev.get("result_error") or ""))
        elif typ == "chat.completion":
            data = ev.get("data")
            if isinstance(data, dict):
                for msg in _messages_from_completion_data(data):
                    role = str(msg.get("role") or "")
                    if role in ("assistant", "tool", "system"):
                        content = msg.get("content")
                        if isinstance(content, str):
                            parts.append(content)
                        elif content is not None:
                            parts.append(json.dumps(content, ensure_ascii=False))
    return "\n".join(parts)


def first_catalog_model(client) -> dict[str, Any]:
    models_resp = client.get_json("/v1/models")
    rows = models_resp.get("data") if isinstance(models_resp, dict) else None
    if not rows or not isinstance(rows, list):
        raise RuntimeError("no models in GET /v1/models — configure LLM_PROVIDER_* or Admin LLM")
    row = rows[0]
    if not isinstance(row, dict) or not row.get("id"):
        raise RuntimeError(f"invalid model row: {row!r}")
    return row
