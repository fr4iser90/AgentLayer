"""Dashboard access asks ``users.site_role`` — never ``users.role``, not even as a fallback.

``infrastructure/dashboard/dashboard_access.user_may_use_dashboards`` read ``db.user_role``
and handed it to ``domain/dashboards/access.evaluate_dashboards_access`` as ``user_role``,
preferring it over the per-user grant: ``if role == "admin": return True`` came first, so
``site_role`` was only ever consulted for accounts the legacy column had already cleared.
ADR 0011 §1 keeps ``users.role`` as a compatibility column and a demotion does not rewrite
it, so an account demoted to ``site_user`` that still carried ``role='admin'`` went on seeing
and creating dashboards — and the second path in the resolver made it worse: an account with
no id, or one whose DB lookup raised, fell back onto ``user.role`` off the request object.

The rule decides who may use the dashboards feature at all (create gate, quota gate, and
``dashboard_persistence``'s read guard), so this is a feature-wide right, unlike the task
queueing rule, which only names the status of a fresh row.

Pinned per actor and by source scan, because the read and the rule sit in two layers:
``apps/backend/infrastructure/dashboard/dashboard_access.py`` feeds
``apps/backend/domain/dashboards/access.py``.
"""

from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.backend.domain.dashboards import access as rule
from apps.backend.infrastructure.dashboard import dashboard_access as mod

REPO_ROOT = Path(__file__).resolve().parents[2]

DEMOTED = uuid.uuid4()  # site_role='site_user', legacy users.role='admin'
SITE_ADMIN = uuid.uuid4()  # site_role='site_admin'
MEMBER = uuid.uuid4()  # site_role='site_user'

_SCANNED = (
    "apps/backend/infrastructure/dashboard/dashboard_access.py",
    "apps/backend/domain/dashboards/access.py",
)


def _site_roles() -> dict[str, str]:
    return {str(DEMOTED): "site_user", str(SITE_ADMIN): "site_admin", str(MEMBER): "site_user"}


def _may(uid: uuid.UUID, *, grant: bool) -> bool:
    """Ask the real resolver with the legacy reader answering ``admin`` for every id.

    A resolver that still consults it returns True for all three actors and the demoted
    assertions below cannot be satisfied.
    """
    with (
        patch.object(mod, "global_dashboards_enabled", return_value=True),
        patch.object(mod, "_load_user_dashboards_allowed", return_value=grant),
        patch(
            "apps.backend.infrastructure.db.db.user_site_role",
            side_effect=lambda uid_, **_kw: _site_roles().get(str(uid_), "site_user"),
        ),
        patch("apps.backend.infrastructure.db.db.user_role", return_value="admin"),
    ):
        return mod.user_may_use_dashboards(user_id=uid)


# ---------------------------------------------------------------------------
# The rule itself.


def test_a_site_admin_may_use_dashboards_without_a_grant() -> None:
    assert rule.evaluate_dashboards_access(site_role="site_admin", dashboards_allowed=False) is True


def test_a_demoted_account_may_not() -> None:
    assert rule.evaluate_dashboards_access(site_role="site_user", dashboards_allowed=False) is False


def test_an_unknown_site_role_elevates_nothing() -> None:
    for raw in (None, "", "  ", "siteuser", "ADMIN", "SiteAdmin"):
        assert rule.evaluate_dashboards_access(site_role=raw, dashboards_allowed=False) is False, raw


def test_a_member_still_follows_the_per_user_grant() -> None:
    assert rule.evaluate_dashboards_access(site_role="site_user", dashboards_allowed=True) is True


# ---------------------------------------------------------------------------
# The resolver: per actor, with the legacy column deliberately left readable.


def test_the_demoted_legacy_admin_loses_the_feature() -> None:
    assert _may(DEMOTED, grant=False) is False


def test_the_site_admin_keeps_it_against_a_revoked_grant() -> None:
    assert _may(SITE_ADMIN, grant=False) is True


def test_a_member_with_the_grant_keeps_it() -> None:
    assert _may(MEMBER, grant=True) is True


def test_no_id_means_no_site_role_means_denied() -> None:
    """``user.role`` used to be the fallback here; an id is the only way in now."""
    with patch.object(mod, "global_dashboards_enabled", return_value=True):
        assert mod.user_may_use_dashboards(user=SimpleNamespace(role="admin")) is False
        assert mod.user_may_use_dashboards() is False


# ---------------------------------------------------------------------------
# Source scans: the read moved out of the rule, so a re-introduced legacy read would sit
# two layers away from the right it opens — and a parameter would be enough to bring it back.


def test_neither_file_reads_the_legacy_role_column() -> None:
    for rel in _SCANNED:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {"db.user_role", "user_role"}:
                raise AssertionError(f"{rel}:{node.lineno} reads the legacy users.role")


def test_no_dashboard_rule_accepts_a_role_string() -> None:
    """A parameter that can hold ``users.role`` is how this comes back."""
    for name, fn in vars(rule).items():
        if name.startswith("_") or not callable(fn) or getattr(fn, "__module__", None) != rule.__name__:
            continue
        for param in inspect.signature(fn).parameters:
            assert param not in {"user_role", "role"}, f"{name} takes {param!r} again"


def _assigned_sources(tree: ast.AST) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            out.setdefault(node.targets[0].id, []).append(ast.unparse(node.value))
    return out


def test_the_resolver_passes_the_canonical_read_to_the_rule() -> None:
    """``site_role=`` must trace back to ``db.user_site_role``, not merely be named that.

    The read sits in a local so a failing lookup is caught and denies instead of raising, so
    the name is followed to where it was assigned rather than matched as literal call text.
    """
    rel = "apps/backend/infrastructure/dashboard/dashboard_access.py"
    tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
    assigned = _assigned_sources(tree)
    calls = [
        node for node in ast.walk(tree) if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("evaluate_dashboards_access")
    ]
    assert calls, "the resolver no longer asks the dashboard rule at all"
    for node in calls:
        args = {kw.arg: kw.value for kw in node.keywords}
        assert "user_role" not in args, f"line {node.lineno} feeds a role string to the rule again"
        assert "site_role" in args, f"line {node.lineno} does not pass site_role"
        value = args["site_role"]
        origin = assigned.get(value.id, []) if isinstance(value, ast.Name) else [ast.unparse(value)]
        assert len(origin) == 1, f"line {node.lineno} passes {ast.unparse(value)!r}, assigned from {origin}"
        assert "user_site_role" in origin[0] and "user_role(" not in origin[0], (
            f"line {node.lineno} feeds {ast.unparse(value)!r} = {origin[0]!r}"
        )


def test_the_second_door_stays_shut() -> None:
    """``dashboard_permission_error_from_flags`` had no callers and took ``user_role`` too.

    Kept as a helper it is a ready-made way to hand the retired column to a dashboard rule,
    so it was deleted rather than converted.
    """
    assert not hasattr(rule, "dashboard_permission_error_from_flags")
