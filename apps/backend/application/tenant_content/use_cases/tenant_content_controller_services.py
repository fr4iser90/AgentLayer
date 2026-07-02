"""Tenant CMS controller wiring (Task 04–06)."""

from __future__ import annotations

from apps.backend.application.tenant_content.use_cases import tenant_content_service as cms
from apps.backend.application.tenant_profession.use_cases.profession_policy_service import (
    effective_policy,
)
from apps.backend.domain.tenant_profession.policy import (
    CAP_CONTENT_EDITOR,
    CAP_CONTENT_REVIEW,
    content_visible_to_policy,
    require_capability,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.identity.auth import get_current_user
from apps.backend.infrastructure.platform.public_error import http_500_detail
from apps.backend.infrastructure.settings import operator_settings

__all__ = [
    "CAP_CONTENT_EDITOR",
    "CAP_CONTENT_REVIEW",
    "cms",
    "content_visible_to_policy",
    "db",
    "effective_policy",
    "get_current_user",
    "http_500_detail",
    "operator_settings",
    "require_capability",
]
