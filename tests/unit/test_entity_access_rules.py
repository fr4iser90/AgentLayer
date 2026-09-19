"""The pure access rules must reproduce today's SQL guards exactly.

Each case cites the SQL it mirrors, so a future "cleanup" that unifies the two
models has to consciously break a cited invariant rather than drift by accident.
"""

from __future__ import annotations

import pytest

from apps.backend.domain.access.entity_access import (
    EDIT,
    MANAGE,
    OWNED,
    VIEW,
    evaluate_dashboard_access,
    evaluate_tenant_branch,
    evaluate_tenant_grant,
    evaluate_workspace_access,
    tenant_role_rank,
)

# --------------------------------------------------------------------------
# Workspace — mirrors project_workspaces guards
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "is_owner, access_role, needed, expected",
    [
        # view  <- owner_user_id = actor OR access_role IN ('editor','viewer')
        (True, "owner", VIEW, True),
        (False, "editor", VIEW, True),
        (False, "viewer", VIEW, True),
        (False, "owner", VIEW, False),  # role 'owner' without ownership is not a share grant
        (False, None, VIEW, False),
        # edit  <- owner_user_id = actor AND access_role IN ('owner','editor')
        (True, "owner", EDIT, True),
        (True, "editor", EDIT, True),
        (True, "viewer", EDIT, False),
        (False, "editor", EDIT, False),  # THE asymmetry: a shared editor cannot edit
        (False, "viewer", EDIT, False),
        # manage  <- owner_user_id = actor AND access_role = 'owner'
        (True, "owner", MANAGE, True),
        (True, "editor", MANAGE, False),
        (False, "editor", MANAGE, False),
        (False, "owner", MANAGE, False),
    ],
)
def test_workspace_access_matches_sql_guards(is_owner, access_role, needed, expected):
    assert (
        evaluate_workspace_access(is_owner=is_owner, access_role=access_role, needed=needed)
        is expected
    )


def test_workspace_rule_is_not_a_rank_ladder():
    """Guard the asymmetry on purpose.

    A unified ladder would make (False,'editor',EDIT) true, which today's SQL
    (`owner_user_id = %s AND access_role IN ('owner','editor')`) forbids.
    """
    assert evaluate_workspace_access(is_owner=False, access_role="editor", needed=EDIT) is False
    assert evaluate_workspace_access(is_owner=False, access_role="editor", needed=VIEW) is True


@pytest.mark.parametrize("needed", ["delete", "", "ADMIN", None])
def test_workspace_unknown_need_denies(needed):
    assert evaluate_workspace_access(is_owner=True, access_role="owner", needed=needed) is False


@pytest.mark.parametrize(
    "is_owner, access_role, expected",
    [
        (True, "owner", True),
        (True, "viewer", True),  # owned ignores the share role
        (False, "editor", False),  # a share is never ownership
        (False, "co_owner", False),
        (False, None, False),
    ],
)
def test_workspace_owned_is_strict_ownership(is_owner, access_role, expected):
    assert (
        evaluate_workspace_access(
            is_owner=is_owner, access_role=access_role, needed=OWNED
        )
        is expected
    )


@pytest.mark.parametrize(
    "is_owner, member_role, expected",
    [
        (True, None, True),
        (True, "viewer", True),
        (False, "co_owner", False),  # co_owner is a member, not the owner
        (False, "editor", False),
        (False, None, False),
    ],
)
def test_dashboard_owned_bypasses_the_rank_ladder(is_owner, member_role, expected):
    assert (
        evaluate_dashboard_access(
            is_owner=is_owner, member_role=member_role, needed=OWNED
        )
        is expected
    )


# --------------------------------------------------------------------------
# Dashboard — mirrors dashboard_db access resolution
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "is_owner, member_role, needed, expected",
    [
        (True, None, MANAGE, True),
        (True, "viewer", MANAGE, True),  # ownership outranks any member row
        (False, "co_owner", MANAGE, True),  # can_manage_members: owner or co_owner
        (False, "co_owner", EDIT, True),
        (False, "editor", EDIT, True),
        (False, "editor", MANAGE, False),
        (False, "viewer", EDIT, False),
        (False, "viewer", VIEW, True),
        (False, None, VIEW, False),
        (False, None, EDIT, False),
    ],
)
def test_dashboard_access_rank_ladder(is_owner, member_role, needed, expected):
    assert (
        evaluate_dashboard_access(
            is_owner=is_owner, member_role=member_role, needed=needed
        )
        is expected
    )


def test_dashboard_unknown_role_ranks_zero():
    assert evaluate_dashboard_access(is_owner=False, member_role="superuser", needed=VIEW) is False


# --------------------------------------------------------------------------
# Tenant grants — fail closed on missing membership
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tenant_role, min_role, grant_access, needed, expected",
    [
        ("tenant_admin", "tenant_member", "view", VIEW, True),
        ("tenant_owner", "tenant_admin", "manage", MANAGE, True),
        ("tenant_member", "tenant_admin", "manage", VIEW, False),  # below min role
        ("tenant_admin", "tenant_member", "view", EDIT, False),  # grant too shallow
        ("tenant_admin", "tenant_member", "manage", EDIT, True),
        (None, "tenant_member", "manage", VIEW, False),  # no membership -> closed
        ("tenant_member", None, "manage", VIEW, False),  # no min_role -> closed
        ("tenant_member", "tenant_member", None, VIEW, False),  # no grant level -> closed
        ("guest", "tenant_member", "view", VIEW, False),  # unknown role ranks 0
    ],
)
def test_tenant_grant_rules(tenant_role, min_role, grant_access, needed, expected):
    assert (
        evaluate_tenant_grant(
            tenant_role=tenant_role,
            min_role=min_role,
            grant_access=grant_access,
            needed=needed,
        )
        is expected
    )


def test_tenant_role_hierarchy_is_member_below_admin_below_owner():
    """Semantic ranking (the CHECK-constraint array itself is listed descending)."""
    assert (
        tenant_role_rank("tenant_member")
        < tenant_role_rank("tenant_admin")
        < tenant_role_rank("tenant_owner")
    )
    assert tenant_role_rank("site_admin") == 0  # not a tenant role


# --------------------------------------------------------------------------
# Tenant branch — the decided floor
# --------------------------------------------------------------------------


@pytest.mark.parametrize("needed", [VIEW, EDIT, MANAGE])
@pytest.mark.parametrize("role", ["tenant_admin", "tenant_owner"])
def test_tenant_admin_holds_manage_implicitly(role, needed):
    """No grant row is needed for the delegated admin to work."""
    assert evaluate_tenant_branch(tenant_role=role, grants=None, needed=needed) is True


@pytest.mark.parametrize("needed", [VIEW, EDIT, MANAGE])
def test_tenant_member_gets_nothing_without_a_grant(needed):
    assert (
        evaluate_tenant_branch(tenant_role="tenant_member", grants=[], needed=needed)
        is False
    )


@pytest.mark.parametrize(
    "grant_access, needed, expected",
    [
        ("view", VIEW, True),
        ("view", EDIT, False),
        ("view", MANAGE, False),
        ("edit", VIEW, True),
        ("edit", EDIT, True),
        ("edit", MANAGE, False),
        ("manage", VIEW, True),
        ("manage", EDIT, True),
        ("manage", MANAGE, True),
    ],
)
def test_member_grant_covers_exactly_its_level_and_below(grant_access, needed, expected):
    assert (
        evaluate_tenant_branch(
            tenant_role="tenant_member",
            grants=[("tenant_member", grant_access)],
            needed=needed,
        )
        is expected
    )


def test_grant_above_the_actor_does_not_reach_down():
    """A grant aimed at tenant_admin does not help a plain member."""
    assert (
        evaluate_tenant_branch(
            tenant_role="tenant_member",
            grants=[("tenant_admin", "manage")],
            needed=VIEW,
        )
        is False
    )


def test_any_one_grant_in_the_set_is_enough():
    assert (
        evaluate_tenant_branch(
            tenant_role="tenant_member",
            grants=[("tenant_admin", "view"), ("tenant_member", "edit")],
            needed=EDIT,
        )
        is True
    )


@pytest.mark.parametrize("role", [None, "", "guest", "site_admin"])
def test_no_or_unknown_tenant_role_denies(role):
    """A grant row cannot pull in someone with no standing in the tenant."""
    assert (
        evaluate_tenant_branch(
            tenant_role=role, grants=[("tenant_member", "manage")], needed=VIEW
        )
        is False
    )


@pytest.mark.parametrize("role", ["tenant_admin", "tenant_owner", "tenant_member"])
def test_tenant_branch_never_satisfies_owned(role):
    """owned is identity, not delegated authority — the schema refuses to grant
    it too, so the rule must not hand it out either."""
    assert (
        evaluate_tenant_branch(
            tenant_role=role, grants=[("tenant_member", "manage")], needed=OWNED
        )
        is False
    )


@pytest.mark.parametrize("role", ["tenant_admin", "tenant_owner"])
@pytest.mark.parametrize("needed", ["delete", "", "view ", "admin"])
def test_unrecognised_needed_level_denies_even_for_admin(role, needed):
    """A typo in `needed` must not fall through to the implicit-admin pass."""
    assert evaluate_tenant_branch(tenant_role=role, grants=None, needed=needed) is False


def test_grant_access_is_matched_case_and_whitespace_insensitively():
    assert (
        evaluate_tenant_branch(
            tenant_role="tenant_member",
            grants=[("TENANT_MEMBER", "  Edit  ")],
            needed=EDIT,
        )
        is True
    )
