"""Access decision infrastructure."""
from apps.backend.infrastructure.access.entity_access_service import (
    DASHBOARD,
    SUPPORTED_ENTITY_TYPES,
    WORKSPACE,
    can_access,
    can_access_workspace_row,
    tenant_layer_allows,
)

__all__ = [
    "DASHBOARD",
    "SUPPORTED_ENTITY_TYPES",
    "WORKSPACE",
    "can_access",
    "can_access_workspace_row",
    "tenant_layer_allows",
]
