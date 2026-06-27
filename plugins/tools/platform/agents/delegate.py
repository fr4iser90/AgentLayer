"""Delegate work to a specialist agent (coding, security_auditor, coding_plan)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, cast

from apps.backend.application.agent_runtime.runtime.embedded_subagent import (
    build_delegate_agents_catalog_snippet,
    caller_is_admin,
    effective_delegatable_agent_ids,
    run_embedded_subagent_sync,
)
from apps.backend.domain.shared.identity import get_identity

__version__ = "1.0.0"
TOOL_ID = "delegate"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "delegate"
# Router phrases: co-located delegate.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("meta.delegate",)
TOOL_LABEL = "Delegate to specialist agent"
TOOL_DESCRIPTION = (
    "Run a specialist sub-agent in the background and return its report. "
    "Use list_agents=true to see available agent_id values. "
    "Requires run_subagent=true, agent_id, prompt."
)


def _delegatable_ids_for_context(context: dict[str, Any] | None) -> frozenset[str]:
    ctx = context or {}
    uid = None
    tid = None
    u = ctx.get("user")
    if u is not None:
        uid = getattr(u, "id", None)
        tid = getattr(u, "tenant_id", None)
    if uid is None:
        tid, uid = get_identity()
    if tid is None and ctx.get("tenant_id") is not None:
        tid = ctx.get("tenant_id")
    try:
        tid_i = int(tid) if tid is not None else None
    except (TypeError, ValueError):
        tid_i = None
    is_adm = caller_is_admin(uid if isinstance(uid, uuid.UUID) else None)
    return effective_delegatable_agent_ids(
        caller_is_admin=is_adm,
        tenant_id=tid_i,
        user_id=uid if isinstance(uid, uuid.UUID) else None,
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
    from apps.backend.infrastructure.settings.operator_settings import delegate_enabled as _delegate_enabled

    if not _delegate_enabled():
        return json.dumps(
            {"ok": False, "error": "delegate is disabled in operator settings (delegate_enabled=false)"},
            ensure_ascii=False,
        )
    allowed = _delegatable_ids_for_context(context)
    if _truthy(arguments.get("list_agents")):
        uid = None
        tid = None
        u = (context or {}).get("user")
        if u is not None:
            uid = getattr(u, "id", None)
            tid = getattr(u, "tenant_id", None)
        if uid is None:
            tid, uid = get_identity()
        if tid is None and context and context.get("tenant_id") is not None:
            tid = context.get("tenant_id")
        try:
            tid_i = int(tid) if tid is not None else None
        except (TypeError, ValueError):
            tid_i = None
        is_adm = caller_is_admin(uid if isinstance(uid, uuid.UUID) else None)
        return json.dumps(
            {
                "ok": True,
                "catalog": build_delegate_agents_catalog_snippet(
                    caller_is_admin=is_adm,
                    tenant_id=tid_i,
                    user_id=uid if isinstance(uid, uuid.UUID) else None,
                ),
                "agent_ids": sorted(allowed),
            },
            ensure_ascii=False,
        )

    prompt = (arguments.get("prompt") or "").strip()
    description = (arguments.get("description") or "").strip() or "Specialist sub-agent"
    agent_id = (arguments.get("agent_id") or "").strip()

    if not _truthy(arguments.get("run_subagent")):
        if agent_id and prompt:
            arguments = dict(arguments)
            arguments["run_subagent"] = True
        else:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "Set run_subagent=true to execute. Required: agent_id "
                        f"({', '.join(sorted(allowed))}), description, prompt. "
                        "Or list_agents=true to see specialists."
                    ),
                },
                ensure_ascii=False,
            )

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
                        "description": (
                            "Specialist agent_id (coding, coding_plan, security_auditor, creative, "
                            "dashboard, math, operator for admins). Use list_agents=true for the full list."
                        ),
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
