"""Tenant ownership of entities — the rules around handing one over.

A tenant-visible workspace or dashboard is company data that happens to have a
person's name on the ``owner_user_id`` column. Two operations collide with that:

* moving the person to another company drags the entity along into the wrong
  tenant, and
* removing the person cascades the entity away.

Neither is expressible as a foreign-key rule, because the FK cannot see
``visibility``. The guard therefore lives here, in the layer that decides
access, and the infrastructure refuses the operation rather than picking a
silent answer.
"""

from __future__ import annotations


class TenantOwnedEntitiesConflict(RuntimeError):
    """A user still owns tenant-visible entities and cannot be moved on.

    Carries the counts so the caller can say what has to be transferred rather
    than just that something went wrong. This is a conflict with the state of
    the data, not a permission failure — the actor may be perfectly entitled to
    move the person and still be blocked until someone decides who owns the
    company's workspaces.
    """

    def __init__(self, user_id: object, workspace_count: int, dashboard_count: int) -> None:
        self.user_id = user_id
        self.workspace_count = int(workspace_count)
        self.dashboard_count = int(dashboard_count)
        super().__init__(
            "cannot move user: they still own "
            f"{self.workspace_count} tenant-visible workspace(s) and "
            f"{self.dashboard_count} tenant-visible dashboard(s). "
            "Transfer them to another member of the tenant first."
        )

    @property
    def total(self) -> int:
        return self.workspace_count + self.dashboard_count


def same_tenant(entity_tenant_id: int | None, target_tenant_id: int | None) -> bool:
    """A transfer may not move an entity across tenants by way of its owner.

    Both sides must be known; a missing tenant on either side is not a match.
    """
    if entity_tenant_id is None or target_tenant_id is None:
        return False
    return int(entity_tenant_id) == int(target_tenant_id)
