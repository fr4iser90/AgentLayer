from __future__ import annotations

import json
from typing import Any

from apps.backend.domain.agent_runtime.tool_call_parsing import (
    _format_normalized_tool_args_for_recap,
    _parse_tool_arguments,
    _text_blobs_from_message,
)
from apps.backend.domain.agent_runtime.tool_schema import _normalize_tool_call_arguments

_TOOL_RECAP_HEADER = "## Tool transcript (server-extracted)"
_ROUNDS_DIGEST_HEADER = "## LLM tool rounds (server-extracted)"


def _agent_session_tool_recap_system_message(
    batch_parts: list[str],
    *,
    overflow_tail: str = "",
    user_task: str = "",
) -> str:
    """Post-tool status plus explicit user task so small models do not lose the request."""
    status = ", ".join(batch_parts) + overflow_tail
    ut = (user_task or "").strip()
    task_section = ""
    if ut:
        if len(ut) > 6000:
            ut = ut[:6000] + "\n…[truncated]"
        task_section = (
            "## User request (complete this now)\n\n"
            f"{ut}\n\n"
        )
    return (
        task_section
        + "## Server tool batch status (internal — not a user message)\n\n"
        f"Tools just executed in this reply: **{status}**.\n\n"
        "Answer the **user request** section above using the **`tool` role payloads** in the transcript. "
        "Call more tools if the task is incomplete; otherwise reply with the facts the user asked for."
    )


def _assistant_plain_text_from_message(msg: dict[str, Any]) -> str:
    return "\n".join(_text_blobs_from_message(msg)).strip()


def _tool_call_id_to_name_map(messages: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            fn = tc.get("function") or {}
            nm = str(fn.get("name") or "").strip() if isinstance(fn, dict) else ""
            if tid and nm:
                out[tid] = nm
    return out


def _tool_call_id_to_args_recap_line(messages: list[dict[str, Any]], *, max_len: int = 400) -> dict[str, str]:
    """Short, human-readable args from prior assistant ``tool_calls`` by id."""
    out: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if not isinstance(fn, dict) or not tid:
                continue
            name = str(fn.get("name") or "").strip()
            raw = fn.get("arguments")
            if raw in (None, "", "{}") or (isinstance(raw, dict) and not raw):
                if isinstance(tc.get("arguments"), (str, dict)) and tc.get("arguments") not in (None, ""):
                    raw = tc.get("arguments")
            args0 = _parse_tool_arguments(raw)
            norm = _normalize_tool_call_arguments(name, dict(args0), m, messages, None)
            out[tid] = _format_normalized_tool_args_for_recap(name, norm, max_len=max_len)
    return out


def _summarize_tool_json_body(raw: str, *, max_body: int) -> str:
    s = (raw or "").strip()
    if not s:
        return "(empty)"
    if not s.startswith("{"):
        return s[:max_body] + ("…" if len(s) > max_body else "")

    try:
        o = json.loads(s)
    except json.JSONDecodeError:
        return s[:max_body] + ("…" if len(s) > max_body else "")
    if not isinstance(o, dict):
        return s[:max_body] + ("…" if len(s) > max_body else "")

    meta: list[str] = []
    if "ok" in o:
        meta.append(f"ok={bool(o.get('ok'))}")
    for key in ("path", "pattern", "query", "path_prefix", "operation", "search_engine"):
        val = o.get(key)
        if isinstance(val, str) and val.strip():
            u = val.strip().replace("\n", " ")
            if len(u) > 220:
                u = u[:220] + "…"
            meta.append(f"{key}={u}")
    if "regex" in o and isinstance(o.get("regex"), bool):
        meta.append(f"regex={bool(o.get('regex'))}")
    ec = o.get("exit_code")
    if isinstance(ec, int) or (isinstance(ec, str) and str(ec).strip().isdigit()):
        meta.append(f"exit_code={ec}")
    if isinstance(o.get("count"), int):
        meta.append(f"count={o['count']}")
    if isinstance(o.get("files_scanned"), int):
        meta.append(f"files_scanned={o['files_scanned']}")
    if isinstance(o.get("line_count_total"), int):
        meta.append(f"line_count_total={o['line_count_total']}")
    if o.get("truncated") is True or o.get("truncated_lines") is True:
        meta.append("truncated=true")
    if o.get("truncated_matches") is True:
        meta.append("truncated_matches=true")
    if o.get("truncated_scan") is True:
        meta.append("truncated_scan=true")
    err = o.get("error")
    if isinstance(err, str) and err.strip():
        meta.append("error=" + err.strip()[:480])
    th = o.get("truncation_hint")
    if isinstance(th, str) and th.strip():
        u = th.strip().replace("\n", " ")
        meta.append("hint=" + (u[:300] + "…" if len(u) > 300 else u))
    if o.get("deduplicated") is True:
        meta.append("deduplicated=true")
    srv_note = o.get("message")
    u = (srv_note if isinstance(srv_note, str) else "").strip()
    dedup = o.get("deduplicated") is True
    if dedup:
        if u.startswith("Identical tool+arguments"):
            previews_note = (
                "server_note: _(skipped — identical tool+args; use the earlier matching result "
                "in this transcript)_"
            )
        elif u:
            previews_note = "server_note:\n" + (u if len(u) <= 400 else u[:400] + "…")
        else:
            previews_note = "server_note: _(skipped — identical tool+args)_"
    elif u:
        previews_note = "server_note:\n" + (u if len(u) <= 900 else u[:900] + "…")
    else:
        previews_note = ""

    previews: list[str] = []
    if previews_note:
        previews.append(previews_note)

    files = o.get("files")
    if isinstance(files, list) and files:
        names = [str(x).replace("\n", " ") for x in files[:45] if x is not None]
        if names:
            tail = len(files) - len(names)
            head = ", ".join(names)
            if tail > 0:
                head += f" …(+{tail} more in payload)"
            previews.append(f"files ({len(files)}): {head}")

    entries = o.get("entries")
    if isinstance(entries, list) and entries:
        bits: list[str] = []
        for ent in entries[:35]:
            if not isinstance(ent, dict):
                continue
            p = str(ent.get("path") or ent.get("name") or "").strip()
            if not p:
                continue
            suf = "/" if ent.get("is_dir") else ""
            bits.append(p + suf)
        if bits:
            tail = len(entries) - len(bits)
            line = ", ".join(bits)
            if tail > 0:
                line += f" …(+{tail} more entries)"
            previews.append(f"listing: {line}")

    matches = o.get("matches")
    if isinstance(matches, list) and matches:
        mlines: list[str] = []
        for m in matches[:14]:
            if not isinstance(m, dict):
                continue
            pth = str(m.get("path") or "").strip()
            ln = m.get("line")
            tx = m.get("text")
            ts = tx.strip()[:180] + ("…" if isinstance(tx, str) and len(tx.strip()) > 180 else "") if isinstance(tx, str) else ""
            if pth and isinstance(ln, int):
                mlines.append(f"  {pth}:{ln}: {ts}".rstrip())
            elif pth:
                mlines.append(f"  {pth}: {ts}".rstrip())
        if mlines:
            tail = len(matches) - len(mlines)
            block = "matches:\n" + "\n".join(mlines)
            if tail > 0:
                block += f"\n  …(+{tail} more matches)"
            previews.append(block)

    out_text = o.get("output")
    if isinstance(out_text, str) and out_text.strip():
        u = out_text.strip()
        previews.append("output:\n" + (u if len(u) <= max_body - 80 else u[: max_body - 80] + "…"))

    content = o.get("content")
    if isinstance(content, str) and content.strip() and "path" in o:
        u = content.strip()
        cap = min(1600, max(200, max_body - 120))
        previews.append(
            "file_content:\n"
            + (u if len(u) <= cap else u[:cap] + "…")
        )

    body = " | ".join(meta) if meta else ""
    for p in previews:
        if not p.strip():
            continue
        sep = "\n" if body else ""
        if len(body) + len(sep) + len(p) > max_body:
            room = max_body - len(body) - len(sep) - 1
            if room > 40:
                body += sep + p[:room] + "…"
            else:
                body += "\n…[preview truncated]"
            break
        body += sep + p

    if not body.strip():
        return s[:max_body] + ("…" if len(s) > max_body else "")
    if len(body) > max_body:
        return body[:max_body] + "…"
    return body


def _build_tool_transcript_recap(
    messages: list[dict[str, Any]],
    *,
    max_entries: int = 32,
    max_body_chars: int = 2200,
) -> str:
    """Deterministic markdown from ``role: tool`` payloads (JSON-aware)."""
    id_to_name = _tool_call_id_to_name_map(messages)
    id_to_args = _tool_call_id_to_args_recap_line(messages, max_len=400)
    lines: list[str] = []
    n = 0
    for m in messages:
        if m.get("role") != "tool":
            continue
        n += 1
        if n > max_entries:
            lines.append(f"\n_…{n - max_entries} more tool message(s) omitted._\n")
            break
        tid = str(m.get("tool_call_id") or "").strip()
        name = id_to_name.get(tid, "tool")
        body = m.get("content")
        text = body if isinstance(body, str) else str(body)
        summ = _summarize_tool_json_body(text, max_body=max_body_chars)
        req = (id_to_args.get(tid) or "").strip()
        if req:
            req_safe = req.replace("`", "'")
            lines.append(f"### {n}. `{name}`\n**Tool args:** `{req_safe}`\n{summ}\n")
        else:
            lines.append(f"### {n}. `{name}`\n{summ}\n")
    if not lines:
        return f"{_TOOL_RECAP_HEADER}\n\n_No tool messages in this reply._\n"
    return f"{_TOOL_RECAP_HEADER}\n\n" + "\n".join(lines)


def _build_llm_tool_rounds_digest(
    messages: list[dict[str, Any]],
    *,
    max_rounds_shown: int = 32,
    max_calls_per_round: int = 24,
    max_args_len: int = 320,
) -> str:
    """Per-assistant-turn list of tool names + normalized args."""
    blocks: list[str] = []
    r = 0
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list) or not tcs:
            continue
        r += 1
        if r > max_rounds_shown:
            blocks.append(f"_…{r - max_rounds_shown} more LLM tool round(s) omitted._")
            break
        lines: list[str] = [f"### Round {r}"]
        n_call = 0
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            n_call += 1
            if n_call > max_calls_per_round:
                rest = len(tcs) - max_calls_per_round
                lines.append(f"- _…{rest} more tool_call(s) in this round._")
                break
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if not isinstance(fn, dict):
                continue
            name = str(fn.get("name") or "").strip() or "tool"
            raw = fn.get("arguments")
            if raw in (None, "", "{}") or (isinstance(raw, dict) and not raw):
                if isinstance(tc.get("arguments"), (str, dict)) and tc.get("arguments") not in (None, ""):
                    raw = tc.get("arguments")
            args0 = _parse_tool_arguments(raw)
            norm = _normalize_tool_call_arguments(name, dict(args0), m, messages, None)
            arg_line = _format_normalized_tool_args_for_recap(name, norm, max_len=max_args_len)
            lines.append(f"- `{name}`: {arg_line}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return f"{_ROUNDS_DIGEST_HEADER}\n\n" + "\n\n".join(blocks)


def _build_client_tool_context_markdown(messages: list[dict[str, Any]]) -> str:
    """LLM tool rounds plus tool transcript for the client-facing reply."""
    digest = _build_llm_tool_rounds_digest(messages).strip()
    recap = _build_tool_transcript_recap(messages).strip()
    if digest and recap:
        return digest + "\n\n" + recap
    return digest or recap


def _client_reply_is_only_server_tool_context_prefix(tail: str) -> bool:
    t = (tail or "").strip()
    if not t:
        return True
    return t.startswith(_TOOL_RECAP_HEADER) or t.startswith(_ROUNDS_DIGEST_HEADER)


def _merge_deterministic_tool_recap_into_final_completion(
    data: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    plain_completion: bool,
) -> bool:
    """Prefix assistant content with server recap when the tool loop ends."""
    if plain_completion:
        return False
    try:
        recap = _build_client_tool_context_markdown(messages)
        if not recap.strip():
            return False
        cap = 18_000
        recap_use = recap if len(recap) <= cap else recap[:cap] + "\n\n…[truncated]"
        ch_list = data.get("choices")
        if not isinstance(ch_list, list) or not ch_list:
            return False
        ch0 = ch_list[0]
        if not isinstance(ch0, dict):
            return False
        msg0 = ch0.get("message")
        if not isinstance(msg0, dict):
            return False
        ex = msg0.get("content")
        if ex is None:
            msg0["content"] = ""
            ex = ""
        elif not isinstance(ex, str):
            return False
        tail = ex.strip()
        sep = "\n\n---\n\n### Model reply\n\n"
        if not tail or _client_reply_is_only_server_tool_context_prefix(tail):
            msg0["content"] = recap_use.strip()[:80_000]
        else:
            merged = (recap_use.rstrip() + sep + tail).strip()
            if len(merged) > 80_000:
                merged = merged[:80_000] + "…"
            msg0["content"] = merged
        msg0.pop("tool_calls", None)
        ch0["message"] = msg0
        ch_list[0] = ch0
        return True
    except (TypeError, KeyError, IndexError):
        return False


__all__ = [
    "_ROUNDS_DIGEST_HEADER",
    "_TOOL_RECAP_HEADER",
    "_agent_session_tool_recap_system_message",
    "_assistant_plain_text_from_message",
    "_build_client_tool_context_markdown",
    "_build_llm_tool_rounds_digest",
    "_build_tool_transcript_recap",
    "_client_reply_is_only_server_tool_context_prefix",
    "_merge_deterministic_tool_recap_into_final_completion",
    "_summarize_tool_json_body",
    "_tool_call_id_to_args_recap_line",
    "_tool_call_id_to_name_map",
]
