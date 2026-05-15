"""Delegate a subtask to a subagent session."""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Callable, cast

__version__ = "1.0.0"
TOOL_ID = "coding_task"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding task", "subagent", "delegate")
TOOL_CAPABILITIES = ("coding.task",)
TOOL_LABEL = "Coding: Task"
TOOL_DESCRIPTION = (
    "Delegate a subtask. Two modes: (1) Default: register a pending task_id (lightweight). "
    "(2) **run_plan_subagent=true**: run a bounded **coding_plan** read-only planner in a side thread "
    "(same workspace + identity) and return its assistant text excerpt — embedded runs cannot use approval UI, "
    "so only read/search tools are allowed there."
)

_active_tasks: dict[str, dict[str, Any]] = {}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


_PLAN_SUBAGENT_READONLY_TOOLS = [
    "coding_list_dir",
    "coding_read_file",
    "coding_glob",
    "coding_search",
    "coding_git_read",
    "coding_semantic_search",
    "coding_symbols",
    "coding_lsp",
    "project_explain",
]


def _execute_plan_subagent_sync(arguments: dict[str, Any], context: dict[str, Any] | None) -> str:
    """Run ``chat_completion`` as **coding_plan** in a fresh thread + ``asyncio.run`` (avoids nested event loops)."""
    from apps.backend.core.config import config as cfg
    from apps.backend.domain.agent import chat_completion
    from apps.backend.domain.identity import get_identity, reset_identity, set_identity

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

    prompt = (arguments.get("prompt") or "").strip()
    if not prompt:
        return json.dumps(
            {"ok": False, "error": "prompt is required when run_plan_subagent is true"},
            ensure_ascii=False,
        )
    task_id = (arguments.get("task_id") or "").strip()
    if task_id and task_id in _active_tasks:
        meta = _active_tasks[task_id]
        desc = (meta.get("description") or "").strip()
        prev_p = (meta.get("prompt") or "").strip()
        if desc or prev_p:
            block = f"[Registered task {task_id!r}]\n"
            if desc:
                block += f"Description: {desc}\n"
            if prev_p:
                block += "Original instructions:\n" + prev_p.strip() + "\n"
            block += "\n---\nThis run (follow these now):\n"
            prompt = (block + prompt).strip()
    max_r = 4
    try:
        raw_mr = arguments.get("max_rounds")
        if raw_mr is not None:
            max_r = max(1, min(int(raw_mr), 8))
    except (TypeError, ValueError):
        pass
    model = (arguments.get("subagent_model") or "").strip() or cfg.OLLAMA_DEFAULT_MODEL
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "agent_id": "coding_plan",
        "agent_max_tool_rounds": max_r,
        "agent_plain_completion": False,
        # Embedded run has no WebSocket ``control_queue`` — lock to read-only tools (no silent bash/write).
        "agent_tool_name_allowlist": list(_PLAN_SUBAGENT_READONLY_TOOLS),
    }
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

    async def _runner() -> dict[str, Any]:
        return await chat_completion(
            body,
            event_emit=None,
            control_queue=None,
            cancel_event=ce,
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

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            data = pool.submit(_thread_entry).result(timeout=600.0)
    except FuturesTimeout:
        return json.dumps(
            {"ok": False, "error": "plan subagent timed out after 600s"},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": f"plan subagent failed: {e}"[:800]},
            ensure_ascii=False,
        )
    ch0 = (data.get("choices") or [{}])[0]
    msg = ch0.get("message") or {}
    content = msg.get("content") or ""
    if not isinstance(content, str):
        content = ""
    content = content.strip()
    return json.dumps(
        {
            "ok": True,
            "mode": "plan_subagent",
            "agent_id": "coding_plan",
            "assistant_excerpt": content[:12000],
            "finish_reason": ch0.get("finish_reason"),
            "detail": (
                "Read-only sub-run finished. Use assistant_excerpt with your reasoning; "
                "use the Coding agent and write/shell tools to apply changes."
            ),
        },
        ensure_ascii=False,
    )


def coding_task(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    if _truthy(arguments.get("run_plan_subagent")):
        return _execute_plan_subagent_sync(arguments, context)

    description = (arguments.get("description") or "").strip()
    if not description:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "coding_task requires non-empty **description** and **prompt**. "
                    r'Example: {"description": "Analyze README", "prompt": "Read README.md and suggest updates."}'
                ),
            },
            ensure_ascii=False,
        )
    prompt = (arguments.get("prompt") or "").strip()
    if not prompt:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "coding_task requires **prompt** (full instructions for the subtask). "
                    r'Same example: {"description": "…", "prompt": "…"}'
                ),
            },
            ensure_ascii=False,
        )
    task_id = (arguments.get("task_id") or "").strip()
    if task_id and task_id in _active_tasks:
        existing = _active_tasks[task_id]
        return json.dumps(
            {
                "ok": False,
                "error": f"task_id {task_id!r} already exists. Use a different description or wait for completion.",
                "existing_task": existing,
            },
            ensure_ascii=False,
        )
    new_id = f"task-{uuid.uuid4().hex[:12]}"
    _active_tasks[new_id] = {
        "id": new_id,
        "description": description,
        "prompt": prompt,
        "status": "pending",
        "parent_id": arguments.get("_parent_id"),
    }
    return json.dumps(
        {
            "ok": True,
            "task_id": new_id,
            "description": description,
            "status": "pending",
            "detail": (
                f"Task {new_id!r} registered. "
                "Set run_plan_subagent=true on a later call to execute a read-only coding_plan pass, "
                "or use the Coding (plan) agent from the UI."
            ),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "coding_task": cast(Callable[..., str], coding_task),
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_task",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "A short (3-5 words) description of the task",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The full task prompt/instructions for the subagent",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Optional. With run_plan_subagent: merge context from a prior coding_task registration with this id. Default mode: resume collision check only.",
                    },
                    "run_plan_subagent": {
                        "type": "boolean",
                        "description": "If true, run a bounded read-only coding_plan sub-planner (requires prompt; uses workspace from context).",
                    },
                    "max_rounds": {
                        "type": "integer",
                        "description": "Max tool rounds for plan subagent (1–8, default 4) when run_plan_subagent is true",
                    },
                    "subagent_model": {
                        "type": "string",
                        "description": "Ollama model id for the plan subagent (optional; defaults to OLLAMA_DEFAULT_MODEL)",
                    },
                },
                "required": ["description", "prompt"],
            },
        },
    },
]
