"""Accumulate OpenAI-compatible *streaming* ``chat/completions`` into a normal completion dict."""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from apps.backend.domain.model_routing import profile_default_model_id
from apps.backend.infrastructure.openai_compat_http import _openai_strict_tools
from apps.backend.infrastructure.operator_settings import (
    external_llm_should_failover,
    llm_chat_transport,
)
from apps.backend.infrastructure.stream_repetition_guard import guard_assistant_text

logger = logging.getLogger(__name__)


def _prepare_json_body(json_body: dict[str, Any]) -> dict[str, Any]:
    body = json_body
    if "tools" in json_body:
        body = copy.deepcopy(json_body)
        body["tools"] = _openai_strict_tools(body["tools"])
    return body


@dataclass(frozen=True)
class StreamFeedResult:
    text: str
    abort_stream: bool


class OpenAIStreamAccumulator:
    """Merge ``chat.completion.chunk`` JSON objects into a non-streaming-shaped completion."""

    __slots__ = (
        "_content_parts",
        "_tool_calls_by_index",
        "_finish_reason",
        "usage",
        "_role",
        "repetition_aborted",
    )

    def __init__(self) -> None:
        self._content_parts: list[str] = []
        self._tool_calls_by_index: dict[int, dict[str, Any]] = {}
        self._finish_reason: str | None = None
        self.usage: dict[str, Any] | None = None
        self._role: str | None = None
        self.repetition_aborted: bool = False


def _accum_usage(acc: OpenAIStreamAccumulator, chunk: dict[str, Any]) -> None:
    u = chunk.get("usage")
    if isinstance(u, dict):
        acc.usage = u


def stream_accumulator_feed(acc: OpenAIStreamAccumulator, chunk: dict[str, Any]) -> StreamFeedResult:
    """Apply one chunk; return text delta for the client and whether to abort the HTTP stream."""
    text_out_parts: list[str] = []
    choices = chunk.get("choices") or []
    if not choices:
        _accum_usage(acc, chunk)
        return StreamFeedResult("", False)
    ch0 = choices[0] if isinstance(choices[0], dict) else {}
    if not isinstance(ch0, dict):
        _accum_usage(acc, chunk)
        return StreamFeedResult("", False)
    fr = ch0.get("finish_reason")
    if isinstance(fr, str) and fr:
        acc._finish_reason = fr
    delta = ch0.get("delta")
    if not isinstance(delta, dict):
        delta = {}
    r = delta.get("role")
    if isinstance(r, str) and r:
        acc._role = r
    c = delta.get("content")
    if isinstance(c, str) and c:
        text_out_parts.append(c)
    for k in ("reasoning", "thinking"):
        v = delta.get(k)
        if isinstance(v, str) and v:
            text_out_parts.append(v)
    tcd = delta.get("tool_calls")
    if isinstance(tcd, list):
        for tc in tcd:
            if not isinstance(tc, dict):
                continue
            idx = int(tc.get("index", 0))
            cur = acc._tool_calls_by_index.setdefault(
                idx,
                {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
            )
            tid = tc.get("id")
            if isinstance(tid, str) and tid:
                cur["id"] = tid
            ttyp = tc.get("type")
            if isinstance(ttyp, str) and ttyp:
                cur["type"] = ttyp
            fn = tc.get("function")
            if isinstance(fn, dict):
                name = fn.get("name")
                if isinstance(name, str) and name:
                    cur["function"]["name"] = name
                args = fn.get("arguments")
                if isinstance(args, str) and args:
                    prev_a = cur["function"].get("arguments") or ""
                    if not isinstance(prev_a, str):
                        prev_a = ""
                    cur["function"]["arguments"] = prev_a + args
    _accum_usage(acc, chunk)

    new_text = "".join(text_out_parts)
    if new_text and not acc.repetition_aborted:
        prev = "".join(acc._content_parts)
        candidate = prev + new_text
        truncated, aborted = guard_assistant_text(candidate)
        if aborted:
            acc._content_parts = [truncated]
            acc._finish_reason = "stop"
            acc.repetition_aborted = True
            emit = truncated[len(prev) :] if len(truncated) > len(prev) else ""
            logger.info(
                "stream repetition guard: aborted stream (%d -> %d chars)",
                len(candidate),
                len(truncated),
            )
            return StreamFeedResult(emit, True)
        acc._content_parts.append(new_text)

    return StreamFeedResult(new_text if not acc.repetition_aborted else "", False)


def stream_accumulator_build_completion(acc: OpenAIStreamAccumulator) -> dict[str, Any]:
    content = "".join(acc._content_parts)
    tool_calls_list: list[dict[str, Any]] | None = None
    if acc._tool_calls_by_index:
        tool_calls_list = [acc._tool_calls_by_index[i] for i in sorted(acc._tool_calls_by_index)]
    msg: dict[str, Any] = {"role": acc._role or "assistant", "content": content if content else None}
    if msg["content"] is None and not tool_calls_list:
        msg["content"] = ""
    if tool_calls_list:
        msg["tool_calls"] = tool_calls_list
    fin = acc._finish_reason
    if not fin:
        fin = "tool_calls" if tool_calls_list else "stop"
    choice: dict[str, Any] = {
        "index": 0,
        "message": msg,
        "finish_reason": fin,
    }
    out: dict[str, Any] = {"choices": [choice]}
    if acc.usage:
        out["usage"] = acc.usage
    return out


def _extract_sse_payloads(block: str) -> list[str]:
    payloads: list[str] = []
    for line in block.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            p = line[5:].strip()
            if p and p != "[DONE]":
                payloads.append(p)
        elif line.startswith("{"):
            payloads.append(line)
    return payloads


async def _feed_chunk_async(
    acc: OpenAIStreamAccumulator,
    obj: dict[str, Any],
    on_text_delta: Callable[[str], Awaitable[None]] | None,
) -> bool:
    result = stream_accumulator_feed(acc, obj)
    if result.text and on_text_delta is not None:
        await on_text_delta(result.text)
    return result.abort_stream


async def stream_chat_completions_aggregate(
    attempts_seq: list[tuple[str, dict[str, str], str]],
    payload_base: dict[str, Any],
    *,
    llm_backend: str,
    profile_key: str,
    on_text_delta: Callable[[str], Awaitable[None]] | None,
    cancel_event: Any | None = None,
    timeout: float = 600.0,
) -> tuple[dict[str, Any], bool, tuple[str, dict[str, str], str]]:
    """
    POST ``stream: true``, parse SSE/NDJSON, merge to a completion dict.
    For each content delta, call ``on_text_delta`` (if set).
    """
    attempts_local = list(attempts_seq)
    lb = llm_backend
    outer_profile = profile_key
    timeout_cfg = httpx.Timeout(timeout, connect=120.0)

    def _cancelled() -> bool:
        if cancel_event is None:
            return False
        try:
            return bool(cancel_event.is_set())
        except Exception:
            return False

    while True:
        last_http: tuple[int, str, str] | None = None
        last_trans: httpx.RequestError | None = None
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            for b_url, b_headers, b_model in attempts_local:
                pl = dict(payload_base)
                pl["stream"] = True
                pl["model"] = b_model
                body = _prepare_json_body(pl)
                h = dict(b_headers) if b_headers else {"Content-Type": "application/json"}
                try:
                    acc = OpenAIStreamAccumulator()
                    carry = ""
                    repetition_abort = False
                    async with client.stream("POST", b_url, json=body, headers=h) as resp:
                        if resp.status_code >= 400:
                            err_body = (await resp.aread()).decode("utf-8", errors="replace")
                            if lb == "provider_admin" and external_llm_should_failover(resp.status_code):
                                logger.warning(
                                    "LLM stream agg: external status=%s; next endpoint url=%s",
                                    resp.status_code,
                                    b_url,
                                )
                                last_http = (resp.status_code, err_body, b_url)
                                continue
                            err_red = err_body[:800] if err_body else ""
                            logger.error(
                                "LLM stream agg failed (%s): status=%s url=%s body~=%s",
                                lb,
                                resp.status_code,
                                b_url,
                                err_red,
                            )
                            resp.raise_for_status()
                        async for raw in resp.aiter_bytes():
                            if repetition_abort:
                                break
                            if _cancelled():
                                from apps.backend.domain.agent import AgentChatCancelled

                                raise AgentChatCancelled()
                            carry += raw.decode("utf-8", errors="replace")
                            while "\n\n" in carry:
                                if repetition_abort:
                                    break
                                sep = carry.index("\n\n")
                                block = carry[:sep]
                                carry = carry[sep + 2 :]
                                for payload in _extract_sse_payloads(block):
                                    try:
                                        obj = json.loads(payload)
                                    except json.JSONDecodeError:
                                        continue
                                    if not isinstance(obj, dict):
                                        continue
                                    if await _feed_chunk_async(acc, obj, on_text_delta):
                                        repetition_abort = True
                                        break
                                if repetition_abort:
                                    break
                            if repetition_abort:
                                break
                        if not repetition_abort:
                            trailing = carry.strip()
                            if trailing:
                                for payload in _extract_sse_payloads(trailing):
                                    try:
                                        obj = json.loads(payload)
                                    except json.JSONDecodeError:
                                        continue
                                    if isinstance(obj, dict):
                                        if await _feed_chunk_async(acc, obj, on_text_delta):
                                            repetition_abort = True
                                            break
                    data = stream_accumulator_build_completion(acc)
                    return data, False, (b_url, b_headers, b_model)
                except httpx.HTTPStatusError:
                    raise
                except httpx.RequestError as e:
                    last_trans = e
                    logger.warning(
                        "LLM stream: chat/completions failed (llm_stack=%s url=%s model=%s): %s: %s",
                        lb,
                        b_url,
                        b_model,
                        type(e).__name__,
                        e,
                    )
                    continue
        if last_trans is not None and last_http is None:
            raise last_trans
        if last_http is not None:
            st, txt, url = last_http
            if st == 429 and lb == "provider_admin":
                local_model = profile_default_model_id(outer_profile)
                attempts_local, lb = llm_chat_transport(
                    local_model,
                    outer_profile,
                    False,
                    backend_override="provider",
                    catalog_owned_by=None,
                )
                logger.warning(
                    "LLM stream agg: external 429; falling back to local catalog provider llm_model_id=%s",
                    local_model,
                )
                continue
            req = httpx.Request("POST", url)
            raise httpx.HTTPStatusError(
                f"HTTP {st}",
                request=req,
                response=httpx.Response(st, request=req, text=txt[:8000]),
            )
        raise RuntimeError("LLM stream agg: no chat/completions attempts")
