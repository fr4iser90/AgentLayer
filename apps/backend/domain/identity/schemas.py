"""Identity input validation helpers."""
from __future__ import annotations

from apps.backend.domain.identity.value_objects import EmailAddress, TenantId, UserRole


def validate_email(raw: str) -> EmailAddress:
    return EmailAddress.parse(raw)


def validate_tenant_id(raw: int) -> TenantId:
    return TenantId(int(raw))


def validate_user_role(raw: str) -> UserRole:
    role = (raw or "").strip().lower()
    if role not in ("user", "admin"):
        raise ValueError("user role must be 'user' or 'admin'")
    return role  # type: ignore[return-value]
