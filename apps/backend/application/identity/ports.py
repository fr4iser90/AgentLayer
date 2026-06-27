"""Application ports for identity use cases."""
from __future__ import annotations

from apps.backend.domain.identity.repositories import TenantRepository, UserRepository

__all__ = ["TenantRepository", "UserRepository"]
