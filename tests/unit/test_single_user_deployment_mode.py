"""The ``single_user`` deployment mode.

A third value on a column whose guards were all written ``!= "multi_tenant"`` is
the risky shape: the new value slips through and behaves like whatever was
already there by accident. These tests pin the three modes apart at each layer
that decides anything, so adding a fourth later has to pass the same bar.
"""

from __future__ import annotations

import pytest

from apps.backend.domain.setup.instance import DEPLOYMENT_MODES

# Import the facade before the readers module. operator_settings and
# operator_settings_readers import each other, and the cycle only unwinds when
# the facade is populated first; importing readers first raises
# "cannot import name 'code_graph_enabled' from a partially initialized module".
from apps.backend.infrastructure.settings import operator_settings  # noqa: F401
from apps.backend.infrastructure.settings import operator_settings_readers as readers


# --- the canonical list ---


def test_three_modes_in_canonical_order() -> None:
    assert DEPLOYMENT_MODES == ("single_user", "agent_system", "multi_tenant")


def test_forms_reexports_the_domain_list() -> None:
    from apps.backend.infrastructure.settings import operator_settings_forms as forms

    assert forms.DEPLOYMENT_MODES is DEPLOYMENT_MODES


# --- reader normalisation ---


@pytest.mark.parametrize("raw", ["single_user", "SINGLE_USER", "  single_user  "])
def test_reader_accepts_single_user(raw: str, monkeypatch) -> None:
    monkeypatch.setattr(readers, "_cached_row", lambda: {"deployment_mode": raw})
    assert readers.deployment_mode() == "single_user"


def test_reader_still_accepts_the_other_two(monkeypatch) -> None:
    for mode in ("agent_system", "multi_tenant"):
        monkeypatch.setattr(readers, "_cached_row", lambda: {"deployment_mode": mode})
        assert readers.deployment_mode() == mode


def test_unknown_mode_falls_back_to_multi_tenant(monkeypatch) -> None:
    monkeypatch.setattr(readers, "_cached_row", lambda: {"deployment_mode": "solo"})
    assert readers.deployment_mode() == "multi_tenant"


def test_unset_mode_falls_back_to_multi_tenant(monkeypatch) -> None:
    monkeypatch.setattr(readers, "_cached_row", lambda: {})
    assert readers.deployment_mode() == "multi_tenant"


# --- the intent predicates, across all three modes ---


@pytest.mark.parametrize(
    "mode,org_surface,single",
    [
        ("single_user", False, True),
        ("agent_system", False, False),
        ("multi_tenant", True, False),
    ],
)
def test_predicates_separate_all_three_modes(mode, org_surface, single, monkeypatch) -> None:
    monkeypatch.setattr(readers, "_cached_row", lambda: {"deployment_mode": mode})
    assert readers.has_org_surface() is org_surface
    assert readers.is_single_user() is single


def test_predicates_are_never_both_true(monkeypatch) -> None:
    """has_org_surface and is_single_user must not overlap in any mode."""
    for mode in (*DEPLOYMENT_MODES, "bogus", ""):
        monkeypatch.setattr(readers, "_cached_row", lambda: {"deployment_mode": mode})
        assert not (readers.has_org_surface() and readers.is_single_user())


# --- patch writer uses the canonical list, not its own copy ---


def test_patch_writer_imports_the_canonical_modes() -> None:
    """The writer used to hardcode ("agent_system", "multi_tenant"), which is
    exactly how a new mode gets silently rejected on write."""
    from apps.backend.infrastructure.settings import operator_settings_patch_writer as w

    assert w.DEPLOYMENT_MODES is DEPLOYMENT_MODES


def test_patch_writer_would_admit_single_user() -> None:
    """Same expression the writer applies, exercised without a database."""
    from apps.backend.infrastructure.settings.operator_settings_patch_writer import (
        DEPLOYMENT_MODES as W,
    )

    v = "single_user"
    assert (v if v in W else "multi_tenant") == "single_user"


# --- the row -> dict mapper, which the reader reads its value from ---

# The reader tests above monkeypatch ``_cached_row`` and so never touch the
# mapper that produces it. That mapper had its own hardcoded
# ("agent_system", "multi_tenant") whitelist, so a ``single_user`` row was
# rewritten to ``multi_tenant`` one step before the (correct) reader looked at
# it — every reader-level assertion stayed green while the mode was dead. These
# go through the real mapper.


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, *_a, **_k):
        return None

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeConn:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _FakeCursor(self._row)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakePool:
    def __init__(self, row):
        self._row = row

    def connection(self):
        return _FakeConn(self._row)


def _mapped_mode(raw, monkeypatch):
    row = [None] * 90
    row[80] = raw
    monkeypatch.setattr(operator_settings.db, "pool", lambda: _FakePool(tuple(row)))
    return operator_settings._fetch_row()["deployment_mode"]


@pytest.mark.parametrize("mode", DEPLOYMENT_MODES)
def test_mapper_preserves_every_declared_mode(mode, monkeypatch) -> None:
    assert _mapped_mode(mode, monkeypatch) == mode


def test_mapper_still_rejects_undeclared_modes(monkeypatch) -> None:
    assert _mapped_mode("solo", monkeypatch) == "multi_tenant"


def test_mapper_whitelist_is_the_canonical_list_not_a_copy(monkeypatch) -> None:
    """Nothing may accept a narrower set than the domain declares."""
    for mode in DEPLOYMENT_MODES:
        assert _mapped_mode(mode, monkeypatch) == mode, f"{mode} dropped by the mapper"
