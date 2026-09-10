from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Advisory only (Deepseek-harness-style): never disable tools / never force text-only.
_AGENT_TOOL_THRASH_HINT = (
    "You are repeating the same tool failure with the same error. Carefully analyze the previous result "
    "before calling again: fix the arguments, try a different approach, or answer the user in plain text."
)

_AGENT_TOOL_THRASH_HINT_DETAILED = (
    "Repeated identical tool failure detected. The repeated calls are not making progress. "
    "Do not call this tool with the same failing arguments again. Inspect the latest error and choose a "
    "different action, different arguments, or finish if enough evidence has been gathered."
)

_AGENT_TOOL_DOOM_LOOP_HINT = (
    "You are repeating the exact same tool call with identical arguments. Carefully analyze the previous "
    "result before calling again: if the task is not complete, try a different approach or different "
    "arguments instead of repeating the call."
)

_AGENT_TOOL_DOOM_LOOP_HINT_DETAILED = (
    "Repeated tool call detected. The repeated calls are not making progress. Do not call this tool with "
    "these exact arguments again. Inspect the latest result and choose a different action, different "
    "arguments, or finish the task if enough evidence has been gathered."
)

# Kept for import compatibility; advisory mode never injects these as a tools-disabled round.
_AGENT_TOOL_THRASH_FORCE_TEXT = _AGENT_TOOL_THRASH_HINT_DETAILED
_AGENT_TOOL_DOOM_FORCE_TEXT = _AGENT_TOOL_DOOM_LOOP_HINT_DETAILED
_AGENT_OUTPUT_ECHO_FORCE_TEXT = (
    "Identical assistant text or tool results are repeating without progress. Analyze what you already "
    "have, change approach, or finish — do not keep emitting the same output."
)

_AGENT_OUTPUT_ECHO_HINT = (
    "Identical output is repeating. Change approach (different tool args / files / commands) "
    "or answer the user in plain text — do not keep emitting the same text or re-fetching the same result."
)

_AGENT_OUTPUT_ECHO_HINT_DETAILED = _AGENT_OUTPUT_ECHO_FORCE_TEXT


def _agent_final_text_looks_like_placeholder_tool_markup(text: str) -> bool:
    """GGUF models often emit fake XML tool blocks when tools[] is omitted."""
    if not (text or "").strip():
        return True
    tl = text.lower()
    if "<tool_call" in tl or "</tool_call>" in tl:
        return True
    if "<function=" in tl or "</function>" in tl:
        return True
    if "<invoke" in tl or "</invoke>" in tl:
        return True
    if "<tool_code" in tl or "</tool_code>" in tl:
        return True
    if "<thinking" in tl or "</thinking>" in tl:
        return True
    if re.search(r"</?(?:read_file|bash|glob|list_dir|search)\b", tl):
        return True
    if re.search(r"<parameters?\b", tl):
        return True
    if re.search(r"call:default_api:", tl):
        return True
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "command" in obj and len(obj) <= 3:
            return True
    return False


def _strip_prose_fake_tool_markup(text: str) -> str:
    """Remove non-executable tool-like XML some models print when no tools[] are sent."""
    if not text:
        return text
    out = text
    for tag in (
        r"tool_call",
        r"invoke",
        r"tool_code",
        r"thinking",
        r"read_file",
        r"bash",
        r"glob",
        r"list_dir",
        r"search",
        r"parameters?",
    ):
        out = re.sub(
            rf"<{tag}\b[^>]*>[\s\S]*?</{tag}>",
            "",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(rf"</?{tag}\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<tool_call\b[^>]*>[\s\S]*?</tool_call>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</?tool_call\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<function\s*=[^>]*>\s*</function>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<function[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</function>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _sanitize_final_completion_assistant_content(data: dict[str, Any]) -> bool:
    """Strip fake tool XML from ``choices[0].message.content`` when present (mutates ``data``)."""
    try:
        ch_list = data.get("choices")
        if not isinstance(ch_list, list) or not ch_list:
            return False
        ch0 = ch_list[0]
        if not isinstance(ch0, dict):
            return False
        msg = ch0.get("message")
        if not isinstance(msg, dict):
            return False
        raw = msg.get("content")
        if not isinstance(raw, str) or not raw.strip():
            return False
        if not _agent_final_text_looks_like_placeholder_tool_markup(raw):
            return False
        stripped = _strip_prose_fake_tool_markup(raw)
        if stripped.strip():
            msg["content"] = stripped
        else:
            msg["content"] = (
                "_(The model returned tool-call markup instead of plain text — no readable answer was produced. "
                "Send a follow-up message to continue; tool results from earlier rounds are still in the transcript.)_"
            )
        msg.pop("tool_calls", None)
        ch0["message"] = msg
        ch_list[0] = ch0
        return True
    except (TypeError, KeyError, IndexError):
        return False


def _synthetic_final_llm_http_error_completion(*, status: int, model_id: str) -> dict[str, Any]:
    """Minimal OpenAI-shaped completion when the last LLM call fails (proxy 502, etc.)."""
    mid = model_id if isinstance(model_id, str) and model_id.strip() else "unknown"
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        f"_(The language model server returned **HTTP {status}** on the **final summary** round "
                        f"(model `{mid}`) — no generated answer was returned.)_\n\n"
                        "**What you can do:** wait a moment and **retry**; check **Agent activity** for outputs from "
                        "earlier tool rounds in this reply; send a **new message** asking to summarize those results "
                        "or to keep exploring (that starts a fresh tool budget)._"
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "model": mid,
    }


def _normalize_advice_thresholds(
    thresholds: list[int] | tuple[int, ...] | None = None,
    *,
    max_streak: int | None = None,
) -> tuple[int, ...]:
    """DSH-style reminder counts (default 3, 5, 8). Advisory only — never a hard stop."""
    vals: set[int] = set()
    if thresholds:
        for x in thresholds:
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if n >= 2:
                vals.add(n)
    if max_streak is not None:
        try:
            ms = int(max_streak)
        except (TypeError, ValueError):
            ms = 0
        if ms >= 2:
            vals.add(ms)
    if not vals:
        vals.update((3, 5, 8))
    return tuple(sorted(vals))


def _advice_hint_for_count(
    count: int,
    thresholds: tuple[int, ...],
    *,
    gentle: str,
    detailed: str,
) -> str | None:
    if count not in thresholds:
        return None
    return gentle if count == thresholds[0] else detailed


def _agent_tool_doom_loop_tick(
    doom_key: str | None,
    doom_count: int,
    *,
    tool_name: str,
    args: dict[str, Any],
    max_streak: int | None = None,
    thresholds: list[int] | tuple[int, ...] | None = None,
    exclude_names: frozenset[str],
    args_preview_chars: int = 500,
) -> tuple[str | None, int, str | None]:
    """
    Advisory repeat detector (same tool + same args).

    Reminds at configured thresholds; never blocks tools. Chain continues counting
    after a reminder (DSH ``repeat-tool-reminder`` semantics).
    """
    th = _normalize_advice_thresholds(thresholds, max_streak=max_streak)
    if tool_name in exclude_names:
        return doom_key, doom_count, None
    try:
        args_canon = json.dumps(dict(args), sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        args_canon = str(args)
    preview = args_canon
    if len(preview) > args_preview_chars:
        omitted = len(preview) - args_preview_chars
        preview = preview[:args_preview_chars] + f"… (+{omitted} more chars)"
    dk = f"{tool_name}|{args_canon}"
    if dk == doom_key:
        n = doom_count + 1
    else:
        dk, n = dk, 1
    hint = _advice_hint_for_count(
        n,
        th,
        gentle=_AGENT_TOOL_DOOM_LOOP_HINT,
        detailed=(
            "Repeated tool call detected:\n"
            f"- tool: `{tool_name}`\n"
            f"- consecutive_calls: {n}\n"
            f"- arguments: `{preview}`\n"
            "The repeated calls are not making progress. Do not call this tool with these exact "
            "arguments again. Inspect the latest result and choose a different action, different "
            "arguments, or finish the task if enough evidence has been gathered."
        ),
    )
    if hint:
        logger.info(
            "agent tool repeat advice: streak=%d tool=%s thresholds=%s (advisory, tools still available)",
            n,
            tool_name,
            th,
        )
    return dk, n, hint


def _tool_result_summary(result: str | None) -> tuple[bool | None, str | None]:
    """Parse leading JSON object from a tool result string: (ok, error text) or (None, None) if unknown."""
    if not result or not str(result).strip():
        return None, None
    s = result.strip()
    if not s.startswith("{"):
        return None, None
    try:
        o = json.loads(s)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(o, dict):
        return None, None
    if "ok" not in o:
        return None, None
    if o.get("ok") is True:
        return True, None
    err = o.get("error")
    if isinstance(err, str) and err.strip():
        return False, err.strip()
    return False, None


def _tool_result_followup_hint(tool_name: str, result: str | None) -> str | None:
    """System hint when a tool result needs explicit operator follow-up."""
    if not result or not str(result).strip().startswith("{"):
        return None
    try:
        o = json.loads(result)
    except json.JSONDecodeError:
        return None
    if not isinstance(o, dict):
        return None
    if tool_name == "task" and o.get("mode") == "register_only":
        warn = o.get("warning") or o.get("detail")
        if isinstance(warn, str) and warn.strip():
            return (
                "coding_task did **not** run a sub-agent — it only registered a task id. "
                f"{warn.strip()} Use **agent_delegate** with run_subagent=true for real execution."
            )
    problems = o.get("problems")
    prob_lines: list[str] = []
    if isinstance(problems, list):
        prob_lines = [str(p).strip() for p in problems if isinstance(p, str) and str(p).strip()]
    if o.get("ok") is False:
        err = o.get("error")
        if isinstance(err, str) and err.strip():
            prob_lines.insert(0, err.strip())
        hint = o.get("hint")
        if isinstance(hint, str) and hint.strip():
            prob_lines.append(hint.strip())
        if prob_lines:
            who = tool_name or "tool"
            return f"{who} failed: " + " | ".join(prob_lines[:5])
    if prob_lines and tool_name in ("delegate", "task"):
        return f"{tool_name} completed with warnings: " + " | ".join(prob_lines[:5])
    if tool_name == "delegate" and o.get("ok") is True:
        excerpt = o.get("assistant_excerpt")
        if isinstance(excerpt, str) and excerpt.strip():
            from apps.backend.domain.delegation.excerpt_quality import delegate_excerpt_is_actionable

            body = excerpt.strip()[:2000]
            if delegate_excerpt_is_actionable(excerpt):
                return (
                    "delegate succeeded. Reply to the user using the specialist result below "
                    "(summarize assistant_excerpt in natural language). "
                    "Do not call delegate again for the same task.\n\n"
                    f"assistant_excerpt:\n{body}"
                )
            return (
                "delegate returned ok but assistant_excerpt is not a usable answer "
                "(tool markup or instructions only). Retry delegate with a clearer prompt, "
                "or answer from tool results already in the sub-agent trace.\n\n"
                f"assistant_excerpt:\n{body}"
            )
    return None


async def _emit_secret_prompt_from_tool_result(
    tool_name: str,
    result: str | None,
    *,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
) -> None:
    """After ``request_user_secret``, push ``agent.secret_prompt`` to the WebSocket client."""
    if tool_name != "request_user_secret" or event_emit is None:
        return
    if not result or not str(result).strip().startswith("{"):
        return
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict) or data.get("ok") is not True:
        return
    sp = data.get("secret_prompt")
    if not isinstance(sp, dict) or not sp.get("prompt_id"):
        return
    ev: dict[str, Any] = {
        "type": "agent.secret_prompt",
        "agent_run_id": agent_run_id,
        "prompt_id": str(sp["prompt_id"]),
        "service_key": str(sp.get("service_key") or ""),
        "mode": str(sp.get("mode") or "authenticated"),
        "title": sp.get("title"),
        "help": sp.get("help"),
        "fields": sp.get("fields") if isinstance(sp.get("fields"), list) else [],
        "reason": sp.get("reason"),
    }
    scope = sp.get("scope")
    if isinstance(scope, str) and scope.strip():
        ev["scope"] = scope.strip().lower()
    wid = sp.get("workspace_id")
    if wid is not None and str(wid).strip():
        ev["workspace_id"] = str(wid).strip()
    await event_emit(ev)


def _agent_tool_thrash_tick(
    thrash_key: str | None,
    thrash_count: int,
    *,
    tool_name: str,
    ok_r: bool | None,
    err_r: str | None,
    max_streak: int | None = None,
    thresholds: list[int] | tuple[int, ...] | None = None,
) -> tuple[str | None, int, str | None]:
    """
    Advisory identical-failure detector.

    Returns ``(new_key, new_count, optional_system_hint)`` — never disables tools.
    """
    th = _normalize_advice_thresholds(thresholds, max_streak=max_streak)
    if ok_r is True:
        return None, 0, None
    if ok_r is None:
        return thrash_key, thrash_count, None
    err_norm = (err_r or "(no error text)")[:200]
    key = f"{tool_name}|{err_norm}"
    if key == thrash_key:
        n = thrash_count + 1
    else:
        n = 1
    hint = _advice_hint_for_count(
        n,
        th,
        gentle=_AGENT_TOOL_THRASH_HINT,
        detailed=_AGENT_TOOL_THRASH_HINT_DETAILED,
    )
    if hint:
        logger.info(
            "agent tool thrash advice: streak=%d tool=%s (advisory, tools still available)",
            n,
            tool_name,
        )
    return key, n, hint


def _normalize_echo_fingerprint(text: str, *, min_chars: int, max_chars: int = 4000) -> str | None:
    """Stable fingerprint for identical-output detection; None if too short to count."""
    if not text:
        return None
    collapsed = re.sub(r"\s+", " ", text.strip())
    if len(collapsed) < min_chars:
        return None
    return collapsed[:max_chars]


def _agent_assistant_output_echo_tick(
    echo_key: str | None,
    echo_count: int,
    *,
    content: str | None,
    max_streak: int | None = None,
    thresholds: list[int] | tuple[int, ...] | None = None,
    min_chars: int,
) -> tuple[str | None, int, str | None]:
    """
    Advisory identical assistant-text detector across consecutive LLM rounds.

    Short / empty content resets the streak. Never disables tools.
    """
    th = _normalize_advice_thresholds(thresholds, max_streak=max_streak)
    fp = _normalize_echo_fingerprint(content or "", min_chars=min_chars)
    if fp is None:
        return None, 0, None
    if fp == echo_key:
        n = echo_count + 1
    else:
        n = 1
    hint = _advice_hint_for_count(
        n,
        th,
        gentle=_AGENT_OUTPUT_ECHO_HINT,
        detailed=_AGENT_OUTPUT_ECHO_HINT_DETAILED,
    )
    if hint:
        logger.info(
            "agent assistant output echo advice: streak=%d chars=%d (advisory)",
            n,
            len(fp),
        )
    return fp, n, hint


def _agent_tool_result_echo_tick(
    echo_key: str | None,
    echo_count: int,
    *,
    tool_name: str,
    result: str | None,
    max_streak: int | None = None,
    thresholds: list[int] | tuple[int, ...] | None = None,
    min_chars: int,
) -> tuple[str | None, int, str | None]:
    """
    Advisory identical tool-result detector (incl. doom-excluded reads).

    Never disables tools.
    """
    th = _normalize_advice_thresholds(thresholds, max_streak=max_streak)
    body = _normalize_echo_fingerprint(result or "", min_chars=min_chars)
    if body is None:
        return None, 0, None
    key = f"{tool_name}|{body}"
    if key == echo_key:
        n = echo_count + 1
    else:
        n = 1
    hint = _advice_hint_for_count(
        n,
        th,
        gentle=_AGENT_OUTPUT_ECHO_HINT,
        detailed=_AGENT_OUTPUT_ECHO_HINT_DETAILED,
    )
    if hint:
        logger.info(
            "agent tool result echo advice: streak=%d tool=%s (advisory)",
            n,
            tool_name,
        )
    return key, n, hint


__all__ = [
    "_AGENT_OUTPUT_ECHO_FORCE_TEXT",
    "_AGENT_OUTPUT_ECHO_HINT",
    "_AGENT_OUTPUT_ECHO_HINT_DETAILED",
    "_AGENT_TOOL_DOOM_FORCE_TEXT",
    "_AGENT_TOOL_DOOM_LOOP_HINT",
    "_AGENT_TOOL_DOOM_LOOP_HINT_DETAILED",
    "_AGENT_TOOL_THRASH_FORCE_TEXT",
    "_AGENT_TOOL_THRASH_HINT",
    "_AGENT_TOOL_THRASH_HINT_DETAILED",
    "_advice_hint_for_count",
    "_agent_assistant_output_echo_tick",
    "_agent_final_text_looks_like_placeholder_tool_markup",
    "_agent_tool_doom_loop_tick",
    "_agent_tool_result_echo_tick",
    "_agent_tool_thrash_tick",
    "_emit_secret_prompt_from_tool_result",
    "_normalize_advice_thresholds",
    "_normalize_echo_fingerprint",
    "_sanitize_final_completion_assistant_content",
    "_strip_prose_fake_tool_markup",
    "_synthetic_final_llm_http_error_completion",
    "_tool_result_followup_hint",
    "_tool_result_summary",
]
