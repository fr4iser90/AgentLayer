"""Pure schedules feature-access rules (no IO)."""

from __future__ import annotations

_FEATURE_DENIED = (
    "Schedules are restricted to admins unless an admin enables schedules_allowed for your account."
)


def schedules_feature_denied_message() -> str:
    return _FEATURE_DENIED


def evaluate_schedules_access(
    *,
    site_role: str | None = None,
    schedules_allowed: bool = False,
) -> bool:
    """Site admins always; otherwise ``schedules_allowed`` must be true.

    ``site_role`` is the only elevation source here (ADR 0011 §1). The legacy
    ``users.role`` has no parameter to be passed into: an account demoted by
    ``site_role='site_user'`` keeps the feature only through the per-user grant,
    which is the one an admin can actually revoke.
    """
    if str(site_role or "").strip().lower() == "site_admin":
        return True
    return bool(schedules_allowed)


def schedule_feature_permission_error_from_flags(
    *,
    site_role: str | None = None,
    schedules_allowed: bool = False,
) -> str | None:
    if evaluate_schedules_access(
        site_role=site_role,
        schedules_allowed=schedules_allowed,
    ):
        return None
    return _FEATURE_DENIED
