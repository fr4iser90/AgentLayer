"""Unit-test composition root for infrastructure-backed domain ports."""

from apps.backend.infrastructure.agent_runtime import agent_registry_service as _agent_registry_service  # noqa: F401
from apps.backend.infrastructure.plugins import plugin_registry_service as _plugin_registry_service  # noqa: F401
