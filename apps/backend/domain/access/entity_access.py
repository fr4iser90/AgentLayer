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

On top of both sits the tenant layer, which only ever *adds* access and only for
an entity whose ``visibility`` is ``tenant``. See ``evaluate_tenant_branch``.
"""

from __future__ import annotations

VIEW = "view"
EDIT = "edit"
MANAGE = "manage"
OWNED = "owned"

NEEDED_LEVELS = (OWNED, VIEW, EDIT, MANAGE)

PRIVATE = "private"
TENANT_VISIBLE = "tenant"

VISIBILITY_VALUES = (PRIVATE, TENANT_VISIBLE)

TENANT_ADMIN_ROLE = "tenant_admin"
TENANT_MEMBER_ROLE = "tenant_member"
TENANT_OWNER_ROLE = "tenant_owner"

# What a grant row may say. Mirrors the CHECK constraints on tenant_entity_grants
# so a bad value is refused in Python with a readable message rather than by a
# database error surfacing through a 500. ``owned`` is absent on purpose: it is
# pure ownership and cannot be handed out.
GRANT_MIN_ROLES = (TENANT_MEMBER_ROLE, TENANT_ADMIN_ROLE, TENANT_OWNER_ROLE)
GRANT_ACCESS_LEVELS = (VIEW, EDIT, MANAGE)

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


def normalize_visibility(raw: object) -> str:
    """Anything unrecognised means ``private``.

    A typo in a create request must not turn somebody's workspace into
    company-visible content, so the fallback is the narrower value — the same
    direction ``normalize_execution_mode`` takes for the same reason.
    """
    v = str(raw or "").strip().lower()
    return TENANT_VISIBLE if v == TENANT_VISIBLE else PRIVATE


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


def evaluate_tenant_branch(
    *,
    tenant_role: str | None,
    grants: list[tuple[str, str]] | None = None,
    needed: str = VIEW,
) -> bool:
    """Tenant-layer access to an entity whose visibility is ``tenant``.

    ``tenant_admin`` and ``tenant_owner`` hold ``manage`` implicitly — the
    delegated company admin stays able to work without any grant rows.
    ``tenant_member`` gets nothing unless a grant row clears them.

    Two things this deliberately cannot do:

    * satisfy ``owned``. ``owned`` is pure ownership, not delegated authority,
      and the schema refuses to grant it too. A tenant admin who can ``manage``
      a company workspace is still not the person it belongs to.
    * reach an actor with no membership. An absent or unknown tenant role ranks
      below ``tenant_member`` and denies, so a user outside the tenant gets
      nothing from a grant row that names them.

    ``grants`` is the (min_role, access) rows for this entity and tenant. The
    caller must key that lookup on the entity's own tenant, not the actor's.
    """
    needed_rank = _NEEDED_RANK.get(needed)
    if needed_rank is None:
        # Only view/edit/manage are ranked. owned is deliberately unranked, so
        # it lands here and denies: delegated tenant authority never satisfies
        # pure ownership. An unrecognised level denies for the same reason,
        # rather than falling through to the implicit-admin pass below.
        return False
    rank = tenant_role_rank(tenant_role)
    if rank < tenant_role_rank(TENANT_MEMBER_ROLE):
        return False
    if rank >= tenant_role_rank(TENANT_ADMIN_ROLE):
        return True
    for min_role, access in grants or ():
        if evaluate_tenant_grant(
            tenant_role=tenant_role,
            min_role=min_role,
            grant_access=access,
            needed=needed,
        ):
            return True
    return False
