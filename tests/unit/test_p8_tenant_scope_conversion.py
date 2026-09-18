"""Tenant scope on the surfaces converted after the first ``agent.assign`` pass.

Each of these took ``require_admin`` (which is ``require_site_admin``) and now
either carries a tenant-bounded capability or is explicitly site-only. The
tests pin both directions: a delegated admin reaches their own tenant and is
refused everything outside it, and the deliberately-undelegable surfaces refuse
a delegated admin outright.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.api.providers.controllers import model_catalog_api as model_api
from apps.backend.api.rag.controllers import rag_api
from apps.backend.api.workspaces.controllers import workspaces_admin_api as ws_api
from apps.backend.application.workspace.use_cases import (
    workspace_controller_services as ws_services,
)
from apps.backend.domain.access.capabilities import AdminScope

_ACTOR = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_OWN_TENANT = 4
_OTHER_TENANT = 9
_USER_OWN = uuid.UUID("22222222-2222-2222-2222-222222222222")
_USER_OTHER = uuid.UUID("33333333-3333-3333-3333-333333333333")
_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"


def _delegated() -> AdminScope:
    return AdminScope(actor_id=_ACTOR, site_wide=False, tenant_ids=frozenset({_OWN_TENANT}))


def _site() -> AdminScope:
    return AdminScope(actor_id=_ACTOR, site_wide=True, tenant_ids=frozenset())


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def _workspace_row(tenant_id: int) -> tuple:
    """A row shaped like WORKSPACE_SELECT_SQL: 27 leading columns, tenant last."""
    row: list = [None] * 28
    row[0] = uuid.UUID(_WORKSPACE_ID)
    row[1] = _ACTOR
    row[2] = "own-repo"
    row[3] = "/data/project_workspaces/own-repo"
    row[27] = tenant_id
    return tuple(row)


def _ws_mocks(tenant_id: int | None):
    """Patch the fetch but leave ``workspace_tenant_id`` real, so the index
    constant is exercised rather than stubbed away."""
    return {
        "require_admin_scope": AsyncMock(return_value=_delegated()),
        "fetch": MagicMock(return_value=_workspace_row(tenant_id)),
    }


# --- workspaces_admin_api: POST /v1/admin/workspaces/{id}/reindex ---


def test_reindex_allows_workspace_in_own_tenant() -> None:
    with (
        patch.object(ws_api, "require_admin_scope", AsyncMock(return_value=_delegated())),
        patch.object(ws_services, "fetch_workspace_row_any_owner", return_value=_workspace_row(_OWN_TENANT)),
        patch.object(ws_services, "row_to_workspace", return_value={"id": _WORKSPACE_ID}),
    ):
        kick = MagicMock()
        kick.get = lambda k, d=None: {"started": True, "job": "j1"}.get(k, d)
        status = MagicMock()
        status.index_status_payload = MagicMock(return_value={})
        with patch.object(ws_services, "workspace_retrieval", status):
            out = _run(ws_api.admin_reindex_workspace(MagicMock(), _WORKSPACE_ID, None))
    assert out["ok"] is True
    assert out["started"] is True


def test_reindex_refuses_workspace_of_another_tenant() -> None:
    with (
        patch.object(ws_api, "require_admin_scope", AsyncMock(return_value=_delegated())),
        patch.object(ws_services, "fetch_workspace_row_any_owner", return_value=_workspace_row(_OTHER_TENANT)),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(ws_api.admin_reindex_workspace(MagicMock(), _WORKSPACE_ID, None))
    assert exc.value.status_code == 403


def test_reindex_allows_any_workspace_for_site_admin() -> None:
    with (
        patch.object(ws_api, "require_admin_scope", AsyncMock(return_value=_site())),
        patch.object(ws_services, "fetch_workspace_row_any_owner", return_value=_workspace_row(_OTHER_TENANT)),
        patch.object(ws_services, "row_to_workspace", return_value={"id": _WORKSPACE_ID}),
    ):
        kick = MagicMock()
        kick.get = lambda k, d=None: {"started": True}.get(k, d)
        status = MagicMock()
        status.index_status_payload = MagicMock(return_value={})
        with patch.object(ws_services, "workspace_retrieval", status):
            out = _run(ws_api.admin_reindex_workspace(MagicMock(), _WORKSPACE_ID, None))
    assert out["ok"] is True


def test_reindex_missing_workspace_is_404_before_scope_check() -> None:
    guard = AsyncMock(return_value=_delegated())
    with (
        patch.object(ws_api, "require_admin_scope", guard),
        patch.object(ws_services, "fetch_workspace_row_any_owner", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(ws_api.admin_reindex_workspace(MagicMock(), _WORKSPACE_ID, None))
    assert exc.value.status_code == 404


# --- model_catalog_api: /v1/admin/model-access/users/{user_id} ---


def _model_access_mocks(scope: AdminScope, target_tenant: int):
    return (
        patch.object(model_api, "require_admin_scope", AsyncMock(return_value=scope)),
        patch.object(model_api, "user_exists", MagicMock(return_value=True)),
        patch.object(model_api, "tenant_id_for_user", MagicMock(return_value=target_tenant)),
        patch.object(model_api, "_model_access_payload_for_scope", MagicMock(return_value={"ok": True})),
        patch.object(model_api, "_sync_model_access_payload", MagicMock()),
        patch.object(model_api.asyncio, "to_thread", AsyncMock(return_value=None)),
    )


def test_user_model_access_get_own_tenant() -> None:
    from contextlib import ExitStack

    with ExitStack() as stack:
        for ctx in _model_access_mocks(_delegated(), _OWN_TENANT):
            stack.enter_context(ctx)
        out = _run(model_api.admin_get_user_model_access(MagicMock(), _USER_OWN))
    assert out == {"ok": True}


def test_user_model_access_get_other_tenant_refused() -> None:
    from contextlib import ExitStack

    with ExitStack() as stack:
        for ctx in _model_access_mocks(_delegated(), _OTHER_TENANT):
            stack.enter_context(ctx)
        with pytest.raises(HTTPException) as exc:
            _run(model_api.admin_get_user_model_access(MagicMock(), _USER_OTHER))
    assert exc.value.status_code == 403


def test_user_model_access_put_other_tenant_refused_before_write() -> None:
    from contextlib import ExitStack

    with ExitStack() as stack:
        sync = AsyncMock(return_value=None)
        for ctx in _model_access_mocks(_delegated(), _OTHER_TENANT):
            stack.enter_context(ctx)
        stack.enter_context(patch.object(model_api.asyncio, "to_thread", sync))
        with pytest.raises(HTTPException) as exc:
            _run(
                model_api.admin_put_user_model_access(
                    MagicMock(), _USER_OTHER, MagicMock()
                )
            )
    assert exc.value.status_code == 403
    sync.assert_not_called()


# --- rag_api ---


def test_rag_ingest_uses_actor_id_as_tenant_source() -> None:
    req = MagicMock()
    req.json = AsyncMock(return_value={"text": "hello"})
    with (
        patch.object(rag_api, "require_admin_scope", AsyncMock(return_value=_delegated())),
        patch.object(rag_api.operator_settings, "rag_settings", MagicMock(return_value={"enabled": True})),
        patch.object(rag_api, "reject_admin_tenant_knowledge_rag_ingest", MagicMock()),
        patch.object(rag_api.db, "user_tenant_id", return_value=_OWN_TENANT) as tid,
        patch.object(rag_api.rag_service, "ingest_for_user", return_value={"ok": True}) as ingest,
    ):
        out = _run(rag_api.admin_rag_ingest(req))
    assert out == {"ok": True}
    tid.assert_called_once_with(_ACTOR)
    assert ingest.call_args[0][0] == _OWN_TENANT
    assert ingest.call_args[0][1] == _ACTOR


def test_rag_ingest_docs_is_site_only() -> None:
    """docs_root is a caller-supplied server path, so a delegated admin is refused."""
    with (
        patch.object(rag_api, "require_site_admin", AsyncMock(side_effect=HTTPException(403, "site admin"))),
        patch.object(rag_api, "require_admin_scope", AsyncMock(return_value=_delegated())),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(rag_api.admin_rag_ingest_docs(MagicMock(), body=rag_api.IngestDocsBody(domain="x")))
    assert exc.value.status_code == 403


def test_rag_ingest_docs_calls_site_guard_not_scope_guard() -> None:
    site = AsyncMock(side_effect=HTTPException(403, "nope"))
    scope = AsyncMock(return_value=_delegated())
    with (
        patch.object(rag_api, "require_site_admin", site),
        patch.object(rag_api, "require_admin_scope", scope),
    ):
        with pytest.raises(HTTPException):
            _run(rag_api.admin_rag_ingest_docs(MagicMock(), body=rag_api.IngestDocsBody(domain="x")))
    site.assert_awaited_once()
    scope.assert_not_awaited()
