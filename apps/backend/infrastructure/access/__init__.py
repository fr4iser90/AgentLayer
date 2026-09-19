"""Access decision infrastructure."""
from apps.backend.infrastructure.access.entity_access_service import (
    DASHBOARD,
    SUPPORTED_ENTITY_TYPES,
    WORKSPACE,
    can_access,
)

__all__ = [
    "DASHBOARD",
    "SUPPORTED_ENTITY_TYPES",
    "WORKSPACE",
    "can_access",
]
