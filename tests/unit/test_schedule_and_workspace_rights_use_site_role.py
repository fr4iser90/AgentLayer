"""Schedules and workspaces ask ``users.site_role`` who the admin is — never ``users.role``.

ADR 0011 §1 made ``users.site_role`` the only source of elevation and left
``users.role`` as a compatibility column, but ``infrastructure/identity/auth.py`` still
builds ``User.role`` from that legacy column (``SELECT id, email, role …``). Four gates
kept judging it anyway, so an account demoted through ``site_role='site_user'`` that
still carries ``role='admin'`` kept:

  * every schedule in its company — listing, enabling, editing, **hard delete**
    (``api/scheduling/controllers/scheduler_jobs_user_api.py``),
  * the run history of other accounts' schedules (``scheduler_job_runs_api.py``),
  * binding a workspace onto a host path (``client_surface_policy.py``),
  * AgentLayer's own source tree as a self-workspace
    (``workspace_service.self_editing_allowed``),
  * and the schedules feature itself (``schedules_access.py``), whose legacy check ran
    before ``site_role`` and before the ``schedules_allowed`` grant an admin can revoke.

Each gate is pinned for one demoted account, and by source scan: the flag is handed to a
store that documents taking "the caller's already-resolved right", so a re-introduced
legacy read shows up far from the door it opens.
"""

from __future__ import annotations

import ast
import asyncio
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

# Wiring: the HTTP controllers take their collaborators as module attributes, so
# patching here exercises the real handler bodies.
import apps.backend.api.scheduling.controllers.scheduler_job_runs_api as runs_api
import apps.backend.api.scheduling.controllers.scheduler_jobs_user_api as jobs_api
import apps.backend.domain.workspace.workspace_common as workspace_common
from apps.backend.api.scheduling.controllers.scheduler_jobs_user_api import (
    SchedulerJobPatchBody,
    SchedulerJobSetEnabledBody,
)
from apps.backend.infrastructure.scheduling import schedules_access as schedules_gate
from apps.backend.infrastructure.workspace import workspace_service

REPO_ROOT = Path(__file__).resolve().parents[2]

DEMETED = uuid.uuid4()  # role='admin', site_role='site_user'
SITE_ADMIN = uuid.uuid4()  # site_role='site_admin'
PLAIN = uuid.uuid4()  # site_role='site_user'
TENANT = 7
JOB = uuid.uuid4()

# (label, user id, expected admin flag) — one demoted account against a site admin.
ACTORS: list[tuple[str, uuid.UUID, bool]] = [
    ("demoted legacy admin", DEMETED, False),
    ("site admin", SITE_ADMIN, True),
    ("plain member", PLAIN, False),
]


class _User:
    """What ``get_current_user`` hands a handler: ``role`` is the legacy column."""

    def __init__(self, user_id: uuid.UUID) -> None:
        self.id = user_id
        self.role = "admin" if user_id in (DEMETED, SITE_ADMIN) else "user"


class _Pool:
    """Answers ``db.pool().connection()`` for a gate reading one boolean grant."""

    def __init__(self, grant: bool) -> None:
        self._grant = grant

    def connection(self) -> "_Pool":
        return self

    def cursor(self) -> Any:
        grant = self._grant

        class _Cur:
            def execute(self, *_a: Any, **_k: Any) -> None:
                return None

            def fetchone(self) -> tuple[bool]:
                return (grant,)

            def __enter__(self) -> "_Cur":
                return self

            def __exit__(self, *_e: Any) -> bool:
                return False

        return _Cur()

    def __enter__(self) -> "_Pool":
        return self

    def __exit__(self, *_e: Any) -> bool:
        return False


def _site_roles() -> dict[str, str]:
    return {str(DEMETED): "site_user", str(SITE_ADMIN): "site_admin", str(PLAIN): "site_user"}


def _user_effective_role(user_id: Any) -> str:
    return "admin" if _site_roles().get(str(user_id)) == "site_admin" else "user"


@contextmanager
def _identity_patches(grant: bool = False) -> Iterator[None]:
    """All readers live; the legacy one answers ``admin`` for every id, on purpose."""
    with ExitStack() as stack:
        for patcher in (
            patch(
                "apps.backend.infrastructure.db.db.user_site_role",
                side_effect=lambda uid, **_kw: _site_roles().get(str(uid), "site_user"),
            ),
            patch("apps.backend.infrastructure.db.db.user_role", return_value="admin"),
            patch("apps.backend.infrastructure.db.db.user_effective_role", side_effect=_user_effective_role),
            patch("apps.backend.infrastructure.db.db.pool", return_value=_Pool(grant)),
        ):
            stack.enter_context(patcher)
        yield


class _JobsStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_jobs_for_user(self, **kw: Any) -> list[dict[str, Any]]:
        self.calls.append(("list_jobs_for_user", kw))
        return []

    def update_job(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("update_job", kw))
        return {"id": str(JOB)}

    def hard_delete_job(self, **kw: Any) -> bool:
        self.calls.append(("hard_delete_job", kw))
        return True

    def set_enabled(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("set_enabled", kw))
        return {"id": str(JOB)}

    @staticmethod
    def row_to_public(row: Any) -> Any:
        return row


def _call(handler_name: str, store: _JobsStore) -> Any:
    """The real handler body, with only the store, the user and the two DB reads stubbed."""
    if handler_name == "list_jobs_for_user":
        return jobs_api.scheduler_job_list(MagicMock(), dashboard_id=None, limit=50)
    if handler_name == "update_job":
        return jobs_api.scheduler_job_patch(MagicMock(), str(JOB), SchedulerJobPatchBody(title="renamed"))
    if handler_name == "hard_delete_job":
        return jobs_api.scheduler_job_hard_delete(MagicMock(), str(JOB))
    if handler_name == "set_enabled":
        return jobs_api.scheduler_job_set_enabled(
            MagicMock(), str(JOB), SchedulerJobSetEnabledBody(enabled=False)
        )
    raise AssertionError(f"no handler wired for {handler_name}")


HANDLERS = ("list_jobs_for_user", "update_job", "hard_delete_job", "set_enabled")


def _drive(handler_name: str, user_id: uuid.UUID, store: _JobsStore) -> dict[str, Any]:
    with (
        patch.object(jobs_api, "get_current_user", _async_user(user_id)),
        patch.object(jobs_api, "scheduler_jobs_store", store),
        patch.object(jobs_api, "schedule_feature_permission_error", return_value=None),
        patch.object(jobs_api.db, "user_tenant_id", return_value=TENANT),
        patch.object(jobs_api.db, "user_effective_role", side_effect=_user_effective_role),
    ):
        asyncio.run(_call(handler_name, store))
    assert store.calls and store.calls[0][0] == handler_name, f"{handler_name} never reached the store"
    return store.calls[0][1]


def _async_user(user_id: uuid.UUID) -> Any:
    async def _get(_request: Any) -> _User:
        return _User(user_id)

    return _get


def _flag_of(kwargs: dict[str, Any]) -> bool:
    return bool(kwargs.get("is_admin", kwargs.get("actor_is_admin")))


def _request_admin_flags() -> dict[str, dict[str, bool]]:
    """For each handler: the admin flag each of the three accounts is given."""
    out: dict[str, dict[str, bool]] = {}
    for handler_name in HANDLERS:
        per_actor: dict[str, bool] = {}
        for label, user_id, _expected in ACTORS:
            kwargs = _drive(handler_name, user_id, _JobsStore())
            per_actor[label] = _flag_of(kwargs)
            # the mutation must stay company-pinned whatever the flag says
            assert kwargs.get("tenant_id") == TENANT
        out[handler_name] = per_actor
    return out


def test_http_admin_flag_follows_site_role_not_the_legacy_column() -> None:
    flags = _request_admin_flags()
    assert set(flags) == set(HANDLERS)
    for handler_name, per_actor in flags.items():
        for label, _user_id, expected in ACTORS:
            assert per_actor[label] is expected, f"{handler_name}: {label} got the wrong right"


def test_the_demoted_account_keeps_its_own_rows_and_loses_everyone_elses() -> None:
    """The flag is the only difference: with it False, the store's owner rule applies."""
    for handler_name in ("hard_delete_job", "set_enabled", "update_job"):
        kwargs = _drive(handler_name, DEMETED, _JobsStore())
        assert kwargs["actor_user_id"] == DEMETED, "the actor must still be named for the owner check"
        assert _flag_of(kwargs) is False


class _RunsStore:
    def __init__(self) -> None:
        self.seen: list[bool | None] = []

    def user_can_view_job(self, **kw: Any) -> bool:
        self.seen.append(kw.get("is_admin"))
        return True

    def list_runs_for_job(self, **_kw: Any) -> list[dict[str, Any]]:
        return []

    def get_run(self, **_kw: Any) -> dict[str, Any]:
        return {"scheduler_job_id": JOB, "id": str(uuid.uuid4())}

    @staticmethod
    def row_to_public(row: Any) -> Any:
        return row


def _drive_runs(handler: Any, user_id: uuid.UUID, store: _RunsStore) -> _RunsStore:
    with (
        patch.object(runs_api, "get_current_user", _async_user(user_id)),
        patch.object(runs_api, "scheduler_job_runs_store", store),
        patch.object(runs_api.db, "user_tenant_id", return_value=TENANT),
        patch.object(runs_api.db, "user_effective_role", side_effect=_user_effective_role),
    ):
        asyncio.run(handler(MagicMock(), str(JOB)))
    return store


def test_run_history_admin_flag_follows_site_role() -> None:
    for handler in (
        runs_api.user_list_scheduler_job_runs,
        runs_api.user_get_scheduler_job_run,
    ):
        for label, user_id, expected in ACTORS:
            store = _drive_runs(handler, user_id, _RunsStore())
            assert store.seen == [expected], f"{handler.__name__}: {label} got the wrong right"


def test_schedules_feature_needs_site_role_or_the_named_grant() -> None:
    """The legacy column reads ``admin`` for all three accounts inside these patches."""
    with _identity_patches(grant=False):
        assert schedules_gate.user_may_use_schedules(user_id=DEMETED) is False
        assert schedules_gate.user_may_use_schedules(user_id=SITE_ADMIN) is True
        assert schedules_gate.schedule_feature_permission_error(user_id=DEMETED) is not None
        assert schedules_gate.schedule_feature_permission_error(user_id=SITE_ADMIN) is None
    with _identity_patches(grant=True):
        assert schedules_gate.user_may_use_schedules(user_id=PLAIN) is True, (
            "an admin can grant the feature; that grant is what survives a demotion"
        )


def test_schedules_feature_denies_an_identity_that_cannot_be_resolved() -> None:
    with _identity_patches(grant=True):
        assert schedules_gate.user_may_use_schedules(user_id=None) is False


def _self_editing(user_id: uuid.UUID, *, grant: bool) -> bool:
    with (
        patch(
            "apps.backend.infrastructure.settings.operator_settings.public_dict",
            return_value={"workspace_allow_self_editing": True},
        ),
        patch(
            "apps.backend.infrastructure.db.db.user_site_role",
            side_effect=lambda uid, **_kw: _site_roles().get(str(uid), "site_user"),
        ),
        patch("apps.backend.infrastructure.db.db.pool", return_value=_Pool(grant)),
    ):
        return workspace_service.self_editing_allowed(_User(user_id))


def test_self_workspace_needs_site_role_or_the_named_grant() -> None:
    assert _self_editing(DEMETED, grant=False) is False
    assert _self_editing(SITE_ADMIN, grant=False) is True
    assert _self_editing(PLAIN, grant=True) is True
    assert _self_editing(PLAIN, grant=False) is False


def test_the_context_user_carries_no_role_at_all() -> None:
    """The object the workspace tools build must not be able to assert a role."""
    with (
        # ``workspace_common`` imported ``get_identity`` by name, so that is the binding to patch.
        patch.object(workspace_common, "get_identity", return_value=(TENANT, DEMETED)),
        patch("apps.backend.infrastructure.db.db.user_role", return_value="admin"),
    ):
        user = workspace_common.user_from_context(None)
    assert getattr(user, "role", "<unset>") == "<unset>"
    assert user.id == DEMETED


# ---------------------------------------------------------------------------
# Source scan: a legacy read that decides one of these rights is invisible in a diff
# of the resolver, so it is rejected where it would be written.

SCANNED = (
    "apps/backend/api/scheduling/controllers/scheduler_jobs_user_api.py",
    "apps/backend/api/scheduling/controllers/scheduler_job_runs_api.py",
    "apps/backend/infrastructure/platform/client_surface_policy.py",
    "apps/backend/infrastructure/scheduling/schedules_access.py",
    "apps/backend/infrastructure/workspace/workspace_service.py",
    "apps/backend/domain/workspace/workspace_common.py",
)

# Names that take "already an admin" as an argument on these paths.
ADMIN_FLAGS = frozenset({"is_admin", "actor_is_admin"})
# A right may only come from a resolver that reads ``users.site_role``.
_CANONICAL_MARKERS = ("user_effective_role", "user_site_role", "user_site_admin", "user_is_tenant_admin")


def _admin_flag_values(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in ADMIN_FLAGS:
                out.append(ast.unparse(kw.value))
    return out


def test_no_scanned_file_reads_the_legacy_role_column() -> None:
    for rel in SCANNED:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {"db.user_role", "user_role"}:
                raise AssertionError(f"{rel}:{node.lineno} reads the legacy users.role")


def test_every_admin_flag_comes_from_the_canonical_resolver() -> None:
    for rel in SCANNED:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for value in _admin_flag_values(tree):
            assert ".role" not in value, f"{rel}: {value!r} decides an admin right from a role attribute"
            assert "user_role(" not in value, f"{rel}: {value!r} decides an admin right from the legacy reader"
            assert any(marker in value for marker in _CANONICAL_MARKERS) or value in {"True", "False"}, (
                f"{rel}: {value!r} is neither a canonical read nor an explicit constant"
            )


def test_the_schedules_gate_is_never_handed_a_role_string() -> None:
    for rel in SCANNED:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if name.endswith(("user_may_use_schedules", "schedule_feature_permission_error")):
                for kw in node.keywords:
                    assert kw.arg != "user_role", f"{rel}:{node.lineno} feeds a role string to the feature gate"
