"""The role word that still travels is always the resolved one — never the compatibility column.

ADR 0011 §1 demoted ``users.role`` to a compatibility column that may speak for a row only while
that row was never migrated. The elevation *decisions* were moved onto ``users.site_role`` family
by family; what remained is a set of carriers that hand a role word onward (the chat run's user
object, the bridge agent list, the model-override door, the catalog tool's context). Those carriers
are safe exactly as long as the word they carry came out of the identity resolver.

So every fixture here is a row pair — ``(users.site_role, users.role)`` — patched at
``identity_tenants._role_columns``, and never a reader's verdict. A carrier that reached back for
the legacy column would answer ``admin`` for the demoted account and fail.

The four rows cover the whole rule:
``site_user``+``admin`` (demoted, the case the column used to win), ``site_admin`` (elevated),
``NULL``+``admin`` (never migrated, the one case the column still speaks for) and
``NULL``+``NULL`` (row unreadable — deny, everywhere).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import plugins.tools.platform.agents.catalog as catalog_tool
from apps.backend.api.chat.controllers import chat_completions_api
from apps.backend.application.agent_runtime.use_cases import agent_catalog as agent_catalog_uc
from apps.backend.application.agent_runtime.use_cases.chat_run_bootstrap import bootstrap_chat_run
from apps.backend.domain.identity import roles as role_rules
from apps.backend.domain.model_routing.resolution import ModelRoutingSettings, resolve_effective_model
from apps.backend.infrastructure.db import db, identity_tenants
from apps.backend.infrastructure.identity import auth
from apps.backend.infrastructure.integrations import bridge_agent_session
from apps.backend.domain.shared import identity
from apps.backend.domain.tools.invocation_context import (
    reset_agent_run_id,
    reset_agent_task_id,
)

TENANT = 7

#: ``(users.site_role, users.role)`` per actor. Every legacy value claims ``admin`` where a
#: demotion would have left it, so a legacy read is visible as a wrong answer.
DEMOTED: tuple[str, str] = ("site_user", "admin")
SITE_ADMIN: tuple[str, str] = ("site_admin", "admin")
NEVER_MIGRATED: tuple[str | None, str] = (None, "admin")
UNREADABLE: tuple[None, None] = (None, None)

#: (label, row pair, elevated)
ACTORS: list[tuple[str, tuple[str | None, str], bool]] = [
    ("demoted legacy admin", DEMOTED, False),
    ("site admin", SITE_ADMIN, True),
    ("never migrated", NEVER_MIGRATED, True),
    ("unreadable row", UNREADABLE, False),
]


def _resolver_word(row: tuple[str | None, str]) -> str:
    """The word the resolver answers for this row, through the real reader chain."""
    with patch.object(identity_tenants, "_role_columns", lambda _uid, **_kw: row):
        return identity_tenants.user_effective_role(uuid.uuid4())


# --------------------------------------------------------------------------- the resolver, once


def test_the_row_pairs_answer_the_rule_and_nothing_else() -> None:
    assert _resolver_word(DEMOTED) == role_rules.USER
    assert _resolver_word(SITE_ADMIN) == role_rules.ADMIN
    assert _resolver_word(NEVER_MIGRATED) == role_rules.ADMIN, "an unmigrated row keeps working"
    assert _resolver_word(UNREADABLE) == role_rules.USER, "nothing elevates on a row it cannot read"


class _RecordingCursor:
    def __init__(self, row: Any, statements: list[str]) -> None:
        self._row = row
        self._statements = statements

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False

    def execute(self, sql: str, *_args: Any, **_kwargs: Any) -> None:
        self._statements.append(" ".join(sql.split()))

    def fetchone(self) -> Any:
        return self._row


class _RecordingConnection:
    def __init__(self, row: Any, statements: list[str]) -> None:
        self._row = row
        self._statements = statements

    def __enter__(self) -> "_RecordingConnection":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self._row, self._statements)

    def commit(self) -> None:
        return None


class _FakePool:
    """A pool that hands back one fixed row and remembers the statements it was asked to run."""

    def __init__(self, row: Any) -> None:
        self.row = row
        self.statements: list[str] = []

    def connection(self) -> _RecordingConnection:
        return _RecordingConnection(self.row, self.statements)


#: The only statement a role answer may cost — both columns, in one read.
PAIR_STATEMENT = "SELECT site_role, role FROM users WHERE id = %s"


def _statements_of_the_readers() -> dict[str, list[str]]:
    pool = _FakePool(("site_user", "admin"))
    seen: dict[str, list[str]] = {}
    with patch.object(identity_tenants, "pool", lambda: pool):
        for reader in (
            identity_tenants.user_site_role,
            identity_tenants.user_site_admin,
            identity_tenants.user_effective_role,
        ):
            before = len(pool.statements)
            reader(uuid.uuid4())
            seen[reader.__name__] = pool.statements[before:]
    return seen


def test_every_role_reader_costs_the_paired_statement_and_nothing_else() -> None:
    """No reader may resolve a second statement, and none may read the legacy column alone.

    The AST gate cannot see a resolver that quietly grew a second query, so this pins the SQL the
    whole identity layer runs: one paired read per answer.
    """
    for name, statements in _statements_of_the_readers().items():
        assert statements == [PAIR_STATEMENT], f"{name}: {statements}"


def test_the_legacy_reader_is_gone_from_the_facade() -> None:
    """``db.user_role`` answered the legacy column; a repointed caller must not find it again."""
    assert not hasattr(identity_tenants, "user_role")
    assert not hasattr(db, "user_role")


# ------------------------------------------------- 1. the chat run's user object (tool identity)


def _bootstrap_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "body": {"messages": [{"role": "user", "content": "hello"}]},
        "agent_id": None,
        "embedded_subagent": False,
        "bearer_user_role": None,
        "agent_storage_images": [],
        "pre_run_id": None,
        "parent_agent_run_id": None,
        "cancel_event": None,
        "event_emit": None,
        "agent_unattended": False,
        "agent_delegate_mode": None,
        "delegate_allowed_paths": None,
        "delegate_required_branch": None,
        "handoff_collector": None,
        "active_task_body": None,
        "agent_require_workspace_verify": False,
    }
    base.update(overrides)
    return base


@contextlib.contextmanager
def _no_run_store() -> Iterator[None]:
    """Park the run-persist step: it needs a pool and answers nothing about the role."""
    store = SimpleNamespace(insert_run_start_resilient=lambda **_kw: (None, []))
    with patch(
        "apps.backend.application.agent_runtime.use_cases.chat_run_bootstrap.agent_runs_store",
        store,
    ):
        yield


def _carrier_roles(row: tuple[str | None, str], **overrides: Any) -> tuple[str, str]:
    """``(user_obj.role, tool_context["user"].role)`` for one row pair.

    The run's own context tokens are set and reset inside one event loop — ``asyncio.run``
    gives the coroutine its own context copy, so resetting them from the test frame would
    raise — while the identity context belongs to the test frame.
    """

    async def _run() -> tuple[str, str]:
        result = await bootstrap_chat_run(**_bootstrap_kwargs(**overrides))
        try:
            assert result.user_obj is not None
            assert result.tool_context["user"] is result.user_obj
            return str(result.user_obj.role), str(result.tool_context["user"].role)
        finally:
            identity.reset_workspace(result.workspace_token)
            reset_agent_run_id(result.run_ctx_token)
            reset_agent_task_id(result.task_ctx_token)

    token = identity.set_identity(TENANT, uuid.uuid4())
    try:
        with _no_run_store(), patch.object(identity_tenants, "_role_columns", lambda _uid, **_kw: row):
            return asyncio.run(_run())
    finally:
        identity.reset_identity(token)


def test_the_chat_run_carrier_carries_the_resolved_word() -> None:
    """The object handed to tools and workspace gates must not be able to say ``admin`` alone."""
    for label, row, elevated in ACTORS:
        expected = role_rules.ADMIN if elevated else role_rules.USER
        assert _carrier_roles(row) == (expected, expected), label


def test_a_carried_bearer_claim_still_does_not_make_the_carrier_elevated() -> None:
    """``bearer_user_role`` is a hint; it never writes onto the identity context."""
    assert _carrier_roles(DEMOTED, bearer_user_role="admin") == (role_rules.USER, role_rules.USER)


# --------------------------------------------- 2. the agent-visibility door (application layer)


def test_the_agent_door_ignores_a_role_claim_on_the_caller_object() -> None:
    """``user.role`` on the passed object is never asked — the row answers."""
    for label, row, elevated in ACTORS:
        caller = SimpleNamespace(id=uuid.uuid4(), role="admin")
        expected = role_rules.ADMIN if elevated else role_rules.USER
        with patch.object(identity_tenants, "_role_columns", lambda _uid, **_kw: row):
            assert agent_catalog_uc._agent_access_role(caller) == expected, label


def test_the_agent_door_denies_a_caller_without_an_identity() -> None:
    """No id to look up is its own denial — the row pair is never reached."""
    # The stand-in keeps the real guard: only an id can have a row.
    with patch.object(
        identity_tenants,
        "_role_columns",
        lambda uid, **_kw: SITE_ADMIN if uid is not None else (None, None),
    ):
        assert agent_catalog_uc._agent_access_role(None) == role_rules.USER
        assert agent_catalog_uc._agent_access_role(SimpleNamespace(id=None)) == role_rules.USER


# ------------------------------------------- 3. the catalog tool (context can no longer override)


def _catalog_role_passed_to_the_rule(context: dict[str, Any] | None, row: tuple[str | None, str]) -> str:
    seen: dict[str, Any] = {}

    def _fake_catalog(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"agents": []}

    token = identity.set_identity(TENANT, uuid.uuid4())
    try:
        with (
            patch.object(identity_tenants, "_role_columns", lambda _uid, **_kw: row),
            patch.object(catalog_tool.db, "user_tenant_id", lambda _uid: TENANT),
            patch.object(catalog_tool, "build_agents_catalog", side_effect=_fake_catalog),
        ):
            catalog_tool.catalog({}, context=context)
    finally:
        identity.reset_identity(token)
    assert "user_role" in seen, "the catalog rule is no longer fed a role at all"
    return str(seen["user_role"])


def test_the_catalog_tool_takes_its_role_from_the_resolver_not_the_context() -> None:
    """A context key used to be able to hand this tool ``admin``; nothing may write it."""
    for context in (None, {}, {"user_role": "admin"}, {"role": "admin"}, {"user_role": "ADMIN"}):
        assert _catalog_role_passed_to_the_rule(context, DEMOTED) == role_rules.USER, context


def test_the_catalog_tool_still_sees_a_site_admin() -> None:
    """Non-vacuity: the answer is not simply ``user``."""
    assert _catalog_role_passed_to_the_rule({"user_role": "user"}, SITE_ADMIN) == role_rules.ADMIN


# ------------------------------------------------------ 4. the bridge ``/agent list`` surface


class _FakeRegistry:
    def __init__(self, agents: dict[str, dict[str, Any]]) -> None:
        self._agents = agents

    def agent_ids(self) -> list[str]:
        return list(self._agents)

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return self._agents.get(agent_id)


_BRIDGE_AGENTS = {
    "general": {"id": "general", "name": "General", "min_role": "user"},
    "operator": {"id": "operator", "name": "Operator", "min_role": "admin"},
}


def _bridge_visible_agents(row: tuple[str | None, str]) -> list[str]:
    with (
        patch.object(identity_tenants, "_role_columns", lambda _uid, **_kw: row),
        patch(
            "apps.backend.domain.agent_runtime.registry.get_agent_registry",
            return_value=_FakeRegistry(_BRIDGE_AGENTS),
        ),
    ):
        lines = bridge_agent_session._bridge_list_agent_lines(uuid.uuid4())
    return [line.split("`")[1] for line in lines if "`" in line]


def test_the_bridge_lists_an_admin_agent_only_for_an_elevated_caller() -> None:
    for label, row, elevated in ACTORS:
        visible = _bridge_visible_agents(row)
        assert "general" in visible, label
        assert ("operator" in visible) is elevated, f"{label}: {visible}"


# ---------------------------------------- 5. the model-override door (was untested end to end)


_ADMIN_ONLY_OVERRIDE = ModelRoutingSettings(
    profile_default="profile-default",
    allow_model_override=True,
    override_roles=frozenset({"admin"}),
    override_anonymous=False,
)


def _override_won(row: tuple[str | None, str], settings: ModelRoutingSettings = _ADMIN_ONLY_OVERRIDE) -> bool:
    """Ask the door with the word the resolver answers for that row, as every carrier does."""
    with patch.object(identity_tenants, "_role_columns", lambda _uid, **_kw: row):
        word = identity_tenants.user_effective_role(uuid.uuid4())
    _, _, _, is_override = resolve_effective_model(
        messages=[{"role": "user", "content": "hello"}],
        body_model="gpt-override",
        profile_header=None,
        override_header=None,
        bearer_user_role=word,
        settings=settings,
    )
    return bool(is_override)


def test_the_model_override_door_follows_the_resolved_word() -> None:
    for label, row, elevated in ACTORS:
        assert _override_won(row) is elevated, label


def test_the_door_still_opens_without_a_role_list_and_for_anonymous_when_configured() -> None:
    """Non-vacuity: with no role list everyone overrides; anonymity is its own switch."""
    everyone = ModelRoutingSettings(allow_model_override=True, override_roles=frozenset())
    assert _override_won(UNREADABLE, everyone) is True

    anonymous_open = ModelRoutingSettings(
        allow_model_override=True, override_roles=frozenset({"admin"}), override_anonymous=True
    )
    _, _, _, is_override = resolve_effective_model(
        messages=[{"role": "user", "content": "hello"}],
        body_model="gpt-override",
        profile_header=None,
        override_header=None,
        bearer_user_role=None,
        settings=anonymous_open,
    )
    assert is_override is True


def test_a_disabled_override_switch_closes_the_door_for_everyone() -> None:
    closed = ModelRoutingSettings(allow_model_override=False, override_roles=frozenset())
    for label, row, _elevated in ACTORS:
        assert _override_won(row, closed) is False, label


# ------------------------- 6. the identity object the API layer authenticates with (``User.role``)


def _stored_user_row(row: tuple[str | None, str]) -> tuple[Any, ...] | None:
    """The row as ``users`` stores it: ``(id, email, role, site_role, created_at)``.

    Both role columns go in as stored values, never as a verdict. The unreadable actor has no row
    at all, which is what ``(None, None)`` means for this read.
    """
    site, legacy = row
    if site is None and legacy is None:
        return None
    return (uuid.uuid4(), "someone@example.test", legacy, site, datetime.now(UTC))


def _authenticated_user_role(row: tuple[str | None, str]) -> str | None:
    """``User.role`` as ``get_user_by_id`` builds it — the word every bearer consumer believes."""
    with patch.object(auth.db, "pool", lambda: _FakePool(_stored_user_row(row))):
        user = auth.get_user_by_id(uuid.uuid4())
    return None if user is None else str(user.role)


def test_the_authenticated_user_object_carries_the_resolved_word() -> None:
    for label, row, elevated in ACTORS:
        got = _authenticated_user_role(row)
        if row == UNREADABLE:
            assert got is None, label
            continue
        assert got == (role_rules.ADMIN if elevated else role_rules.USER), label


# ----------------------------- 7. the bearer carrier on the OpenAI-compatible endpoint


class _HeadersOnlyRequest:
    """A request with headers and nothing else.

    A carrier that started taking an identity from ``request.state`` or ``request.scope`` fails
    here with ``AttributeError`` instead of quietly trusting a value nobody authenticated.
    """

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def _bearer_word_from_request(row: tuple[str | None, str], headers: dict[str, str]) -> str | None:
    def _lookup(token: str) -> Any:
        # The real choke point's output for that row (section 6): an account, or nobody.
        assert token == "tok", token
        word = _authenticated_user_role(row)
        return None if word is None else SimpleNamespace(id=uuid.uuid4(), role=word)

    with patch.object(chat_completions_api, "get_user_for_bearer_token", side_effect=_lookup):
        return chat_completions_api._bearer_user_role_from_request(_HeadersOnlyRequest(headers))


def test_the_bearer_carrier_forwards_the_authenticated_word_and_nothing_more() -> None:
    for label, row, elevated in ACTORS:
        got = _bearer_word_from_request(row, {"authorization": "Bearer tok"})
        if row == UNREADABLE:
            assert got is None, "no account behind the token, so no word at all"
            continue
        assert got == (role_rules.ADMIN if elevated else role_rules.USER), label


def test_the_bearer_carrier_denies_without_an_authenticated_account() -> None:
    """No token is ``None``, and so is a token that resolves to nobody."""
    assert _bearer_word_from_request(SITE_ADMIN, {}) is None
    assert _bearer_word_from_request(SITE_ADMIN, {"authorization": "Bearer "}) is None
    with patch.object(chat_completions_api, "get_user_for_bearer_token", return_value=None):
        assert chat_completions_api._bearer_user_role_from_request(
            _HeadersOnlyRequest({"authorization": "Bearer tok"})
        ) is None


def test_a_header_claiming_a_role_is_not_the_authenticated_word() -> None:
    """The endpoint used to be reachable with only headers; none of them may speak for the caller."""
    for extra in ({"x-role": "admin"}, {"x-user-role": "admin"}, {"authorization": "Bearer tok", "x-role": "ADMIN"}):
        headers = {"authorization": "Bearer tok", **extra}
        assert _bearer_word_from_request(DEMOTED, headers) == role_rules.USER, headers
