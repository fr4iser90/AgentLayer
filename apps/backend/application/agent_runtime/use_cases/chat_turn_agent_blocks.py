"""Agent-conditional system blocks injected before the model call (goal, catalog, skills)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.application.agent_runtime.dependencies import (
    build_knowledge_orchestration_snippet,
    build_media_library_context_snippet,
    load_combined_skills_prompt,
)
from apps.backend.application.agent_runtime.use_cases.upload_storage_images import (
    storage_upload_prompt as _storage_upload_prompt,
)
from apps.backend.domain.agent_runtime.persona import _append_system_block

logger = logging.getLogger(__name__)

__all__ = [
    "agent_goal_tool_names",
    "inject_agent_catalog_blocks",
    "inject_conversation_goal_block",
    "inject_knowledge_orchestration_block",
]


def agent_goal_tool_names(agent_id: str | None) -> frozenset[str]:
    """Goal/todo tools this agent may call — empty when the agent is unknown."""
    from apps.backend.domain.agent_runtime.registry import get_agent_registry
    from apps.backend.domain.agent_runtime.conversation_goal import (
        GOAL_TOOLS,
        PLAN_TOOLS,
        TODO_TOOLS,
    )

    if not agent_id:
        return frozenset()
    agent = get_agent_registry().get_agent(agent_id)
    if not agent:
        return frozenset()
    names = {str(n).strip() for n in (agent.get("tool_names") or [])}
    return frozenset(names & (GOAL_TOOLS | TODO_TOOLS | PLAN_TOOLS))


def inject_conversation_goal_block(
    messages: list[dict[str, Any]],
    *,
    agent_id: str | None,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Tell the agent which goal/todo tools it has and what the current goal/todos are."""
    from apps.backend.domain.agent_runtime.conversation_goal import (
        PLAN_MODE_GUIDANCE,
        conversation_goal_prompt_block,
    )
    from apps.backend.infrastructure.agent_runtime import conversation_goal_store as goal_store

    state = goal_store.get_conversation_goal(user_id, conversation_id)
    if not state:
        return messages
    goal_tools = agent_goal_tool_names(agent_id)
    if not goal_tools:
        # Agentless chats resolve tools per turn, so naming tools would be a guess.
        if state.get("plan_mode"):
            return _append_system_block(
                messages, PLAN_MODE_GUIDANCE, kind="conversation_goal", label="Plan mode"
            )
        return messages
    block = conversation_goal_prompt_block(
        tool_names=goal_tools,
        goal=state.get("goal") if isinstance(state.get("goal"), dict) else None,
        todos=state.get("todos") if isinstance(state.get("todos"), list) else [],
        plan_mode=bool(state.get("plan_mode")),
    )
    return (
        _append_system_block(
            messages, block, kind="conversation_goal", label="Goal / todos / plan"
        )
        if block
        else messages
    )


def inject_agent_catalog_blocks(
    messages: list[dict[str, Any]],
    *,
    agent_id: str | None,
    user_id: Any,
    tenant_id: int | None,
    is_admin: bool,
    active_task_id: str | None,
    plain_completion: bool,
    agent_delegate_mode: str | None,
    agent_storage_images: list[dict[str, Any]],
    ingested_audio: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Snippets that only certain agents get: profession capsule, uploads, delegate catalog, skills."""
    user_uuid = user_id if isinstance(user_id, uuid.UUID) else None

    if agent_id == "knowledge_companion" and user_uuid is not None and tenant_id is not None:
        from apps.backend.application.tenant_profession.use_cases.profession_policy_service import (
            build_profession_capsule,
        )

        capsule = build_profession_capsule(user_uuid, int(tenant_id))
        if capsule:
            messages = _append_system_block(
                messages, capsule, kind="profession", label="Profession capsule"
            )
    if agent_storage_images:
        messages = _append_system_block(
            messages,
            _storage_upload_prompt(agent_storage_images),
            kind="storage_upload",
            label="Storage uploads",
        )
    if agent_id == "general":
        from apps.backend.application.agent_runtime.runtime.embedded_subagent import (
            build_delegate_agents_catalog_snippet,
        )

        messages = _append_system_block(
            messages,
            build_delegate_agents_catalog_snippet(
                caller_is_admin=is_admin,
                tenant_id=int(tenant_id) if tenant_id is not None else None,
                user_id=user_uuid,
            ),
            kind="delegate_catalog",
            label="Delegate catalog",
        )
        from apps.backend.domain.agent_runtime.task_prompt import build_agent_tasks_context_snippet

        tasks_snip = build_agent_tasks_context_snippet(active_task_id=active_task_id)
        if tasks_snip:
            messages = _append_system_block(
                messages, tasks_snip, kind="agent_tasks", label="Agent tasks"
            )
    if agent_id in ("general", "dashboard") and user_id is not None and tenant_id is not None:
        _media_snip = build_media_library_context_snippet(
            user_id=user_uuid,
            tenant_id=int(tenant_id),
            ingested_audio=ingested_audio,
            caller_is_admin=is_admin,
        )
        if _media_snip:
            messages = _append_system_block(
                messages, _media_snip, kind="media_library", label="Media library"
            )
    if agent_id and not plain_completion:
        skills_snip = load_combined_skills_prompt(
            agent_id, delegate_mode=agent_delegate_mode
        )
        if skills_snip:
            messages = _append_system_block(
                messages, skills_snip, kind="skills", label="Skills"
            )
    return messages


def inject_knowledge_orchestration_block(
    messages: list[dict[str, Any]],
    *,
    agent_id: str | None,
    cfg_tid: int | None,
) -> list[dict[str, Any]]:
    """Coding agents get the tenant knowledge-orchestration snippet (best effort)."""
    if agent_id not in ("coding", "coding_plan"):
        return messages
    try:
        _knowledge_snip = build_knowledge_orchestration_snippet(tenant_id=cfg_tid)
        if _knowledge_snip:
            return _append_system_block(
                messages,
                _knowledge_snip,
                kind="knowledge_orchestration",
                label="Knowledge orchestration",
            )
    except Exception:
        logger.debug("knowledge orchestration prompt skipped", exc_info=True)
    return messages
