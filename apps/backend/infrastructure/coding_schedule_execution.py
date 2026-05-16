"""Run scheduled / queued work via the coding agent (``chat_completion`` + workspace)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.core.config import config
from apps.backend.domain.agent import WorkspaceAccessDenied, chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure.coding_workflow import workflow_from_row
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_MAX_INSTRUCTIONS = 31_000


def _parse_uuid(v: Any) -> uuid.UUID | None:
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v).strip())
    except (ValueError, TypeError):
        return None


async def run_coding_schedule_row(
    row: dict[str, Any],
    *,
    row_kind: str = "scheduler_job",
) -> tuple[bool, str | None]:
    """
    Execute instructions with agent_id + workspace_id from ``coding_workflow`` / legacy column.

    Returns (success, error_message).
    """
    tenant_id = int(row.get("tenant_id") or 0)
    user_id = _parse_uuid(row.get("execution_user_id"))
    if user_id is None:
        return False, "missing execution_user_id"

    wf = workflow_from_row(row)
    ws_id = _parse_uuid(wf.get("workspace_id"))
    if ws_id is None:
        return False, "coding_workflow.workspace_id is required"

    agent_id = str(wf.get("agent_id") or "coding").strip().lower()
    if agent_id not in ("coding", "coding_plan"):
        agent_id = "coding"

    title = (str(row.get("title") or "").strip()) or None
    instr = str(row.get("instructions") or "").strip()
    if not instr:
        return False, "empty instructions"

    preamble = str(wf.get("prompt_preamble") or "").strip()
    dash = row.get("dashboard_id")
    parts: list[str] = [
        f"You are executing a persisted {row_kind} (coding agent on workspace {ws_id}).",
        "Follow the instructions. Apply changes in the workspace when appropriate.",
    ]
    if title:
        parts.append(f"Title: {title}")
    if dash is not None:
        parts.append(f"Dashboard scope (id): {dash}")
    if preamble:
        parts.append(f"Additional context:\n{preamble[:12000]}")
    parts.append(f"Instructions:\n{instr[:_MAX_INSTRUCTIONS]}")
    sys_prompt = "\n\n".join(parts)

    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "Run this scheduled coding task now."},
        ],
        "stream": False,
        "agent_id": agent_id,
        "workspace_id": str(ws_id),
        "TOOL_DOMAIN": "coding",
        "agent_permission_ask": True,
        "model": str(getattr(config, "OLLAMA_DEFAULT_MODEL", "llama3.2") or "llama3.2"),
    }

    role = db.user_role(user_id)
    id_tok = set_identity(tenant_id, user_id)
    try:
        await chat_completion(
            body,
            bearer_user_role=role if role in ("user", "admin") else None,
        )
    except WorkspaceAccessDenied as e:
        return False, str(e) or "workspace access denied"
    except Exception as e:
        logger.exception("coding schedule failed row_kind=%s user=%s", row_kind, user_id)
        return False, str(e)[:2000] if str(e) else "coding agent run failed"
    finally:
        reset_identity(id_tok)

    return True, None
