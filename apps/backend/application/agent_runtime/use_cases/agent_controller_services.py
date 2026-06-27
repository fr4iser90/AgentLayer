from __future__ import annotations

from apps.backend.infrastructure.agent_runtime import (
    agent_artifacts_store,
    agent_config_effective,
    agent_config_fingerprint,
    agent_config_service,
    agent_config_store,
    agent_tasks_store,
)
from apps.backend.infrastructure.agent_runtime.context_budget import (
    completion_quotas_from_budget,
    resolve_context_budget,
)
from apps.backend.infrastructure.benchmarks.benchmark_runner import start_benchmark_run
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.plugins.mcp_runtime import mcp_runtime_status
