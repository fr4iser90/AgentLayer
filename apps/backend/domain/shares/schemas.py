"""Sharing schema validation."""
from __future__ import annotations


def validate_share_role(role: str) -> str:
    value = role.strip().lower()
    if value not in {"viewer", "editor", "owner"}:
        raise ValueError("share role must be viewer, editor, or owner")
    return value


def validate_grantee(grantee: str) -> str:
    value = grantee.strip()
    if not value:
        raise ValueError("share grantee must not be blank")
    return value
