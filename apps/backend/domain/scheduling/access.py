"""Pure schedules feature-access rules (no IO)."""

from __future__ import annotations

_FEATURE_DENIED = (
    "Schedules are restricted to admins unless an admin enables schedules_allowed for your account."
)


def schedules_feature_denied_message() -> str:
    return _FEATURE_DENIED


def evaluate_schedules_access(
    *,
    user_role: str | None = None,
    site_role: str | None = None,
    schedules_allowed: bool = False,
) -> bool:
    """Admins / site_admins always; otherwise ``schedules_allowed`` must be true."""
    role = str(user_role or "").strip().lower()
    if role == "admin":
        return True
    if str(site_role or "").strip().lower() == "site_admin":
        return True
    return bool(schedules_allowed)


def schedule_feature_permission_error_from_flags(
    *,
    user_role: str | None = None,
    site_role: str | None = None,
    schedules_allowed: bool = False,
) -> str | None:
    if evaluate_schedules_access(
        user_role=user_role,
        site_role=site_role,
        schedules_allowed=schedules_allowed,
    ):
        return None
    return _FEATURE_DENIED
