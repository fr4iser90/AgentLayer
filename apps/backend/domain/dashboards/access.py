"""Pure dashboard feature-access rules (no IO).

Dashboards are operator-enabled globally (``operator_settings.dashboards_allowed``) and
per-user (``users.dashboards_allowed``), mirroring the scheduling feature model: site admins
always may; otherwise the per-user grant must be true. The quota cap (how many dashboards a
user may have) is enforced by the caller once access is granted.
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
    site_role: str | None = None,
    dashboards_allowed: bool = False,
) -> bool:
    """Site admins always; otherwise ``dashboards_allowed`` must be true.

    ``site_role`` is the only elevation source here (ADR 0011 §1). This rule used to take
    ``user_role`` as well and returned ``True`` for it before ever reaching ``site_role``, so
    a demoted account — ``site_role='site_user'``, legacy ``users.role`` still ``admin``,
    which a demotion does not rewrite — kept the dashboards it was just denied. There is
    deliberately no parameter for that value: callers resolve ``site_role`` through
    ``db.user_site_role``.
    """
    if str(site_role or "").strip().lower() == "site_admin":
        return True
    return bool(dashboards_allowed)
