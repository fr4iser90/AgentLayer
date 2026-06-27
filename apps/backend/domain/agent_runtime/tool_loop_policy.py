from __future__ import annotations

from typing import Any

from apps.backend.domain.plugin_system.tool_routing import last_user_text


def _agent_tool_budget_system_message(max_rounds: int) -> str:
    """Injected once per agent tool-loop request so models know the exact server cap."""
    n = max(1, int(max_rounds))
    if n <= 1:
        return (
            "## Tool-loop budget (server)\n\n"
            "This reply allows **only one** tool-loop LLM round (one completion; optional tool_calls). "
            "Use tools only if needed, then answer — the user can continue in a **new message** if more rounds are required."
        )
    return (
        "## Tool-loop budget (server)\n\n"
        f"- The server allows **at most {n}** tool-loop LLM rounds for this assistant reply (counting this completion).\n"
        "- **This is round 1** — `tools[]` is available; use `tool_calls` when needed to answer the **latest user message**.\n"
        "- Avoid empty `{}` tool JSON (often normalizes to identical calls and can trigger loop guards).\n\n"
        "If work is unfinished, say so explicitly — the user may send a follow-up message."
    )


def _agent_near_max_tool_rounds_reminder(current_round: int, max_rounds: int) -> str:
    """Shown the round before the final text-only round (requires max_rounds >= 3)."""
    return (
        f"You are in **LLM tool-loop round {current_round} of {max_rounds}**. "
        f"The **next** round ({current_round + 1}) is the **last**; it will be **text-only** (no tools in the API). "
        "Finish critical tool calls **this** round if you still need them, or prepare a complete plain-text "
        "wrap-up on the next turn."
    )


def _agent_final_round_text_only_hint(current_round: int, max_rounds: int) -> str:
    """Shown immediately before the final LLM call (no tools[])."""
    return (
        f"**Round {current_round} of {max_rounds}** — final tool-loop round: **no** `tools[]` will be sent. "
        "Reply with **plain Markdown only** — the API **never** runs tools from prose. "
        "**Never** write `<tool_call>`, `</tool_call>`, `<function=…>`, or similar XML.\n\n"
        "**You must do exactly one of:**\n"
        "(A) **Synthesize** everything useful from **existing** `tool` messages above (findings, errors, paths, "
        "open questions, next steps for the user); **or**\n"
        "(B) If the transcript is **not** enough to answer, say that plainly and tell the user to send **one new "
        "message** to continue (a new request gets a fresh tool budget — you cannot call more tools in this reply).\n\n"
        "Do not stall with vague intent to explore — either recap what you already have, or ask for a follow-up."
    )


def _rewrite_delegatable_agent_tool_alias(
    name: str,
    args: dict[str, Any],
    *,
    allowed_names: set[str] | frozenset[str],
    messages: list[dict[str, Any]],
    caller_is_admin: bool = False,
) -> tuple[str, dict[str, Any]] | None:
    """Map ``agent_id`` used as tool name (e.g. ``math``) to ``delegate`` when allowed."""
    n = (name or "").strip()
    if not n or n in allowed_names or "delegate" not in allowed_names:
        return None
    from apps.backend.domain.agent_runtime.subagent_catalog import effective_delegatable_agent_ids

    if n not in effective_delegatable_agent_ids(caller_is_admin=caller_is_admin):
        return None
    prompt = ""
    for key in ("prompt", "expression", "query", "task", "message"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            prompt = val.strip()
            break
    if not prompt:
        prompt = (last_user_text(messages) or "").strip()
    if not prompt:
        return None
    return (
        "delegate",
        {
            "agent_id": n,
            "prompt": prompt,
            "run_subagent": True,
        },
    )


__all__ = [
    "_agent_final_round_text_only_hint",
    "_agent_near_max_tool_rounds_reminder",
    "_agent_tool_budget_system_message",
    "_rewrite_delegatable_agent_tool_alias",
]
