"""Organization profession RBAC controller wiring (Task 05)."""

from __future__ import annotations

from apps.backend.application.tenant_profession.use_cases.profession_policy_service import (
    effective_policy,
    ensure_tenant_profession_defaults,
)
from apps.backend.domain.tenant_profession.policy import CAP_PROFESSION_ADMIN, require_capability
from apps.backend.infrastructure.db import db

__all__ = [
    "CAP_PROFESSION_ADMIN",
    "db",
    "effective_policy",
    "ensure_tenant_profession_defaults",
    "require_capability",
]
