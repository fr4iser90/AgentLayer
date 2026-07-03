"""Tenant provisioning controller wiring (Task 07)."""

from __future__ import annotations

from apps.backend.application.tenant_provisioning.use_cases import tenant_provision_service as provision
from apps.backend.application.tenant_provisioning.use_cases.tenant_template_loader import (
    list_templates_public,
)
from apps.backend.infrastructure.db import db

__all__ = ["db", "list_templates_public", "provision"]
