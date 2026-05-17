"""Run scheduled / queued work via the coding agent (``chat_completion`` + workspace)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.domain.agent import WorkspaceAccessDenied, chat_completion
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure.coding_workflow import workflow_from_row
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_MAX_INSTRUCTIONS = 31_000
_SCHEDULE_MODEL_PROFILE = "coding"
_SCHEDULE_PROVIDER_ORDER = ("llama_cpp", "ollama")


def _provider_configured(provider_id: str) -> bool:
    from apps.backend.infrastructure.model_catalog_providers import get_provider_spec

    spec = get_provider_spec(provider_id)
    return spec is not None and bool(spec.base_url.strip())


def _pick_schedule_catalog_provider() -> str | None:
    """
    Prefer a reachable coding stack for background jobs (llama.cpp before Ollama).

    Falls back to the first configured provider when health probes fail.
    Override with env ``AGENT_SCHEDULE_LLM_PROVIDER`` (e.g. ``ollama`` when only Ollama is up).
    """
    import os

    from apps.backend.infrastructure.model_catalog_providers import fetch_full_model_catalog
    from apps.backend.infrastructure.operator_settings import normalize_model_catalog_owned_by

    raw = (os.environ.get("AGENT_SCHEDULE_LLM_PROVIDER") or "").strip()
    if raw:
        forced = normalize_model_catalog_owned_by(raw)
        if forced and _provider_configured(forced):
            return forced

    _, agentlayer = fetch_full_model_catalog()
    for pid in _SCHEDULE_PROVIDER_ORDER:
        if not _provider_configured(pid):
            continue
        meta = agentlayer.get(pid)
        if isinstance(meta, dict) and meta.get("reachable") is True:
            return pid

    for pid in _SCHEDULE_PROVIDER_ORDER:
        if _provider_configured(pid):
            return pid
    return None


def _schedule_llm_body_fields(workflow: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """``chat_completion`` body fields + ``model_profile_header`` (no bare OLLAMA_DEFAULT_MODEL override)."""
    from apps.backend.infrastructure.operator_settings import normalize_model_catalog_owned_by

    extras: dict[str, Any] = {}

    explicit_owned = workflow.get("model_catalog_owned_by")
    if explicit_owned is not None and str(explicit_owned).strip():
        ob = normalize_model_catalog_owned_by(explicit_owned)
        if ob:
            extras["agent_model_catalog_owned_by"] = ob

    explicit_model = workflow.get("model")
    if explicit_model is not None and str(explicit_model).strip():
        extras["model"] = str(explicit_model).strip()[:256]
    else:
        extras["model"] = _SCHEDULE_MODEL_PROFILE

    if "agent_model_catalog_owned_by" not in extras:
        owned = _pick_schedule_catalog_provider()
        if owned:
            extras["agent_model_catalog_owned_by"] = owned
            logger.info("schedule LLM: using catalog provider %r", owned)

    return extras, _SCHEDULE_MODEL_PROFILE


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

    llm_fields, model_profile = _schedule_llm_body_fields(wf)
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
        **llm_fields,
    }

    role = db.user_role(user_id)
    id_tok = set_identity(tenant_id, user_id)
    try:
        await chat_completion(
            body,
            bearer_user_role=role if role in ("user", "admin") else None,
            model_profile_header=model_profile,
        )
    except WorkspaceAccessDenied as e:
        return False, str(e) or "workspace access denied"
    except Exception as e:
        logger.exception("coding schedule failed row_kind=%s user=%s", row_kind, user_id)
        return False, str(e)[:2000] if str(e) else "coding agent run failed"
    finally:
        reset_identity(id_tok)

    return True, None
