"""Infrastructure adapter for trusted HTTP/WebSocket identity resolution."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.shared import http_identity as domain
from apps.backend.infrastructure.identity.auth import get_user_for_bearer_token
from apps.backend.infrastructure.db import db


class _HttpIdentityDeps:
    @staticmethod
    def get_user_for_bearer_token(token: str) -> Any | None:
        return get_user_for_bearer_token(token)

    @staticmethod
    def user_tenant_id(user_id: uuid.UUID) -> int:
        return db.user_tenant_id(user_id)


domain.register_http_identity_dependencies(_HttpIdentityDeps())

resolve_chat_identity = domain.resolve_chat_identity
resolve_chat_identity_ws = domain.resolve_chat_identity_ws
resolve_tools_list_identity = domain.resolve_tools_list_identity
