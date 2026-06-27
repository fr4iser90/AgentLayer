from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.agent_runtime.governance import (
    AgentAccessPolicy,
    normalize_access_state,
    resolve_agent_access,
)
from apps.backend.domain.agent_runtime.registry import effective_tool_names_for_caller, get_agent_registry
from apps.backend.infrastructure.agent_runtime import agent_access_policy_store
from apps.backend.infrastructure.agent_runtime.agent_config_effective import merge_agent_definition
from apps.backend.infrastructure.agent_runtime import agent_prompt_version_store


def _policy_from_row(row: dict[str, Any]) -> AgentAccessPolicy:
    return AgentAccessPolicy(
        scope=str(row.get("scope") or "global"),  # type: ignore[arg-type]
        tenant_id=int(row["tenant_id"]) if row.get("tenant_id") is not None else None,
        user_id=str(row["user_id"]) if row.get("user_id") is not None else None,
        agent_id=str(row.get("agent_id") or ""),
        direct_state=normalize_access_state(row.get("direct_state")),
        delegate_state=normalize_access_state(row.get("delegate_state")),
    )


def _prompt_stats(agent: dict[str, Any]) -> dict[str, Any]:
    prompt = str(agent.get("system_prompt") or "")
    chars = len(prompt)
    approx_tokens = max(1, chars // 4) if prompt.strip() else 0
    return {
        "chars": chars,
        "approx_tokens": approx_tokens,
        "source": agent.get("source_path") or "registry",
        "effective_source": agent.get("system_prompt_source") or "file_default",
        "published_version": agent.get("system_prompt_version"),
        "published_version_id": agent.get("system_prompt_version_id"),
        "editable": True,
        "editing_mode": "draft_publish",
        "note": "Prompt edits are saved as tenant drafts and only affect runtime after publish.",
    }


def list_agent_policy_rows(
    *,
    tenant_id: int | None,
    user_id: uuid.UUID | None = None,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    return agent_access_policy_store.list_agent_policies(
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=agent_id,
    )


def list_agent_prompt_versions(*, tenant_id: int, agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
    return agent_prompt_version_store.list_prompt_versions(
        tenant_id=tenant_id,
        agent_id=agent_id,
        limit=limit,
    )


def resolve_agent_governance(
    *,
    agent_id: str,
    user_role: str,
    tenant_id: int | None,
    user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    reg = get_agent_registry()
    agent = reg.get_agent(agent_id)
    if not agent:
        raise KeyError(agent_id)
    agent = merge_agent_definition(agent, tenant_id=tenant_id)
    policy_rows = list_agent_policy_rows(tenant_id=tenant_id, user_id=user_id, agent_id=agent_id)
    policies = [_policy_from_row(row) for row in policy_rows]
    decision = resolve_agent_access(agent=agent, user_role=user_role, policies=policies)
    return {
        "access": {
            "agent_id": decision.agent_id,
            "direct_allowed": decision.direct_allowed,
            "delegate_allowed": decision.delegate_allowed,
            "direct_reason": decision.direct_reason,
            "delegate_reason": decision.delegate_reason,
            "direct_source": decision.direct_source,
            "delegate_source": decision.delegate_source,
        },
        "policies": policy_rows,
        "prompt": _prompt_stats(agent),
        "system_prompt": str(agent.get("system_prompt") or ""),
        "effective_tool_names": effective_tool_names_for_caller(
            agent_id,
            user_role=user_role,
            tenant_id=tenant_id,
        ),
    }


def upsert_agent_access_policy(
    *,
    scope: str,
    agent_id: str,
    direct_state: str,
    delegate_state: str,
    tenant_id: int | None,
    user_id: uuid.UUID | None,
    notes: str | None,
    updated_by: uuid.UUID | None,
) -> dict[str, Any]:
    reg = get_agent_registry()
    if not reg.get_agent(agent_id):
        raise KeyError(agent_id)
    return agent_access_policy_store.upsert_agent_policy(
        scope=scope,
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=agent_id,
        direct_state=direct_state,
        delegate_state=delegate_state,
        notes=notes,
        updated_by=updated_by,
    )


def delete_agent_access_policy(
    *,
    scope: str,
    agent_id: str,
    tenant_id: int | None,
    user_id: uuid.UUID | None,
) -> bool:
    return agent_access_policy_store.delete_agent_policy(
        scope=scope,
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=agent_id,
    )


def create_agent_prompt_draft(
    *,
    tenant_id: int,
    agent_id: str,
    prompt_text: str,
    notes: str | None,
    created_by: uuid.UUID | None,
) -> dict[str, Any]:
    reg = get_agent_registry()
    if not reg.get_agent(agent_id):
        raise KeyError(agent_id)
    return agent_prompt_version_store.create_prompt_draft(
        tenant_id=tenant_id,
        agent_id=agent_id,
        prompt_text=prompt_text,
        notes=notes,
        created_by=created_by,
    )


def publish_agent_prompt_version(
    *,
    tenant_id: int,
    agent_id: str,
    version_id: uuid.UUID,
    published_by: uuid.UUID | None,
) -> dict[str, Any]:
    reg = get_agent_registry()
    if not reg.get_agent(agent_id):
        raise KeyError(agent_id)
    return agent_prompt_version_store.publish_prompt_version(
        tenant_id=tenant_id,
        agent_id=agent_id,
        version_id=version_id,
        published_by=published_by,
    )
