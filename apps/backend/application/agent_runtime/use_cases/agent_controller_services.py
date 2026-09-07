from __future__ import annotations

from apps.backend.infrastructure.agent_runtime import (
    agent_artifacts_store,
    agent_config_effective,
    agent_config_fingerprint,
    agent_config_service,
    agent_config_store,
    agent_tasks_store,
)
from apps.backend.infrastructure.agent_runtime import conversation_goal_store
from apps.backend.infrastructure.agent_runtime.context_budget import (
    completion_quotas_from_budget,
    resolve_context_budget,
)
from apps.backend.infrastructure.benchmarks.benchmark_runner import start_benchmark_run
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.plugins.mcp_runtime import mcp_runtime_status
from apps.backend.infrastructure.platform import config as platform_config


def vision_availability(*, model_catalog_owned_by: str | None) -> dict:
    """True when a concrete VLM profile model is configured for the active catalog provider."""
    try:
        from apps.backend.domain.model_routing.catalog_chat import finalize_catalog_chat_llm

        effective, catalog = finalize_catalog_chat_llm(
            model="vlm",
            catalog_owned_by=model_catalog_owned_by,
            profile_key="vlm",
            is_override=False,
        )
        ok = bool(effective and effective.strip() and effective.strip().lower() != "vlm")
        return {
            "available": ok,
            "model": effective if ok else None,
            "catalog_owned_by": catalog,
            "profile_vlm_env": (platform_config.AGENT_MODEL_PROFILE_VLM or None),
        }
    except Exception as e:
        return {"available": False, "model": None, "reason": str(e)[:300]}


def load_conversation_goal_for_user(*, user_id, conversation_id):
    return conversation_goal_store.get_conversation_goal(user_id, conversation_id)


def context_tools_budget_ratio() -> float:
    """Effective ratio — a tenant knob override outranks the env constant."""
    return agent_config_effective.context_tools_budget_ratio()
