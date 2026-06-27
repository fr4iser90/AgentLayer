"""Infrastructure adapter for agent task prompt artifact lookups."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain import agent_task_prompt as domain
from apps.backend.infrastructure import agent_artifacts_store


class _AgentTaskPromptDeps:
    @staticmethod
    def get_artifact(*, artifact_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
        return agent_artifacts_store.get_artifact(artifact_id=artifact_id, tenant_id=tenant_id)


domain.register_agent_task_prompt_dependencies(_AgentTaskPromptDeps())

build_agent_tasks_context_snippet = domain.build_agent_tasks_context_snippet
build_artifact_context_block = domain.build_artifact_context_block
enrich_delegate_prompt = domain.enrich_delegate_prompt
format_requirements_block = domain.format_requirements_block
infer_plan_delegate_mode = domain.infer_plan_delegate_mode
parse_delegate_mode = domain.parse_delegate_mode
