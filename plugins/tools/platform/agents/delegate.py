"""Delegate work to a specialist agent (coding, security_auditor, coding_plan)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, cast

from apps.backend.domain.embedded_subagent import (
    DELEGATABLE_AGENT_IDS,
    build_delegate_agents_catalog_snippet,
    run_embedded_subagent_sync,
)

__version__ = "1.0.0"
TOOL_ID = "delegate"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "delegate"
TOOL_TRIGGERS = ("delegate", "subagent", "specialist", "security auditor", "coding agent")
TOOL_CAPABILITIES = ("meta.delegate",)
TOOL_LABEL = "Delegate to specialist agent"
TOOL_DESCRIPTION = (
    "Run a specialist sub-agent in the background and return its report. "
    "Use when the user needs security scans (security_auditor), repo edits/shell/git (coding), "
    "read-only codebase exploration (coding_plan), HTML/image creative work (creative), "
    "or dashboard boards (dashboard). Requires run_subagent=true, agent_id, prompt."
)


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


def _sanitize_task_id(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or len(s) > 64:
        return None
    try:
        uuid.UUID(s)
        return s
    except (ValueError, TypeError):
        return None


def delegate(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    if _truthy(arguments.get("list_agents")):
        return json.dumps(
            {
                "ok": True,
                "catalog": build_delegate_agents_catalog_snippet(),
                "agent_ids": sorted(DELEGATABLE_AGENT_IDS),
            },
            ensure_ascii=False,
        )

    if not _truthy(arguments.get("run_subagent")):
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Set run_subagent=true to execute. Required: agent_id "
                    f"({', '.join(sorted(DELEGATABLE_AGENT_IDS))}), description, prompt. "
                    "Or list_agents=true to see specialists."
                ),
            },
            ensure_ascii=False,
        )

    prompt = (arguments.get("prompt") or "").strip()
    description = (arguments.get("description") or "").strip() or "Specialist sub-agent"
    agent_id = (arguments.get("agent_id") or "").strip()

    artifact_refs = arguments.get("artifact_refs")
    if not isinstance(artifact_refs, list):
        artifact_refs = None
    requirements = arguments.get("requirements")
    if not isinstance(requirements, list):
        requirements = None
    task_id = _sanitize_task_id(arguments.get("task_id"))

    return run_embedded_subagent_sync(
        subagent_agent_id=agent_id,
        prompt=prompt,
        context=context,
        tool_name="delegate",
        description=description,
        artifact_refs=artifact_refs,
        requirements=requirements,
        task_id=task_id,
    )


def tool_step_detail(arguments: dict[str, Any]) -> str:
    aid = str(arguments.get("agent_id") or "").strip()
    desc = str(arguments.get("description") or "").strip()
    return desc or aid


HANDLERS: dict[str, Callable[..., str]] = {
    "delegate": cast(Callable[..., str], delegate),
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "delegate",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "list_agents": {
                        "type": "boolean",
                        "description": "If true, return available specialist agent_ids and descriptions (no run).",
                    },
                    "run_subagent": {
                        "type": "boolean",
                        "description": "If true, run the specialist sub-agent and return assistant_excerpt.",
                    },
                    "agent_id": {
                        "type": "string",
                        "enum": sorted(DELEGATABLE_AGENT_IDS),
                        "description": "Specialist to run: security_auditor (SSC/scans), coding (shell/edits/push), coding_plan (read-only).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Short label for the UI (3–8 words).",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Full instructions for the specialist sub-agent.",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Optional tasks UUID to attach run output as artifact.",
                    },
                    "artifact_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Artifact UUIDs to inject as context (instead of huge chat history).",
                    },
                    "requirements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Structured requirements passed to the sub-agent.",
                    },
                },
                "required": [],
            },
        },
    },
]
