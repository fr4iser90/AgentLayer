"""Deterministic OpenAI-shaped chat completions for E2E (``AGENT_E2E_MOCK_LLM=1``)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any


def e2e_mock_llm_enabled() -> bool:
    raw = (os.environ.get("AGENT_E2E_MOCK_LLM") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _tool_result_count(messages: list[Any]) -> int:
    n = 0
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "tool":
            n += 1
    return n


def build_mock_chat_completion(body: dict[str, Any]) -> dict[str, Any]:
    """First round with tools → ``list_dir``; second round → plain assistant text."""
    messages = body.get("messages") or []
    tools = body.get("tools") or []
    tool_rounds = _tool_result_count(messages if isinstance(messages, list) else [])

    if tools and tool_rounds == 0:
        call_id = f"call_e2e_{uuid.uuid4().hex[:12]}"
        return {
            "id": f"chatcmpl-e2e-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": "list_dir",
                                    "arguments": json.dumps({"path": "."}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    return {
        "id": f"chatcmpl-e2e-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "E2E mock LLM complete.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 3, "total_tokens": 4},
    }


def mock_sse_chunks(body: dict[str, Any]) -> list[bytes]:
    """Minimal SSE byte chunks for streaming mock (one delta + [DONE])."""
    data = build_mock_chat_completion(body)
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    tool_calls = msg.get("tool_calls")
    cid = data["id"]
    chunks: list[bytes] = []
    if tool_calls:
        tc = tool_calls[0]
        chunks.append(
            (
                f'data: {json.dumps({"id": cid, "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": [{"index": 0, "id": tc["id"], "type": "function", "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}]}, "finish_reason": None}]})}\n\n'
            ).encode()
        )
        chunks.append(
            (
                f'data: {json.dumps({"id": cid, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})}\n\n'
            ).encode()
        )
    elif content:
        chunks.append(
            (
                f'data: {json.dumps({"id": cid, "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]})}\n\n'
            ).encode()
        )
        chunks.append(
            (
                f'data: {json.dumps({"id": cid, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})}\n\n'
            ).encode()
        )
    chunks.append(b"data: [DONE]\n\n")
    return chunks
