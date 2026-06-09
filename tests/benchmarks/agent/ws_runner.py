"""WebSocket chat runner — captures compaction/tool timeline during benchmarks."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _http_to_ws_base(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or parsed.path
    return f"{scheme}://{host}"


async def _run_chat_ws_async(
    *,
    base_url: str,
    token: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("websockets package required for timeline capture") from exc

    ws_base = _http_to_ws_base(base_url)
    ws_url = f"{ws_base}/ws/v1/chat?token={token}"
    events: list[dict[str, Any]] = []
    completion: dict[str, Any] = {}
    error: str | None = None

    async with websockets.connect(ws_url, open_timeout=30, close_timeout=10) as ws:
        await ws.send(json.dumps({"type": "chat", "body": body}))
        while True:
            raw = await ws.recv()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            events.append(msg)
            typ = msg.get("type")
            if typ == "chat.completion":
                data = msg.get("data")
                if isinstance(data, dict):
                    completion = data
                elif msg.get("error"):
                    error = str(msg.get("detail") or "chat.completion error")
                break
            if typ == "error":
                error = str(msg.get("detail") or "websocket error")
                break

    return completion, events, error


def run_chat_via_websocket(
    *,
    base_url: str,
    token: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    return asyncio.run(
        _run_chat_ws_async(
            base_url=base_url,
            token=token,
            body=body,
        )
    )


def timeline_capture_enabled(explicit: bool | None = None) -> bool:
    import os

    if explicit is not None:
        return explicit
    return (os.environ.get("AGENT_BENCH_CAPTURE_TIMELINE") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
