"""Phase 4 — where a workspace gets placed on disk.

Private workspaces keep the historical ``<base>/<user_id>/<name>``.
Tenant-visible workspaces get ``<base>/_tenants/<tenant_id>/<name>`` so one
company's bytes sit together and the path says what the access rule says.

The tests here are deliberately about placement and about the two failure modes
that placement introduces: a tenant workspace with nowhere to go, and a create
that fails after it already touched the disk.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg import errors as pg_errors

from apps.backend.domain.access.entity_access import PRIVATE, TENANT_VISIBLE, normalize_visibility
from apps.backend.domain.workspace.location import (
    TENANT_ROOT_SEGMENT,
    tenant_workspace_root,
    user_workspace_root,
    workspace_root_for,
)
from apps.backend.infrastructure.workspace import workspace_project_service as svc
from apps.backend.infrastructure.workspace.workspace_project_common import (
    WorkspaceCreateError,
    resolve_tenant_workspace_dir,
    resolve_user_workspace_dir,
    resolve_workspace_dir,
)

OWNER = uuid.uuid4()
TENANT = 7


# --------------------------------------------------------------------------
# normalize_visibility
# --------------------------------------------------------------------------


def test_visibility_normalizes_the_two_known_values():
    assert normalize_visibility("tenant") == TENANT_VISIBLE
    assert normalize_visibility("private") == PRIVATE
    assert normalize_visibility("  TENANT ") == TENANT_VISIBLE


def test_unknown_visibility_falls_back_to_private():
    """A typo must not make content company-visible."""
    for bad in ("", None, "public", "shared", "company", "tenants", "tenant_"):
        assert normalize_visibility(bad) == PRIVATE, bad


def test_case_and_whitespace_do_not_change_a_known_value():
    assert normalize_visibility("Tenant") == TENANT_VISIBLE
    assert normalize_visibility("PRIVATE") == PRIVATE


# --------------------------------------------------------------------------
# The roots
# --------------------------------------------------------------------------


def test_roots_are_disjoint_from_each_other():
    base = Path("/ws")
    assert user_workspace_root(base, OWNER) == base / str(OWNER)
    assert tenant_workspace_root(base, TENANT) == base / "_tenants" / "7"
    assert tenant_workspace_root(base, TENANT) != user_workspace_root(base, OWNER)


def test_tenant_segment_cannot_be_produced_by_a_user_id():
    """User ids are UUIDs and the segment is not, so the two roots never collide.

    This is the property that keeps ``_tenants`` from being mistaken for a
    person's directory by anything that walks the base.
    """
    with pytest.raises(ValueError):
        uuid.UUID(TENANT_ROOT_SEGMENT)
    for _ in range(50):
        assert TENANT_ROOT_SEGMENT not in str(uuid.uuid4())


def test_tenant_root_coerces_a_string_tenant_id():
    """A bigint arriving as a string must not open a second directory."""
    base = Path("/ws")
    assert tenant_workspace_root(base, "7") == tenant_workspace_root(base, 7)


def test_tenant_visible_without_a_tenant_is_refused_not_parked_in_the_users_dir():
    base = Path("/ws")
    with pytest.raises(ValueError, match="needs a tenant_id"):
        workspace_root_for(
            base=base, visibility=TENANT_VISIBLE, owner_user_id=OWNER, tenant_id=None
        )


def test_private_placement_ignores_the_tenant():
    base = Path("/ws")
    got = workspace_root_for(
        base=base, visibility=PRIVATE, owner_user_id=OWNER, tenant_id=TENANT
    )
    assert got == user_workspace_root(base, OWNER)


# --------------------------------------------------------------------------
# Containment
# --------------------------------------------------------------------------


def test_tenant_dir_stays_under_the_tenant_root(tmp_path):
    got = resolve_tenant_workspace_dir(tmp_path, TENANT, "repo")
    assert got == (tmp_path / "_tenants" / "7" / "repo").resolve()


def test_traversal_cannot_escape_the_tenant_root(tmp_path):
    with pytest.raises(WorkspaceCreateError):
        resolve_tenant_workspace_dir(tmp_path, TENANT, "..")
    with pytest.raises(WorkspaceCreateError):
        resolve_tenant_workspace_dir(tmp_path, TENANT, "../..")


def test_separator_in_name_is_refused_for_both_roots(tmp_path):
    for bad in ("a/b", "a\\b"):
        with pytest.raises(WorkspaceCreateError):
            resolve_tenant_workspace_dir(tmp_path, TENANT, bad)
        with pytest.raises(WorkspaceCreateError):
            resolve_user_workspace_dir(tmp_path, OWNER, bad)


def test_symlink_cannot_carry_a_tenant_workspace_out_of_its_root(tmp_path):
    """The name check alone would allow this; the containment check is what stops it.

    ``validate_workspace_name`` already rejects ``..`` and separators, so the
    ``relative_to`` guard is not redundant -- it is the only thing that catches a
    resolved path leaving the root, which is what a symlink does.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "_tenants" / "7"
    root.mkdir(parents=True)
    (root / "repo").symlink_to(outside)

    with pytest.raises(WorkspaceCreateError):
        resolve_tenant_workspace_dir(tmp_path, TENANT, "repo")


def test_symlink_cannot_carry_a_private_workspace_out_of_its_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / str(OWNER)
    root.mkdir(parents=True)
    (root / "repo").symlink_to(outside)

    with pytest.raises(WorkspaceCreateError):
        resolve_user_workspace_dir(tmp_path, OWNER, "repo")


def test_resolve_workspace_dir_routes_by_visibility(tmp_path):
    tenant_side = resolve_workspace_dir(
        tmp_path, "repo", visibility=TENANT_VISIBLE, owner_user_id=OWNER, tenant_id=TENANT
    )
    private_side = resolve_workspace_dir(
        tmp_path, "repo", visibility=PRIVATE, owner_user_id=OWNER, tenant_id=TENANT
    )
    assert tenant_side == (tmp_path / "_tenants" / "7" / "repo").resolve()
    assert private_side == (tmp_path / str(OWNER) / "repo").resolve()
    assert tenant_side != private_side


# --------------------------------------------------------------------------
# The create path
# --------------------------------------------------------------------------


def _ws_row(name: str, path: str, tenant_id: int) -> tuple:
    """A row shaped like WORKSPACE_SELECT_SQL returns."""
    return (
        uuid.uuid4(),  # id
        OWNER,  # owner_user_id
        name,  # name
        path,  # path
        "manual",  # source
        None,  # git_url
        "main",  # git_branch
        "owner",  # access_role
        None,  # created_at
        None,  # updated_at
        None,  # verify_command
        False,  # verify_required
        None,  # mcp_stdio_servers_json
        True,  # semantic_index_enabled
        True,  # retrieval_enabled
        None,  # last_index_at
        None,  # last_index_stats
        None,  # last_index_error
        True,  # docs_rag_enabled
        None,  # last_docs_rag_at
        None,  # last_docs_rag_stats
        None,  # last_docs_rag_error
        None,  # index_on_write
        True,  # graph_index_enabled
        None,  # retrieve_context_sources
        "server",  # execution_mode
        "text",  # index_consent
        tenant_id,  # tenant_id
    )


class _Router:
    """Records what the create path tried to INSERT."""

    def __init__(self, *, tenant_id: int, insert_fails: bool = False):
        self.tenant_id = tenant_id
        self.insert_fails = insert_fails
        self.insert_params: tuple | None = None
        self.created_row = uuid.uuid4()


class _Cursor:
    def __init__(self, router: _Router, made: list):
        self._r = router
        self._made = made
        self._rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self._rows = []
        if s.startswith("INSERT"):
            self._r.insert_params = tuple(params or ())
            if self._r.insert_fails:
                raise pg_errors.UniqueViolation()
            self._rows = [(self._r.created_row,)]
            return None
        if "COALESCE(workspace_quota" in s:
            self._rows = [(99,)]
        elif "SELECT COUNT(*) FROM project_workspaces" in s:
            self._rows = [(0,)]
        elif "FROM project_workspaces WHERE id = %s" in s:
            self._rows = self._made
        else:
            raise AssertionError(f"unexpected SQL: {s}")
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Conn:
    def __init__(self, router: _Router, made: list):
        self._r = router
        self._made = made

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def connection(self):
        return self

    def cursor(self, **_kw):
        return _Cursor(self._r, self._made)

    def commit(self):
        pass


def _create(monkeypatch, tmp_path: Path, *, visibility: str, tenant_id: int,
           insert_fails: bool = False, made: list | None = None):
    base = tmp_path / "wsbase"
    router = _Router(tenant_id=tenant_id, insert_fails=insert_fails)
    monkeypatch.setattr(svc, "_workspace_base_path", lambda: base)
    monkeypatch.setattr("apps.backend.infrastructure.db.db.pool",
                       lambda: _Conn(router, made or []))
    monkeypatch.setattr("apps.backend.infrastructure.db.db.user_tenant_id",
                       lambda _u: tenant_id)
    monkeypatch.setattr(
        "apps.backend.domain.shared.identity.get_benchmark_run_id", lambda: None)
    monkeypatch.setattr(
        "apps.backend.infrastructure.platform.client_surface_policy"
        ".refuse_api_key_workspace_mode", lambda _m: None)
    monkeypatch.setattr(
        "apps.backend.infrastructure.platform.client_surface_policy"
        ".refuse_server_workspace_for_user", lambda _u, _m: None)
    user = SimpleNamespace(id=OWNER, role="user")
    return svc.create_project_workspace_for_user(
        user, name="repo", source="manual",
        execution_mode="server", visibility=visibility), router, base


def test_tenant_visible_workspace_is_materialized_under_the_tenant_root(monkeypatch, tmp_path):
    made = [_ws_row("repo", "/placeholder", TENANT)]
    out, router, base = _create(
        monkeypatch, tmp_path, visibility=TENANT_VISIBLE, tenant_id=TENANT, made=made
    )
    assert (base / "_tenants" / "7" / "repo").is_dir()
    assert not (base / str(OWNER)).exists()
    assert out["name"] == "repo"
    # visibility reaches the row, not just the disk
    assert router.insert_params[-1] == TENANT_VISIBLE
    assert router.insert_params[-2] == TENANT


def test_private_workspace_still_lands_in_the_users_directory(monkeypatch, tmp_path):
    made = [_ws_row("repo", "/placeholder", TENANT)]
    _out, router, base = _create(
        monkeypatch, tmp_path, visibility=PRIVATE, tenant_id=TENANT, made=made
    )
    assert (base / str(OWNER) / "repo").is_dir()
    assert not (base / "_tenants").exists()
    assert router.insert_params[-1] == PRIVATE


def test_unknown_visibility_is_placed_as_private(monkeypatch, tmp_path):
    """A bad value must not reach the tenant root."""
    made = [_ws_row("repo", "/placeholder", TENANT)]
    _out, router, base = _create(
        monkeypatch, tmp_path, visibility="public", tenant_id=TENANT, made=made
    )
    assert (base / str(OWNER) / "repo").is_dir()
    assert not (base / "_tenants").exists()
    assert router.insert_params[-1] == PRIVATE


def test_tenant_visible_create_without_a_tenant_writes_nothing(monkeypatch, tmp_path):
    base = tmp_path / "wsbase"
    router = _Router(tenant_id=None, insert_fails=False)
    monkeypatch.setattr(svc, "_workspace_base_path", lambda: base)
    monkeypatch.setattr("apps.backend.infrastructure.db.db.pool",
                       lambda: _Conn(router, []))
    monkeypatch.setattr("apps.backend.infrastructure.db.db.user_tenant_id",
                       lambda _u: None)
    monkeypatch.setattr(
        "apps.backend.domain.shared.identity.get_benchmark_run_id", lambda: None)
    monkeypatch.setattr(
        "apps.backend.infrastructure.platform.client_surface_policy"
        ".refuse_api_key_workspace_mode", lambda _m: None)
    monkeypatch.setattr(
        "apps.backend.infrastructure.platform.client_surface_policy"
        ".refuse_server_workspace_for_user", lambda _u, _m: None)

    with pytest.raises(svc.WorkspaceCreateError):
        svc.create_project_workspace_for_user(
            SimpleNamespace(id=OWNER, role="user"),
            name="repo", source="manual", execution_mode="server",
            visibility=TENANT_VISIBLE,
        )
    assert not base.exists() or list(base.rglob("*")) == []
    assert router.insert_params is None


def test_tenant_name_collision_reports_the_company_not_the_user(monkeypatch, tmp_path):
    made = [_ws_row("repo", "/placeholder", TENANT)]
    with pytest.raises(svc.WorkspaceCreateError) as exc:
        _create(monkeypatch, tmp_path, visibility=TENANT_VISIBLE,
                tenant_id=TENANT, insert_fails=True, made=made)
    assert "company already has" in str(exc.value)
    assert "for this user" not in str(exc.value)


def test_private_name_collision_still_reports_the_user(monkeypatch, tmp_path):
    made = [_ws_row("repo", "/placeholder", TENANT)]
    with pytest.raises(svc.WorkspaceCreateError) as exc:
        _create(monkeypatch, tmp_path, visibility=PRIVATE,
                tenant_id=TENANT, insert_fails=True, made=made)
    assert "for this user" in str(exc.value)


def test_failed_tenant_create_leaves_the_colleagues_files_alone(monkeypatch, tmp_path):
    """The sharpest case: two members, same company name, loser must not wipe."""
    base = tmp_path / "wsbase"
    shared = base / "_tenants" / "7" / "repo"
    shared.mkdir(parents=True)
    (shared / "colleague.txt").write_text("company work\n")

    made = [_ws_row("repo", str(shared), TENANT)]
    with pytest.raises(svc.WorkspaceCreateError):
        _create(monkeypatch, tmp_path, visibility=TENANT_VISIBLE,
                tenant_id=TENANT, insert_fails=True, made=made)

    assert (shared / "colleague.txt").read_text() == "company work\n"
