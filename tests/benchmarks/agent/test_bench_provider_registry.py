"""Unit tests for bench provider registry helpers."""

from __future__ import annotations

from tests.benchmarks.agent.bench_provider_registry import catalog_owned_by_for_endpoint_id


def test_catalog_owned_by_for_endpoint_id() -> None:
    assert catalog_owned_by_for_endpoint_id(1) == "provider_33"
    assert catalog_owned_by_for_endpoint_id(2) == "provider_34"
