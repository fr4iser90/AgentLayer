"""Application ports for dashboard use cases."""
from __future__ import annotations

from apps.backend.domain.dashboards.repositories import DashboardAccessRepository, DashboardRepository

__all__ = ["DashboardAccessRepository", "DashboardRepository"]
