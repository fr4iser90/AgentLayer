"""WebSocket chat runner — captures compaction/tool timeline during benchmarks."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_RECV_POLL_SEC = 1.0
_CANCEL_DRAIN_SEC = 15.0


def _http_to_ws_base(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or parsed.path
    return f"{scheme}://{host}"



async def _drain_after_cancel(ws: Any, events: list[dict[str, Any]], on_event: Callable | None) -> tuple[dict[str, Any], str | None]:
    completion: dict[str, Any] = {}
    error: str | None = "Benchmark cancelled"
    deadline = time.monotonic() + _CANCEL_DRAIN_SEC
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(2.0, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            break
        except Exception:
            break
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        events.append(msg)
        if on_event is not None:
            on_event(msg)
        typ = msg.get("type")
        if typ == "chat.completion":
            data = msg.get("data")
            if isinstance(data, dict):
                completion = data
            if msg.get("error"):
                error = str(msg.get("detail") or msg.get("message") or error)
            else:
                error = error
            break
        if typ in ("error", "agent.aborted", "agent.cancelled"):
            error = str(msg.get("detail") or msg.get("message") or error)
            break
    return completion, error


async def _run_chat_ws_async(
    *,
    base_url: str,
    token: str,
    body: dict[str, Any],
    on_event: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    timeout_sec: float | None = None,
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
    started = time.monotonic()
    cancel_sent = False

    async with websockets.connect(ws_url, open_timeout=30, close_timeout=10) as ws:
        await ws.send(json.dumps({"type": "chat", "body": body}))
        while True:
            if cancel_check and cancel_check() and not cancel_sent:
                cancel_sent = True
                await ws.send(json.dumps({"type": "cancel"}))
                completion, error = await _drain_after_cancel(ws, events, on_event)
                break
            if timeout_sec is not None and timeout_sec > 0:
                elapsed = time.monotonic() - started
                if elapsed >= timeout_sec:
                    if not cancel_sent:
                        cancel_sent = True
                        await ws.send(json.dumps({"type": "cancel"}))
                    completion, error = await _drain_after_cancel(ws, events, on_event)
                    if not error or error == "Benchmark cancelled":
                        error = f"scenario timeout after {int(timeout_sec)}s"
                    break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=_RECV_POLL_SEC)
            except asyncio.TimeoutError:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            events.append(msg)
            if on_event is not None:
                on_event(msg)
            typ = msg.get("type")
            if typ == "chat.completion":
                if msg.get("error"):
                    error = str(msg.get("detail") or msg.get("message") or "chat.completion error")
                    break
                data = msg.get("data")
                if isinstance(data, dict):
                    completion = data
                else:
                    error = str(msg.get("detail") or "chat.completion missing data")
                break
            if typ == "error":
                detail = msg.get("detail") or msg.get("message") or "websocket error"
                status = msg.get("http_status")
                error = f"{detail}" + (f" (HTTP {status})" if status else "")
                break
            if typ in ("agent.aborted", "agent.cancelled"):
                error = str(msg.get("detail") or typ.replace("agent.", ""))
                break

    return completion, events, error


def run_chat_via_websocket(
    *,
    base_url: str,
    token: str,
    body: dict[str, Any],
    on_event: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    timeout_sec: float | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    return asyncio.run(
        _run_chat_ws_async(
            base_url=base_url,
            token=token,
            body=body,
            on_event=on_event,
            cancel_check=cancel_check,
            timeout_sec=timeout_sec,
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
