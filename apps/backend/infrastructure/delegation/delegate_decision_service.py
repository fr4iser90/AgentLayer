"""Infrastructure adapter for delegate decision LLM calls."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.delegation import decision as domain
from apps.backend.infrastructure.agent_runtime.catalog_llm_client import post_catalog_chat_completions


class _DelegateDecisionDeps:
    @staticmethod
    def post_catalog_chat_completions(**kwargs: Any) -> tuple[dict[str, Any], Any]:
        return post_catalog_chat_completions(**kwargs)


domain.register_delegate_decision_dependencies(_DelegateDecisionDeps())

run_delegate_decision = domain.run_delegate_decision
