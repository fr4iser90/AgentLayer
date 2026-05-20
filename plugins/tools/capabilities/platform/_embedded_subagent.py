"""Run an embedded ``chat_completion`` as another agent (sub-agent)."""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

DELEGATABLE_AGENT_IDS = frozenset({"coding", "coding_plan", "security_auditor"})

_PLAN_READONLY_TOOLS = [
    "coding_list_dir",
    "coding_read_file",
    "coding_glob",
    "retrieve_context",
    "coding_search",
    "coding_git_read",
    "coding_semantic_search",
    "coding_symbols",
    "coding_lsp",
    "project_explain",
]


def build_delegate_agents_catalog_snippet() -> str:
    """System-prompt block: which specialists exist and how to invoke them (no keyword routing)."""
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    lines = [
        "## Specialist sub-agents",
        "You cannot run shell, git push, or security_scan tools directly. "
        "When the user needs those capabilities, call **`agent_delegate`** with "
        "`run_subagent: true`, a specialist `agent_id`, and a full `prompt`.",
        "",
        "Available specialists:",
    ]
    for aid in ("security_auditor", "coding", "coding_plan"):
        ag = reg.get_agent(aid)
        if not ag:
            continue
        name = ag.get("name") or aid
        desc = (ag.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 240:
            desc = desc[:237] + "…"
        lines.append(f"- **{aid}** ({name}): {desc}")
    lines.append("")
    lines.append(
        "Pick the specialist by task (SSC/findings → security_auditor; "
        "edits/bash/push → coding; read-only exploration → coding_plan). "
        "Summarize the sub-agent JSON `assistant_excerpt` for the user."
    )
    return "\n".join(lines)


def _parent_llm_from_context(context: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Model + catalog provider from the parent chat turn (Web UI), not env defaults."""
    ctx = context or {}
    model = ctx.get("parent_effective_model")
    if isinstance(model, str):
        model = model.strip() or None
    else:
        model = None
    owned = ctx.get("parent_model_catalog_owned_by")
    if isinstance(owned, str):
        owned = owned.strip() or None
    else:
        owned = None
    return model, owned


def run_embedded_subagent_sync(
    *,
    subagent_agent_id: str,
    prompt: str,
    context: dict[str, Any] | None,
    tool_name: str,
    description: str,
    max_rounds: int | None = None,
    tool_allowlist: list[str] | None = None,
) -> str:
    from apps.backend.domain.agent import chat_completion
    from apps.backend.domain.identity import get_identity, reset_identity, set_identity

    aid = (subagent_agent_id or "").strip()
    if aid not in DELEGATABLE_AGENT_IDS:
        return json.dumps(
            {
                "ok": False,
                "error": f"agent_id must be one of: {', '.join(sorted(DELEGATABLE_AGENT_IDS))}",
            },
            ensure_ascii=False,
        )

    parent_tid, parent_uid = get_identity()
    u = (context or {}).get("user") if context else None
    if parent_uid is None and u is not None:
        uid = getattr(u, "id", None)
        if uid is not None:
            parent_uid = uid
            try:
                from apps.backend.infrastructure.db import db as _db

                parent_tid = _db.user_tenant_id(uid)
            except Exception:
                parent_tid = 1

    prompt = (prompt or "").strip()
    if not prompt:
        return json.dumps({"ok": False, "error": "prompt is required"}, ensure_ascii=False)

    max_r = 6
    if max_rounds is not None:
        try:
            max_r = max(1, min(int(max_rounds), 12))
        except (TypeError, ValueError):
            pass
    elif aid == "coding_plan":
        max_r = 4
    elif aid == "coding":
        max_r = 8

    parent_model, parent_catalog = _parent_llm_from_context(context)
    if not parent_model or not parent_catalog:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Sub-agent needs the parent chat model from the UI (model + provider). "
                    "Re-select the model in the chat composer and retry; "
                    "embedded runs do not use OLLAMA_DEFAULT_MODEL from env."
                ),
            },
            ensure_ascii=False,
        )

    body: dict[str, Any] = {
        "model": parent_model,
        "agent_model_catalog_owned_by": parent_catalog,
        "messages": [{"role": "user", "content": prompt}],
        "agent_id": aid,
        "agent_max_tool_rounds": max_r,
        "agent_plain_completion": False,
        "agent_unattended": True,
    }
    if aid == "coding_plan" and tool_allowlist is None:
        body["agent_tool_name_allowlist"] = list(_PLAN_READONLY_TOOLS)
    elif tool_allowlist:
        body["agent_tool_name_allowlist"] = list(tool_allowlist)

    ws = (context or {}).get("workspace") if context else None
    if isinstance(ws, dict) and ws.get("id"):
        body["workspace_id"] = str(ws["id"])

    ctx = context or {}
    ce = ctx.get("cancel_event")
    if not isinstance(ce, asyncio.Event):
        ce = None
    prid = ctx.get("agent_run_id")
    if isinstance(prid, str) and prid.strip():
        body["agent_parent_run_id"] = prid.strip()

    sub_run_id = str(uuid.uuid4())
    notify = ctx.get("agent_subagent_notify")
    detail = (description or aid).strip()[:200]
    if callable(notify):
        notify(
            {
                "type": "agent.subagent_start",
                "subagent_run_id": sub_run_id,
                "agent_id": aid,
                "tool_name": tool_name,
                "detail": detail,
            }
        )

    async def _runner() -> dict[str, Any]:
        return await chat_completion(
            body,
            event_emit=None,
            control_queue=None,
            cancel_event=ce,
            embedded_subagent=True,
        )

    def _thread_entry() -> dict[str, Any]:
        id_tok = None
        if parent_uid is not None:
            id_tok = set_identity(parent_tid, parent_uid)
        try:
            return asyncio.run(_runner())
        finally:
            if id_tok is not None:
                reset_identity(id_tok)

    ok = False
    err_msg: str | None = None
    excerpt_len = 0
    finish_reason: str | None = None
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            data = pool.submit(_thread_entry).result(timeout=600.0)
        ch0 = (data.get("choices") or [{}])[0]
        msg = ch0.get("message") or {}
        content = msg.get("content") or ""
        if not isinstance(content, str):
            content = str(content) if content is not None else ""
        content = content.strip()
        excerpt_len = len(content)
        finish_reason = ch0.get("finish_reason")
        ok = True
        result = json.dumps(
            {
                "ok": True,
                "mode": "embedded_subagent",
                "agent_id": aid,
                "assistant_excerpt": content[:12000],
                "finish_reason": finish_reason,
                "detail": "Sub-agent finished. Use assistant_excerpt in your reply to the user.",
            },
            ensure_ascii=False,
        )
    except FuturesTimeout:
        err_msg = "sub-agent timed out after 600s"
        result = json.dumps({"ok": False, "error": err_msg}, ensure_ascii=False)
    except Exception as e:
        err_msg = f"sub-agent failed: {e}"[:800]
        result = json.dumps({"ok": False, "error": err_msg}, ensure_ascii=False)
    finally:
        if callable(notify):
            notify(
                {
                    "type": "agent.subagent_done",
                    "subagent_run_id": sub_run_id,
                    "agent_id": aid,
                    "tool_name": tool_name,
                    "ok": ok,
                    "detail": err_msg or (f"finished ({excerpt_len} chars)" if ok else "finished"),
                    "result_chars": excerpt_len if ok else None,
                }
            )
    return result
