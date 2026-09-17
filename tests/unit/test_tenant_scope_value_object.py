"""TenantScope value object: predicate shape, matching, post-read guard."""

from __future__ import annotations

import pytest

from apps.backend.domain.identity.tenant_scope import (
    SITE_WIDE_MARKER,
    TenantScope,
    TenantScopeError,
)
from apps.backend.domain.identity.value_objects import TenantId


def test_of_accepts_int_and_tenant_id() -> None:
    assert int(TenantScope.of(7).tenant_id) == 7
    assert int(TenantScope.of(TenantId(7)).tenant_id) == 7


def test_of_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        TenantScope.of(0)
    with pytest.raises(ValueError):
        TenantScope.of(-3)


def test_where_returns_predicate_and_params() -> None:
    clause, params = TenantScope.of(7).where()
    assert clause == "tenant_id = %s"
    assert params == (7,)


def test_where_honours_column_alias() -> None:
    clause, params = TenantScope.of(7).where(column="c.tenant_id")
    assert clause == "c.tenant_id = %s"
    assert params == (7,)


def test_matches_across_representations() -> None:
    scope = TenantScope.of(7)
    assert scope.matches(7) is True
    assert scope.matches(TenantId(7)) is True
    assert scope.matches(TenantScope.of(7)) is True
    assert scope.matches(8) is False


def test_require_matches_passes_same_tenant() -> None:
    TenantScope.of(7).require_matches({"tenant_id": 7}, what="conversation")


def test_require_matches_rejects_other_tenant() -> None:
    with pytest.raises(TenantScopeError, match="another tenant"):
        TenantScope.of(7).require_matches({"tenant_id": 8}, what="conversation")


def test_require_matches_rejects_row_without_tenant() -> None:
    with pytest.raises(TenantScopeError, match="carries no tenant_id"):
        TenantScope.of(7).require_matches({"id": "abc"}, what="conversation")


def test_site_wide_marker_constant_is_stable() -> None:
    # The repository check greps for this exact string; changing it silently
    # un-suppresses every previously marked statement.
    assert SITE_WIDE_MARKER == "tenant-scope: site-wide"
