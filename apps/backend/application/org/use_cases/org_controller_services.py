"""Organization controller wiring."""

from __future__ import annotations

from apps.backend.application.rag.use_cases import rag_controller_services as rag_ctrl
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.public_error import http_500_detail
from apps.backend.infrastructure.settings import operator_settings

__all__ = ["db", "http_500_detail", "operator_settings", "rag_ctrl"]
