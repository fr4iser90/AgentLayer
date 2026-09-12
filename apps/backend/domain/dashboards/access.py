"""Pure dashboard feature-access rules (no IO).

Dashboards are operator-enabled globally (``operator_settings.dashboards_allowed``) and
per-user (``users.dashboards_allowed``), mirroring the scheduling feature model: admins and
site_admins always may; otherwise the per-user grant must be true. The quota cap (how many
dashboards a user may have) is enforced by the caller once access is granted.
"""

from __future__ import annotations

_FEATURE_DENIED = (
    "Dashboards are restricted unless an admin enabled dashboards for your account."
)
_QUOTA_REACHED = "Dashboard quota reached."


def dashboards_feature_denied_message() -> str:
    return _FEATURE_DENIED


def dashboards_quota_reached_message() -> str:
    return _QUOTA_REACHED


def evaluate_dashboards_access(
    *,
    user_role: str | None = None,
    site_role: str | None = None,
    dashboards_allowed: bool = False,
) -> bool:
    """Admins / site_admins always; otherwise ``dashboards_allowed`` must be true."""
    role = str(user_role or "").strip().lower()
    if role == "admin":
        return True
    if str(site_role or "").strip().lower() == "site_admin":
        return True
    return bool(dashboards_allowed)


def dashboard_permission_error_from_flags(
    *,
    user_role: str | None = None,
    site_role: str | None = None,
    dashboards_allowed: bool = False,
) -> str | None:
    if evaluate_dashboards_access(
        user_role=user_role,
        site_role=site_role,
        dashboards_allowed=dashboards_allowed,
    ):
        return None
    return _FEATURE_DENIED
