"""The ``workspace.create`` tool's visibility handling.

The tool is reachable by agents (``workspace.write``, min role ``user``), so the
deliberate shape here is: the handler **accepts** ``visibility`` for the
first-party bulk-import UI, but the advertised ``TOOLS`` spec does **not** declare
it. The runtime performs no schema validation, so an undeclared argument still
reaches the handler — which is why the spec assertion below is the thing that
keeps this off the agent surface rather than the absence of a parameter.

The reuse branch matters as much as the create branch. Reuse never rewrites an
existing workspace's visibility, so a caller that ticked "company" and hit an
existing name did not get what it asked for. Reporting that is the difference
between a visible gap and a silently satisfied checkbox.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from plugins.tools.workspace.bind import workspaces as ws_mod

CREATOR = "apps.backend.infrastructure.workspace.workspace_service.create_project_workspace_for_user"
ENSURER = "apps.backend.infrastructure.workspace.workspace_service.ensure_workspace"
_SURFACE = "apps.backend.infrastructure.platform.client_surface_policy."


def _user():
    u = MagicMock()
    u.id = "u-1"
    return u


def _create(args, *, existing=None):
    """Run the create handler with the service, the lookup, and the hosted-mode
    policy stubbed out — this file is about visibility, not execution mode.

    Returns the parsed result plus the kwargs each ``create_project_workspace_for_user``
    call received, so a test can assert the create path was never taken.
    """
    calls: list[dict] = []

    def fake_create(user, **kw):
        calls.append(kw)
        return {"id": "w-new"}

    materialized = {"id": "w-new", "name": "repo", "source": "git", "path": "/w/repo"}
    if existing:
        materialized["id"] = existing["id"]

    with patch.object(ws_mod, "user_from_context", return_value=_user()), patch.object(
        ws_mod, "list_workspaces_for_user", return_value=[existing] if existing else []
    ), patch.object(ws_mod, "find_workspace_by_name", return_value=existing), patch(
        CREATOR, side_effect=fake_create
    ), patch(
        ENSURER, return_value=materialized
    ), patch(
        _SURFACE + "refuse_api_key_workspace_mode", return_value=None
    ), patch(
        _SURFACE + "refuse_server_workspace_for_user", return_value=None
    ), patch.object(
        ws_mod, "bind_workspace_in_context"
    ), patch.object(
        ws_mod, "persist_conversation_workspace", return_value=False
    ):
        return json.loads(ws_mod.create(args)), calls


def _create_spec():
    for spec in ws_mod.TOOLS:
        if spec.get("function", {}).get("name") == "create":
            return spec["function"]
    raise AssertionError("no create spec in TOOLS")


# --------------------------------------------------------------------------
# Forwarding
# --------------------------------------------------------------------------


def test_visibility_is_forwarded_to_the_service():
    out, calls = _create({"name": "repo", "source": "manual", "visibility": "tenant"})
    assert len(calls) == 1
    assert calls[0]["visibility"] == "tenant"
    assert out["ok"] is True
    assert out["company_visibility_applied"] is True


def test_absent_visibility_stays_private():
    out, calls = _create({"name": "repo", "source": "manual"})
    assert calls[0]["visibility"] == "private"
    assert out["company_visibility_applied"] is False


def test_case_is_normalized_before_the_applied_flag_is_set():
    """The flag must follow the normalized value, not the raw string."""
    out, calls = _create({"name": "repo", "source": "manual", "visibility": "TENANT"})
    assert calls[0]["visibility"] == "tenant"
    assert out["company_visibility_applied"] is True


def test_an_unrecognised_value_is_reported_as_not_company_visible():
    """A typo must not claim company visibility even though the create succeeded."""
    out, calls = _create({"name": "repo", "source": "manual", "visibility": "comapny"})
    assert calls[0]["visibility"] == "private"
    assert out["company_visibility_applied"] is False


# --------------------------------------------------------------------------
# The reuse branch
# --------------------------------------------------------------------------


def test_reuse_does_not_claim_company_visibility():
    existing = {"id": "w-old", "name": "repo"}
    out, _ = _create({"name": "repo", "source": "manual", "visibility": "tenant"}, existing=existing)
    assert out["ok"] is True
    assert out["reused"] is True
    assert out["company_visibility_applied"] is False


def test_reuse_never_calls_the_creator():
    """A reused name must not go through the create path at all."""
    existing = {"id": "w-old", "name": "repo"}
    out, calls = _create({"name": "repo", "source": "manual", "visibility": "tenant"}, existing=existing)
    assert calls == []
    assert out["reused"] is True


# --------------------------------------------------------------------------
# The agent surface stays closed
# --------------------------------------------------------------------------


def test_visibility_is_not_advertised_in_the_tool_spec():
    """The parameter is accepted but not declared, so the model never emits it."""
    props = _create_spec()["parameters"]["properties"]
    assert "visibility" not in props


def test_the_advertised_create_parameters_are_exactly_the_known_set():
    props = _create_spec()["parameters"]["properties"]
    assert set(props) == {"name", "source", "git_url", "git_branch", "bind"}
