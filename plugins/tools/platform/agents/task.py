"""Register or run bounded subagent work from a coding/build session (not agent_tasks backlog)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, cast

from apps.backend.domain.embedded_subagent import run_embedded_subagent_sync
from apps.backend.domain.delegate_enforcement import subagent_reject_reason

__version__ = "1.0.0"
TOOL_ID = "task"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "delegate"
TOOL_TRIGGERS = ("coding task", "subagent", "run_plan_subagent")
TOOL_CAPABILITIES = ("coding.task",)
TOOL_LABEL = "Subagent task"
TOOL_DESCRIPTION = (
    "Delegate a subtask from a coding session. (1) Default: register a pending task_id. "
    "(2) run_plan_subagent=true: read-only coding_plan sub-run. "
    "For security_auditor or full coding builds prefer **delegate** with run_subagent=true."
)

_active_tasks: dict[str, dict[str, Any]] = {}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


def task(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
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
        reject = subagent_reject_reason(
            agent_id="coding_plan",
            requirements=arguments.get("requirements"),
        )
        if reject:
            return json.dumps({"ok": False, "error": reject}, ensure_ascii=False)
        return run_embedded_subagent_sync(
            subagent_agent_id="coding_plan",
            prompt=prompt,
            context=context,
            tool_name="task",
            description=(arguments.get("description") or "Plan sub-agent").strip()[:200],
            requirements=arguments.get("requirements"),
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
            "mode": "register_only",
            "executed": False,
            "task_id": new_id,
            "description": description,
            "status": "pending",
            "warning": (
                "No sub-agent was started — this only registered a task id. "
                "For real execution use agent_delegate with run_subagent=true "
                "or coding_task with run_plan_subagent=true."
            ),
            "detail": (
                f"Task {new_id!r} registered only (no code was run). "
                "Use agent_delegate (run_subagent=true) for security_auditor/coding, "
                "or coding_task with run_plan_subagent=true for read-only planning."
            ),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "task": cast(Callable[..., str], task),
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "task",
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
                },
                "required": ["description", "prompt"],
            },
        },
    },
]
