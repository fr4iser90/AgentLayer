"""Platform/admin scope RBAC — per-user capabilities (P6, Weg B).

Global (tenant-independent) administrative capabilities granted to individual
users. These gate the People/People-admin surfaces and per-person agent
assignment, independent of any tenant.

The evaluation here is pure; the :mod:`require_admin_capability` guard in the
auth layer reads the stored capability set for a user and delegates to
:func:`evaluate_access`. Content/knowledge RBAC lives in
:mod:`domain.tenant_profession.policy` and is a separate axis.
"""

from __future__ import annotations

from typing import Iterable

# Platform/admin capabilities. A site admin implicitly holds every capability;
# non-site-admins must be granted each one explicitly on ``users.capabilities``.
CAP_AGENT_ASSIGN = "agent.assign"
CAP_USER_MANAGE = "user.manage"
CAP_WORKSPACE_MANAGE = "workspace.manage"
CAP_DASHBOARD_MANAGE = "dashboard.manage"

ALL_ADMIN_CAPABILITIES = frozenset(
    {CAP_AGENT_ASSIGN, CAP_USER_MANAGE, CAP_WORKSPACE_MANAGE, CAP_DASHBOARD_MANAGE}
)


def _as_set(capabilities: Iterable[str] | None) -> set[str]:
    out: set[str] = set()
    for cap in capabilities or ():
        name = str(cap).strip().lower()
        if name:
            out.add(name)
    return out


def evaluate_access(
    *,
    site_role: str | None,
    capabilities: Iterable[str] | None,
    capability: str,
) -> bool:
    """Whether the caller may perform ``capability``.

    A site admin holds every capability. Otherwise ``capability`` must be present
    in ``capabilities`` (an iterable of slugs). A missing/unknown ``capability``
    slug fails closed (denied).
    """
    if (site_role or "").strip().lower() == "site_admin":
        return True
    return capability in _as_set(capabilities)


def has_capability(
    *,
    capabilities: Iterable[str] | None,
    capability: str,
) -> bool:
    """Whether an identity carries ``capability`` without a site-admin short-circuit."""
    return capability in _as_set(capabilities)
