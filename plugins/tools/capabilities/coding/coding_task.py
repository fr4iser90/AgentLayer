"""Delegate a subtask to a subagent session."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, cast

from plugins.tools.capabilities.platform._embedded_subagent import run_embedded_subagent_sync

__version__ = "1.0.0"
TOOL_ID = "coding_task"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding task", "subagent", "delegate")
TOOL_CAPABILITIES = ("coding.task",)
TOOL_LABEL = "Coding: Task"
TOOL_DESCRIPTION = (
    "Delegate a subtask. (1) Default: register a pending task_id. "
    "(2) run_plan_subagent=true: read-only coding_plan sub-run. "
    "For security_auditor or full coding builds prefer **agent_delegate** with run_subagent=true."
)

_active_tasks: dict[str, dict[str, Any]] = {}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


def coding_task(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    if _truthy(arguments.get("run_plan_subagent")):
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
        return run_embedded_subagent_sync(
            subagent_agent_id="coding_plan",
            prompt=prompt,
            context=context,
            tool_name="coding_task",
            description=(arguments.get("description") or "Plan sub-agent").strip()[:200],
            max_rounds=arguments.get("max_rounds"),
        )

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
                "Use run_plan_subagent=true or agent_delegate for a live sub-agent run."
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
                        "description": "Optional. With run_plan_subagent: merge context from a prior coding_task registration with this id.",
                    },
                    "run_plan_subagent": {
                        "type": "boolean",
                        "description": "If true, run a bounded read-only coding_plan sub-agent (requires prompt).",
                    },
                    "max_rounds": {
                        "type": "integer",
                        "description": "Max tool rounds for plan subagent (1–8, default 4) when run_plan_subagent is true",
                    },
                },
                "required": ["description", "prompt"],
            },
        },
    },
]
