"""Explicit tenant scoping for queries against tenant-scoped tables.

Two ways a query is allowed to touch a tenant-scoped table:

* it carries a :class:`TenantScope` predicate (``tenant_id = %s``), or
* the statement is marked ``# tenant-scope: site-wide`` because the surface
  legitimately spans tenants (instance admin, cross-tenant reporting).

Anything else is a bug: an unscoped query on tenant data. The repository check
``tenant_scope`` enforces exactly that split, so the marker and this module are
the two ends of the same contract.

The marker comment is a comment rather than a type because the statements it
legitimises are raw SQL in the infrastructure layer, which cannot import a marker
object into the middle of a query string.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .value_objects import TenantId

TENANT_COLUMN = "tenant_id"

#: Recognised anywhere on the line above, or trailing on the statement line.
SITE_WIDE_MARKER = "tenant-scope: site-wide"


class TenantScopeError(ValueError):
    """Raised when a record turns out to belong to a different tenant than the scope."""


@dataclass(frozen=True, slots=True)
class TenantScope:
    """The tenant a single query is bound to."""

    tenant_id: TenantId

    @classmethod
    def of(cls, raw: int | TenantId) -> "TenantScope":
        return cls(tenant_id=raw if isinstance(raw, TenantId) else TenantId(int(raw)))

    def predicate(self, *, column: str = TENANT_COLUMN) -> str:
        return f"{column} = %s"

    def where(self, *, column: str = TENANT_COLUMN) -> tuple[str, tuple[int, ...]]:
        """``("tenant_id = %s", (7,))`` — ready to join into a WHERE clause."""
        return self.predicate(column=column), (int(self.tenant_id),)

    def matches(self, other: "TenantScope | int | TenantId") -> bool:
        return int(self.tenant_id) == _coerce_tenant_id(other)

    def require_matches(
        self,
        other: "int | TenantId | Mapping[str, Any]",
        *,
        what: str = "record",
    ) -> None:
        """Guard a row that was fetched without a tenant predicate.

        Use when the lookup key (a UUID, a slug) was already trusted to be opaque
        and the tenant check happens after the read.
        """
        if isinstance(other, Mapping):
            raw = other.get(TENANT_COLUMN)
            if raw is None:
                raise TenantScopeError(f"{what} carries no {TENANT_COLUMN}")
            target = raw
        else:
            target = other
        if not self.matches(target):
            raise TenantScopeError(f"{what} belongs to another tenant")


def _coerce_tenant_id(value: "int | TenantId | TenantScope") -> int:
    if isinstance(value, TenantScope):
        return int(value.tenant_id)
    if isinstance(value, TenantId):
        return int(value)
    return int(value)
