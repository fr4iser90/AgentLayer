"""Share adapter registry and the Principle 1 gate (ADR 0014 steps 1–2).

The registry is the boundary that makes generic sharing safe, so these tests
target the boundary rather than the adapters behind it:

* an unregistered type is not readable, even though it is grantable
* a projection carrying a credential raises instead of being served
* the credential check keys on names, not value substrings, so the
  legitimate ``source_hint`` value "ics_url" does not trip it
"""

from __future__ import annotations

import unittest
import uuid
from typing import Any
from unittest import mock

from apps.backend.domain.shares import collection_grant, dashboard_grant
from apps.backend.domain.shares.adapters import register_default_share_adapters
from apps.backend.domain.shares.adapter import find_credential_keys
from apps.backend.domain.shares.registry import (
    ShareRegistryError,
    describe_registered,
    get_share_adapter,
    register_share_adapter,
    registered_resource_types,
    reset_share_registry,
    resolve_projection,
)

OWNER = uuid.uuid4()
GRANTEE = uuid.uuid4()
DASH_ID = uuid.uuid4()


class _LeakyAdapter:
    """A deliberately non-compliant adapter, used to prove the gate holds."""

    resource_types = ("leaky",)
    policy_fields = frozenset()
    supports_list = False

    def __init__(self, projection: Any) -> None:
        self._projection = projection

    def normalize_identifier(self, raw: str) -> str | None:
        return (raw or "").strip() or None

    def resolve(self, **kwargs: Any) -> Any:
        return self._projection

    def list_shared(self, grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
        return []


class _BadTypes:
    resource_types: tuple[str, ...] = ()
    policy_fields = frozenset()

    def normalize_identifier(self, raw: str) -> str | None:
        return raw

    def resolve(self, **kwargs: Any) -> Any:
        return None

    def list_shared(self, grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
        return []


class RegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        reset_share_registry()
        register_default_share_adapters()

    def tearDown(self) -> None:
        reset_share_registry()


class TestRegistration(RegistryTestCase):
    def test_shipped_types_are_registered(self) -> None:
        self.assertEqual(registered_resource_types(), ("collection", "dashboard"))

    def test_registering_the_same_instance_twice_is_idempotent(self) -> None:
        adapter = get_share_adapter("dashboard")
        register_share_adapter(adapter)  # must not raise
        self.assertEqual(registered_resource_types(), ("collection", "dashboard"))

    def test_conflicting_registration_is_refused(self) -> None:
        # A silent override would move which adapter enforces a live grant.
        with self.assertRaises(ShareRegistryError):
            register_share_adapter(_DashboardClone())

    def test_adapter_without_types_is_refused(self) -> None:
        with self.assertRaises(ShareRegistryError):
            register_share_adapter(_BadTypes())

    def test_invalid_type_string_is_refused(self) -> None:
        class _Bad:
            resource_types = ("  ",)
            policy_fields = frozenset()

            def normalize_identifier(self, raw):
                return raw

            def resolve(self, **kw):
                return None

            def list_shared(self, g):
                return []

        with self.assertRaises(ShareRegistryError):
            register_share_adapter(_Bad())


class _DashboardClone(_BadTypes):
    resource_types = ("dashboard",)

    def resolve(self, **kw):
        return {"role": "editor"}


class TestLookup(RegistryTestCase):
    def test_unregistered_type_has_no_adapter(self) -> None:
        self.assertIsNone(get_share_adapter("notes"))
        self.assertIsNone(get_share_adapter("payroll_export"))

    def test_lookup_is_canonicalised(self) -> None:
        self.assertIsNotNone(get_share_adapter("  Dashboard  "))


class TestResolveRefusals(RegistryTestCase):
    def test_unregistered_type_is_not_readable(self) -> None:
        # The write side accepts any type; the read side must not follow it.
        out = resolve_projection(
            resource_type="payroll_export",
            owner_user_id=OWNER,
            grantee_user_id=GRANTEE,
            identifier="primary",
        )
        self.assertFalse(out.served)
        self.assertEqual(out.refusal, "no_adapter_registered")
        self.assertIsNone(out.projection)

    def test_malformed_identifier_is_distinguished_from_no_grant(self) -> None:
        out = resolve_projection(
            resource_type="dashboard",
            owner_user_id=OWNER,
            grantee_user_id=GRANTEE,
            identifier="not-a-uuid",
        )
        self.assertFalse(out.served)
        self.assertEqual(out.refusal, "malformed_identifier")

    def test_no_grant_is_its_own_reason(self) -> None:
        with mock.patch.object(
            dashboard_grant, "friend_dashboard_access_detail", return_value=None
        ):
            out = resolve_projection(
                resource_type="dashboard",
                owner_user_id=OWNER,
                grantee_user_id=GRANTEE,
                identifier=str(DASH_ID),
            )
        self.assertFalse(out.served)
        self.assertEqual(out.refusal, "not_granted")


class TestResolveServesExistingAdapters(RegistryTestCase):
    def test_dashboard_grant_projects_through_the_registry(self) -> None:
        detail = dashboard_grant.DashboardAccessDetail(
            role="editor",
            allowed_block_ids=frozenset({"block-shifts"}),
            granular_can_write=True,
        )
        with mock.patch.object(
            dashboard_grant, "friend_dashboard_access_detail", return_value=detail
        ) as called:
            out = resolve_projection(
                resource_type="dashboard",
                owner_user_id=OWNER,
                grantee_user_id=GRANTEE,
                identifier=str(DASH_ID),
            )
        self.assertTrue(out.served)
        self.assertIs(out.projection, detail)
        # Same call the direct path makes — the wrapper changes no behaviour.
        called.assert_called_once_with(GRANTEE, DASH_ID)

    def test_collection_grant_projects_through_the_registry(self) -> None:
        grant = {"policy": {"permission": "view"}, "owner_user_id": OWNER}
        with mock.patch.object(
            collection_grant, "friend_collection_permission", return_value=grant
        ) as called:
            out = resolve_projection(
                resource_type="collection",
                owner_user_id=OWNER,
                grantee_user_id=GRANTEE,
                identifier="haustiere",
            )
        self.assertTrue(out.served)
        self.assertIs(out.projection, grant)
        called.assert_called_once_with(GRANTEE, OWNER, "haustiere")

    def test_dashboard_listing_delegates(self) -> None:
        rows = [{"id": str(DASH_ID), "title": "Ops"}]
        with mock.patch.object(
            dashboard_grant, "list_friend_shared_dashboards", return_value=rows
        ) as called:
            adapter = get_share_adapter("dashboard")
            out = adapter.list_shared(GRANTEE)
        self.assertEqual(out, rows)
        called.assert_called_once_with(GRANTEE)


class TestPrincipleOneGate(RegistryTestCase):
    """A leaking adapter must raise rather than serve."""

    def _resolve_leaky(self, projection):
        register_share_adapter(_LeakyAdapter(projection))
        return resolve_projection(
            resource_type="leaky",
            owner_user_id=OWNER,
            grantee_user_id=GRANTEE,
            identifier="x",
        )

    def test_top_level_url_key_raises(self) -> None:
        with self.assertRaises(ShareRegistryError) as ctx:
            self._resolve_leaky({"summary": "ok", "url": "https://x/y"})
        self.assertIn("url", str(ctx.exception))

    def test_nested_credential_key_raises_and_names_the_path(self) -> None:
        with self.assertRaises(ShareRegistryError) as ctx:
            self._resolve_leaky({"events": [{"title": "a"}], "meta": {"secret": "s"}})
        self.assertIn("meta.secret", str(ctx.exception))

    def test_named_tuple_field_named_secret_raises(self) -> None:
        from collections import namedtuple

        Leaky = namedtuple("Leaky", ["role", "access_token"])
        with self.assertRaises(ShareRegistryError) as ctx:
            self._resolve_leaky(Leaky(role="viewer", access_token="t"))
        self.assertIn("access_token", str(ctx.exception))

    def test_source_hint_value_ics_url_does_not_trip_the_gate(self) -> None:
        # source_hint legitimately takes "ics_url" as its VALUE for
        # non-Google feeds. Keying on values would false-positive here and
        # teach people to weaken the guard.
        register_share_adapter(_LeakyAdapter({"source_hint": "ics_url", "count": 2}))
        out = resolve_projection(
            resource_type="leaky",
            owner_user_id=OWNER,
            grantee_user_id=GRANTEE,
            identifier="x",
        )
        self.assertTrue(out.served)

    def test_real_dashboard_projection_passes_the_gate(self) -> None:
        detail = dashboard_grant.DashboardAccessDetail(
            role="viewer", allowed_block_ids=None, granular_can_write=False
        )
        self.assertEqual(find_credential_keys(detail), [])

    def test_real_collection_grant_projection_passes_the_gate(self) -> None:
        grant = {
            "owner_user_id": str(OWNER),
            "grantee_user_id": str(GRANTEE),
            "resource_type": "collection",
            "resource_identifier": "haustiere",
            "policy": {"permission": "view"},
        }
        self.assertEqual(find_credential_keys(grant), [])


class TestDescribe(RegistryTestCase):
    def test_describe_reports_policy_fields_and_listability(self) -> None:
        d = {x["resource_type"]: x for x in describe_registered()}
        self.assertEqual(d["dashboard"]["policy_fields"], ["block_ids", "expires_at", "permission"])
        self.assertEqual(d["collection"]["policy_fields"], ["expires_at", "permission"])
        self.assertTrue(d["dashboard"]["listable"])
        self.assertFalse(d["collection"]["listable"])

    def test_policy_fields_are_a_subset_of_the_globally_allowed_set(self) -> None:
        # Guards against an adapter declaring a field the validator would
        # reject anyway, which would make step 3 reject every policy.
        from apps.backend.domain.shares.policy import _ALLOWED_POLICY_FIELDS

        for entry in describe_registered():
            for field in entry["policy_fields"]:
                self.assertIn(field, _ALLOWED_POLICY_FIELDS)


if __name__ == "__main__":
    unittest.main()
