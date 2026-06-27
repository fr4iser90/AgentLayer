"""Infrastructure adapter for delegate enforcement artifact lookups."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.delegation import enforcement as domain
from apps.backend.infrastructure.agent_runtime import agent_artifacts_store


class _DelegateEnforcementDeps:
    @staticmethod
    def get_artifact(*, artifact_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
        return agent_artifacts_store.get_artifact(artifact_id=artifact_id, tenant_id=tenant_id)


domain.register_delegate_enforcement_dependencies(_DelegateEnforcementDeps())

coding_delegate_tool_blocked = domain.coding_delegate_tool_blocked
general_orchestrator_tool_blocked = domain.general_orchestrator_tool_blocked
load_delegate_allowed_paths = domain.load_delegate_allowed_paths
parse_requirement_value = domain.parse_requirement_value
subagent_reject_reason = domain.subagent_reject_reason
