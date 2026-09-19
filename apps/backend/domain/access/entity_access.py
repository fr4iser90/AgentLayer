"""Pure entity-access rules (no IO).

Single place where "may this principal do X to this entity" is decided. The
per-entity rules are deliberately NOT unified into one rank ladder: the two
existing models are not isomorphic and collapsing them would silently change
behaviour.

Workspace (``project_workspaces.access_role`` in owner|editor|viewer) is
owner-centric today: ``edit`` and ``manage`` both require ``owner_user_id`` to
match the actor, so a row shared with ``access_role='editor'`` can only be
*viewed*, never edited. That asymmetry is preserved verbatim.

Dashboard (``dashboard_members.role`` in viewer|editor|co_owner, plus
``owner_user_id``) is a genuine rank ladder and maps cleanly.
"""

from __future__ import annotations

VIEW = "view"
EDIT = "edit"
MANAGE = "manage"
OWNED = "owned"

NEEDED_LEVELS = (OWNED, VIEW, EDIT, MANAGE)

_DASHBOARD_ROLE_RANK = {
    "viewer": 1,
    "editor": 2,
    "co_owner": 3,
    "owner": 4,
}
_NEEDED_RANK = {VIEW: 1, EDIT: 2, MANAGE: 3}

_TENANT_ROLE_RANK = {
    "tenant_member": 1,
    "tenant_admin": 2,
    "tenant_owner": 3,
}


def dashboard_role_rank(role: str | None) -> int:
    return _DASHBOARD_ROLE_RANK.get(str(role or "").strip().lower(), 0)


def tenant_role_rank(role: str | None) -> int:
    return _TENANT_ROLE_RANK.get(str(role or "").strip().lower(), 0)


def evaluate_workspace_access(
    *,
    is_owner: bool,
    access_role: str | None = None,
    needed: str = VIEW,
) -> bool:
    """Mirror of the current workspace SQL guards, unchanged.

    view    <- ``owner_user_id = actor OR access_role IN ('editor','viewer')``
    edit    <- ``owner_user_id = actor AND access_role IN ('owner','editor')``
    manage  <- ``owner_user_id = actor AND access_role = 'owner'``
    owned   <- ``owner_user_id = actor`` (no share path; stricter than ``view``)
    """
    role = str(access_role or "").strip().lower()
    if needed == OWNED:
        return bool(is_owner)
    if needed == VIEW:
        return bool(is_owner) or role in ("editor", "viewer")
    if needed == EDIT:
        return bool(is_owner) and role in ("owner", "editor")
    if needed == MANAGE:
        return bool(is_owner) and role == "owner"
    return False


def evaluate_dashboard_access(
    *,
    is_owner: bool,
    member_role: str | None = None,
    needed: str = VIEW,
) -> bool:
    """Rank ladder over ``dashboard_members.role``; the owner sits above it.

    ``owned`` bypasses the ladder: a ``co_owner`` member is not the owner.
    """
    if needed == OWNED:
        return bool(is_owner)
    rank = 4 if is_owner else dashboard_role_rank(member_role)
    return rank >= _NEEDED_RANK.get(needed, 99)


def evaluate_tenant_grant(
    *,
    tenant_role: str | None,
    min_role: str | None,
    grant_access: str | None,
    needed: str = VIEW,
) -> bool:
    """A tenant-scoped grant holds when the actor's membership clears the grant's
    minimum role and the grant covers the requested level.

    Unknown roles rank 0 and therefore never satisfy a grant, so a missing
    membership fails closed.
    """
    if not min_role:
        return False
    if tenant_role_rank(tenant_role) < tenant_role_rank(min_role):
        return False
    return _NEEDED_RANK.get(needed, 99) <= _NEEDED_RANK.get(
        str(grant_access or "").strip().lower(), 0
    )
