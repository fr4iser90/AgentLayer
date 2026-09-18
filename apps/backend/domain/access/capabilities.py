"""Platform/admin scope RBAC — per-user capabilities (P6, Weg B).

The capability *slug* is tenant-independent: ``user.manage`` means the same thing
everywhere. The *range it reaches* is not — see :class:`AdminScope`. A delegated
holder acts inside their own tenant; only a site admin acts site-wide. Keeping
those two ideas separate is what stops a company admin from reaching into another
company.

The evaluation here is pure; the :mod:`require_admin_capability` guard in the
auth layer reads the stored capability set for a user and delegates to
:func:`evaluate_access`, and :func:`require_admin_scope` builds the
:class:`AdminScope` on top. Content/knowledge RBAC lives in
:mod:`domain.tenant_profession.policy` and is a separate axis.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable

# Platform/admin capabilities. A site admin implicitly holds every capability;
# non-site-admins must be granted each one explicitly on ``users.capabilities``.
CAP_AGENT_ASSIGN = "agent.assign"
CAP_USER_MANAGE = "user.manage"
CAP_WORKSPACE_MANAGE = "workspace.manage"
CAP_DASHBOARD_MANAGE = "dashboard.manage"

# Added when the admin surface was split into site-level and tenant-level work.
# Benchmarks deliberately have no slug: running one consumes shared provider
# compute and stays site-admin only.
CAP_SCHEDULE_MANAGE = "schedule.manage"
CAP_OBSERVABILITY_READ = "observability.read"
CAP_FEEDBACK_READ = "feedback.read"
CAP_KNOWLEDGE_MANAGE = "knowledge.manage"

ALL_ADMIN_CAPABILITIES = frozenset(
    {
        CAP_AGENT_ASSIGN,
        CAP_USER_MANAGE,
        CAP_WORKSPACE_MANAGE,
        CAP_DASHBOARD_MANAGE,
        CAP_SCHEDULE_MANAGE,
        CAP_OBSERVABILITY_READ,
        CAP_FEEDBACK_READ,
        CAP_KNOWLEDGE_MANAGE,
    }
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


class AdminScopeError(PermissionError):
    """An admin action reached outside the actor's tenant scope."""


@dataclass(frozen=True, slots=True)
class AdminScope:
    """The tenant range a delegated admin action may reach.

    A site admin is site-wide. A delegated capability holder is confined to
    ``tenant_ids`` — today exactly their own tenant, which is what stops
    ``user.manage`` and ``agent.assign`` from being instance-wide. Before that
    confinement a delegated admin of company A could list, create, move and
    grant against users of company B.

    ``site_wide`` is carried explicitly rather than encoded as "all tenants
    exist in this set" so that widening the delegated case later cannot
    accidentally read as site-wide.
    """

    actor_id: uuid.UUID
    site_wide: bool
    tenant_ids: frozenset[int]

    def allows_tenant(self, tenant_id: int | None) -> bool:
        if self.site_wide:
            return True
        if tenant_id is None:
            return False
        return int(tenant_id) in self.tenant_ids

    def require_tenant(self, tenant_id: int | None, *, what: str = "tenant") -> int:
        """Return ``tenant_id`` when in scope, else raise. Never returns for ``None``."""
        if tenant_id is None:
            raise AdminScopeError(f"{what} must name a tenant")
        tid = int(tenant_id)
        if not self.allows_tenant(tid):
            raise AdminScopeError(f"{what} is outside your admin scope")
        return tid

    def require_site_wide(self, what: str) -> None:
        """Guard operations that must never be delegated (e.g. moving a user
        between tenants)."""
        if not self.site_wide:
            raise AdminScopeError(f"{what} requires site admin")

    def tenant_filter(self) -> frozenset[int] | None:
        """``None`` means "do not filter" (site admin); otherwise the allowed set.

        For list endpoints, where site-wide genuinely means every tenant rather
        than an empty allow-set.
        """
        return None if self.site_wide else self.tenant_ids
