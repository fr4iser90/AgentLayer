"""The ``min_role`` door asks ``users.site_role``; the legacy ``users.role`` opens nothing.

ADR 0011 §1 made ``users.site_role`` the only source of elevation. The door in
:func:`apps.backend.domain.plugin_system.tool_policy.caller_fulfills_effective_policy`
kept being fed ``db.user_role()`` — a read of ``users.role`` — so every tool whose
manifest says ``TOOL_MIN_ROLE = "admin"`` stayed open for an account that only carries
``role='admin'`` from before the migration while ``site_role`` says ``site_user``.
That is the whole operator surface: ``operator_admin``, ``operator_agent_config`` and
``reviewer_audit`` — which the previous commits had just confined per handler, on the
assumption that whoever got past the door was an admin.

The door has six feeds (invoke, the chat tool list, ``GET /v1/tools``,
``GET /v1/capabilities``, the admin "effective tools" preview, the agents catalog tool
plus ``delegate``'s admin-only specialists), so one resolver is shared and each feed is
pinned here: behaviourally for one demoted account, and by source scan — a feed that
re-reads the legacy column is invisible in a diff of the door itself.
"""

from __future__ import annotations

import ast
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Wiring: the scan directories that make the registry load real plugins, and the
# adapter that owns the invoke-time door.
import apps.backend.api.tools.controllers.tools_api as tools_api
import apps.backend.application.agent_runtime.use_cases.chat_tool_selection as chat_selection
import apps.backend.domain.plugin_system.tool_policy as tool_policy
import apps.backend.infrastructure.plugins.plugin_registry_service  # noqa: F401
import apps.backend.infrastructure.tools.tool_runtime_service as runtime

from apps.backend.application.identity.use_cases.request_auth import agent_effective_role
from apps.backend.domain.plugin_system import tools as tool_dispatch
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.domain.plugin_system.tool_policy import (
    caller_fulfills_effective_policy,
    filter_chat_tool_specs,
    manifest_min_role,
)
from apps.backend.domain.shared.identity import reset_identity, set_identity
from apps.backend.infrastructure.db import identity_tenants as identity_db

REPO_ROOT = Path(__file__).resolve().parents[2]

# Packages whose manifest demands admin; the three operator consoles.
CONSOLE_PACKAGES = frozenset({"operator_admin", "operator_agent_config", "reviewer_audit"})

# Every place that hands a role to the door. The domain door (``tools.py``) is not
# listed: it only declares the seam, and the accessor being named ``tool_role`` makes a
# half-wired door raise instead of falling back to the legacy reader.
DOOR_FEEDS = (
    "apps/backend/infrastructure/tools/tool_runtime_service.py",
    "apps/backend/application/agent_runtime/use_cases/chat_tool_selection.py",
    "apps/backend/api/tools/controllers/tools_api.py",
    "apps/backend/api/agents/controllers/agents_admin_api.py",
    "apps/backend/infrastructure/agent_runtime/agent_registry_service.py",
    "plugins/tools/platform/agents/catalog.py",
)

_SITE_SQL = "SELECT site_role, role"
_LEGACY_SQL = "SELECT role FROM users"


class _Cursor:
    """Answers the two identity queries so the real readers and their parsing run."""

    def __init__(self, rows: dict[str, tuple[Any, ...]]) -> None:
        self._rows = rows
        self._row: tuple[Any, ...] | None = None

    def execute(self, sql: str, params: Any = None) -> None:
        needle = _SITE_SQL if "site_role" in sql else _LEGACY_SQL
        if needle not in sql:
            raise AssertionError(f"unexpected identity query: {sql}")
        self._row = self._rows[needle]

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False


class _Connection:
    def __init__(self, rows: dict[str, tuple[Any, ...]]) -> None:
        self._rows = rows

    def cursor(self) -> _Cursor:
        return _Cursor(self._rows)

    def commit(self) -> None:
        return None

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False


def _rows(*, site_role: str | None, legacy_role: str) -> dict[str, tuple[Any, ...]]:
    return {
        _SITE_SQL: (site_role, legacy_role),
        _LEGACY_SQL: (legacy_role,),
    }


def _db_row(rows: dict[str, tuple[Any, ...]]):
    pool = MagicMock()
    pool.connection.return_value = _Connection(rows)
    return patch.object(identity_db, "pool", return_value=pool)


def _no_tenant_domain_restriction():
    """The tenant tool-domain allow-list is a different gate; unset is its default."""
    return patch(
        "apps.backend.domain.tenant_capability.policy.tenant_allowed_tool_domains",
        return_value=None,
    )


def _admin_class() -> set[tuple[str, str]]:
    """Live (tool name, package id) for every tool the manifest puts behind admin."""
    reg = get_registry()
    out: set[tuple[str, str]] = set()
    for spec in reg.chat_tool_specs:
        name = str((spec.get("function") or {}).get("name") or "")
        meta = reg.meta_entry_for_tool_name(name) if name else None
        if meta and manifest_min_role(meta, name) == "admin":
            out.add((name, str(meta.get("id") or "")))
    return out


def _visible_tool_names(role: str) -> set[str]:
    reg = get_registry()
    with _no_tenant_domain_restriction():
        kept = filter_chat_tool_specs(reg.chat_tool_specs, reg, {}, role, 1)
    return {str((s.get("function") or {}).get("name")) for s in kept}


def test_the_consoles_sit_behind_an_admin_door() -> None:
    """Otherwise every assertion below could pass on an empty admin class."""
    assert CONSOLE_PACKAGES <= {pkg for _name, pkg in _admin_class()}


def test_demoted_legacy_admin_no_longer_opens_the_door() -> None:
    uid = uuid.uuid4()
    with _db_row(_rows(site_role="site_user", legacy_role="admin")):
        assert identity_db.user_role(uid) == "admin", "the legacy column still says admin"
        role = identity_db.user_effective_role(uid)
        assert role == "user"
        assert caller_fulfills_effective_policy(role, 1, {"min_role": "admin"}) is False
        # The delegate surface resolves through the same helper, so it agrees.
        assert agent_effective_role(uid, "admin") == "user"


def test_site_admin_and_unmigrated_admin_still_open_the_door() -> None:
    uid = uuid.uuid4()
    with _db_row(_rows(site_role="site_admin", legacy_role="user")):
        assert identity_db.user_effective_role(uid) == "admin"
    with _db_row(_rows(site_role=None, legacy_role="admin")):
        assert identity_db.user_effective_role(uid) == "admin", "un-migrated installs keep working"
    assert caller_fulfills_effective_policy("admin", 1, {"min_role": "admin"}) is True


def test_demoted_legacy_admin_is_listed_no_admin_class_tool() -> None:
    admin_names = {name for name, _pkg in _admin_class()}
    uid = uuid.uuid4()
    with _db_row(_rows(site_role="site_user", legacy_role="admin")):
        visible = _visible_tool_names(identity_db.user_effective_role(uid))
    assert visible & admin_names == set()


def test_site_admin_is_listed_every_admin_class_tool() -> None:
    admin_names = {name for name, _pkg in _admin_class()}
    uid = uuid.uuid4()
    with _db_row(_rows(site_role="site_admin", legacy_role="user")):
        visible = _visible_tool_names(identity_db.user_effective_role(uid))
    assert admin_names <= visible


_CHAT_KWARGS: dict[str, Any] = dict(
    plain_completion=False,
    agent_id=None,
    tool_domain=None,
    task_intent_user_text="",
    task_intent_matches=[],
    extra_cats_body=frozenset(),
    extra_cats_hdr=frozenset(),
    cap_hints=frozenset(),
    cfg_tid=1,
    raw_tool_allow=None,
    dashboard_ctx=None,
    model="test-model",
    context_window_tokens=200_000,
    tools_ranking_enabled=False,
    tools_full_schema=True,
    agent_run_id="test-run",
    router_strict_default=False,
)


def _door_calls_during_chat_turn(*, rows: dict[str, tuple[Any, ...]] | None = None) -> tuple[str, set[str]]:
    """Run a chat turn's tool selection, capturing the door call as ``(role, kept names)``.

    Only the filters unrelated to the door are turned off — the category filter would
    otherwise shrink the list below the admin class and make the assertions below pass
    on an empty intersection. The door itself, the identity readers behind the role, and
    the feed's own error handling all run for real.
    """
    captured: list[tuple[str, set[str]]] = []
    real_filter = tool_policy.filter_chat_tool_specs

    def spy(specs: Any, reg: Any, pmap: Any, role: str, tid: int) -> Any:
        kept = real_filter(specs, reg, pmap, role, tid)
        captured.append((role, {str((s.get("function") or {}).get("name")) for s in kept}))
        return kept

    uid = uuid.uuid4()
    body = {"tools": [dict(s) for s in get_registry().chat_tool_specs], "messages": []}

    async def run() -> None:
        token = set_identity(1, uid)
        try:
            with (
                patch.object(chat_selection, "policies_map", return_value={}),
                patch.object(chat_selection, "task_intent_strict_tools", return_value=False),
                patch.object(
                    chat_selection,
                    "filter_merged_tools_by_categories_for_agent",
                    side_effect=lambda tools, *_a, **_k: tools,
                ),
                _no_tenant_domain_restriction(),
                patch.object(tool_policy, "filter_chat_tool_specs", side_effect=spy),
            ):
                if rows is None:
                    with patch.object(identity_db, "user_site_role", side_effect=RuntimeError("db down")):
                        await chat_selection.select_tools_for_chat_turn(body=body, tool_context={}, **_CHAT_KWARGS)
                else:
                    with _db_row(rows):
                        await chat_selection.select_tools_for_chat_turn(body=body, tool_context={}, **_CHAT_KWARGS)
        finally:
            reset_identity(token)

    asyncio.run(run())
    assert len(captured) == 1, f"the chat feed must ask the door exactly once, got {[r for r, _ in captured]}"
    return captured[0]


def test_the_chat_turn_feed_filters_the_admin_class_by_site_role() -> None:
    admin_names = {name for name, _pkg in _admin_class()}
    role, kept = _door_calls_during_chat_turn(rows=_rows(site_role="site_admin", legacy_role="user"))
    assert role == "admin"
    assert admin_names <= kept
    role, kept = _door_calls_during_chat_turn(rows=_rows(site_role="site_user", legacy_role="admin"))
    assert role == "user"
    assert kept & admin_names == set()


def test_the_chat_turn_feed_filters_as_plain_user_when_the_role_is_unresolved() -> None:
    """A failing role read must not skip the filter.

    The block around the door call degrades to forwarding the *unfiltered* list on any
    error, so if the role read itself raised, every admin-class tool would be offered to
    the model for whoever the caller turned out to be.
    """
    admin_names = {name for name, _pkg in _admin_class()}
    assert admin_names  # non-vacuity
    role, kept = _door_calls_during_chat_turn(rows=None)
    assert role == "user"
    assert kept & admin_names == set()


def test_the_registered_adapter_hands_the_door_the_site_role_reading() -> None:
    uid = uuid.uuid4()
    with _db_row(_rows(site_role="site_user", legacy_role="admin")):
        assert tool_dispatch.tool_role(uid) == "user"
    with _db_row(_rows(site_role="site_admin", legacy_role="user")):
        assert tool_dispatch.tool_role(uid) == "admin"


def test_invoking_a_console_tool_is_refused_for_a_demoted_legacy_admin() -> None:
    """The handler behind the door never runs — which is why this can name a real tool."""
    uid = uuid.uuid4()
    token = set_identity(1, uid)
    try:
        with _db_row(_rows(site_role="site_user", legacy_role="admin")), patch.object(
            runtime, "policies_map", return_value={}
        ):
            out = json.loads(tool_dispatch.run_tool("agent_config_snapshot", {}))
    finally:
        reset_identity(token)
    assert out["ok"] is False
    assert "not allowed" in out["error"]


def _http_feed_tool_names(*, site_role: str, legacy_role: str) -> tuple[set[str], set[str]]:
    """The tool names ``GET /v1/tools`` and ``GET /v1/capabilities`` offer this caller."""
    uid = uuid.uuid4()

    async def call() -> tuple[list[Any], dict[str, Any]]:
        with (
            patch.object(tools_api, "resolve_tools_list_identity", return_value=(uid, 1)),
            patch.object(tools_api, "_policies_map_safe", return_value={}),
            _no_tenant_domain_restriction(),
            _db_row(_rows(site_role=site_role, legacy_role=legacy_role)),
        ):
            listed = await tools_api.list_tools(MagicMock())
            caps = await tools_api.list_capabilities(MagicMock())
        return listed["tools"], caps["by_capability"]

    tools, by_cap = asyncio.run(call())
    return (
        {str((t.get("function") or {}).get("name")) for t in tools},
        {str(e.get("tool_name")) for entries in by_cap.values() for e in entries},
    )


def test_the_http_tool_feeds_refuse_a_demoted_legacy_admin() -> None:
    """``GET /v1/tools`` and ``GET /v1/capabilities`` promise what the door enforces."""
    admin_names = {name for name, _pkg in _admin_class()}
    tools, by_cap = _http_feed_tool_names(site_role="site_admin", legacy_role="user")
    assert admin_names <= tools
    assert by_cap & admin_names, "the index has to carry admin-class tools for the check below to mean anything"
    tools, by_cap = _http_feed_tool_names(site_role="site_user", legacy_role="admin")
    assert tools & admin_names == set()
    assert by_cap & admin_names == set()


def _legacy_reads(rel: str) -> list[str]:
    module = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"), filename=rel)
    hits: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Attribute):
            continue
        owner = node.value
        if not isinstance(owner, ast.Name):
            continue
        if node.attr == "user_role" and owner.id == "db":
            hits.append(f"{rel}:{node.lineno} db.user_role")
        elif node.attr == "role" and owner.id == "user":
            hits.append(f"{rel}:{node.lineno} user.role")
    return hits


def test_no_door_feed_reads_the_legacy_column() -> None:
    offenders = [hit for rel in DOOR_FEEDS for hit in _legacy_reads(rel)]
    assert offenders == []
