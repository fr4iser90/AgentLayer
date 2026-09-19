"""Per-type policy field enforcement (ADR 0014 step 3, fixes §1.9).

Before this, `normalize_policy` ignored its `resource_type` argument and
validated every type against one global field set. An owner could store
`block_ids` on a calendar grant and believe they had restricted it, while
nothing on the calendar path ever read the key. A restriction that is
stored but not read is worse than a refusal, because it is trusted.

Now a registered adapter's declared `policy_fields` is authoritative. A
type with no adapter falls back to the global set — the write side stays
open on purpose (§1.4) — so the narrowing tracks adapter registration
rather than a hardcoded list.
"""

from __future__ import annotations

import unittest
from typing import Any

from apps.backend.domain.shares.adapters import register_default_share_adapters
from apps.backend.domain.shares.policy import normalize_policy
from apps.backend.domain.shares.registry import (
    policy_fields_for,
    register_share_adapter,
    reset_share_registry,
)


class _HonoursNothing:
    """An adapter that declares no fields: every policy key must be refused."""

    resource_types = ("bare_resource",)
    policy_fields: frozenset[str] = frozenset()

    def normalize_identifier(self, raw: str) -> str | None:
        return (raw or "").strip() or None

    def resolve(self, **kwargs: Any) -> Any:
        return None

    def list_shared(self, grantee_user_id) -> list[dict[str, Any]]:
        return []


class EnforcementTestCase(unittest.TestCase):
    def setUp(self) -> None:
        reset_share_registry()
        register_default_share_adapters()

    def tearDown(self) -> None:
        reset_share_registry()


class TestAppWiringIsPinned(EnforcementTestCase):
    """The enforcement only exists if the app actually loads the wiring.

    Without this check a broken import in server_lifecycle would leave the
    registry empty, `policy_fields_for` would return None for everything,
    and every per-type rejection would silently degrade to the lax global
    set — a green suite enforcing nothing.
    """

    def test_server_lifecycle_imports_the_registry_wiring(self) -> None:
        import apps.backend.application.platform.use_cases.server_lifecycle as sl

        self.assertTrue(
            hasattr(sl, "_share_registry_service"),
            "server_lifecycle no longer imports share_registry_service, so the "
            "adapter registry is never populated at startup and step 3 "
            "enforcement is silently absent",
        )

    def test_the_shipped_registry_narrows_the_known_types(self) -> None:
        self.assertEqual(
            policy_fields_for("collection"), frozenset({"permission", "expires_at"})
        )
        self.assertEqual(
            policy_fields_for("dashboard"),
            frozenset({"permission", "block_ids", "expires_at"}),
        )


class TestCollectionRejectsWhatItDoesNotRead(EnforcementTestCase):
    def test_block_ids_rejected_on_collection(self) -> None:
        clean, err = normalize_policy("collection", {"block_ids": ["a"]})
        self.assertEqual(clean, {})
        self.assertIsNotNone(err)
        self.assertIn("block_ids", err)

    def test_list_keys_rejected_on_collection(self) -> None:
        _, err = normalize_policy("collection", {"list_keys": ["a"]})
        self.assertIsNotNone(err)

    def test_days_ahead_rejected_on_collection(self) -> None:
        _, err = normalize_policy("collection", {"days_ahead": 7})
        self.assertIsNotNone(err)

    def test_permission_still_accepted_on_collection(self) -> None:
        clean, err = normalize_policy("collection", {"permission": "view"})
        self.assertIsNone(err)
        self.assertEqual(clean, {"permission": "view"})

    def test_expires_at_still_accepted_on_collection(self) -> None:
        clean, err = normalize_policy(
            "collection", {"expires_at": "2030-01-01T00:00:00Z"}
        )
        self.assertIsNone(err)
        self.assertIn("expires_at", clean)

    def test_error_names_the_adapter_as_the_authority(self) -> None:
        # The message has to say *why*, not just "not allowed" — otherwise an
        # owner cannot tell a typo from a capability gap.
        _, err = normalize_policy("collection", {"block_ids": ["a"]})
        self.assertIn("the collection adapter does not honour it", err)


class TestDashboardKeepsWhatItReads(EnforcementTestCase):
    def test_block_ids_accepted_on_dashboard(self) -> None:
        clean, err = normalize_policy("dashboard", {"block_ids": ["b1", "b2"]})
        self.assertIsNone(err)
        self.assertEqual(clean["block_ids"], ["b1", "b2"])

    def test_list_keys_rejected_on_dashboard(self) -> None:
        _, err = normalize_policy("dashboard", {"list_keys": ["a"]})
        self.assertIsNotNone(err)
        self.assertIn("dashboard", err)

    def test_days_ahead_rejected_on_dashboard(self) -> None:
        _, err = normalize_policy("dashboard", {"days_ahead": 3})
        self.assertIsNotNone(err)


class TestUnregisteredTypesStayOpen(EnforcementTestCase):
    """No adapter means nobody can say a field is meaningless (§1.4)."""

    def test_notes_still_accepts_block_ids(self) -> None:
        clean, err = normalize_policy("notes", {"block_ids": ["a"]})
        self.assertIsNone(err)
        self.assertEqual(clean, {"block_ids": ["a"]})

    def test_unregistered_type_has_no_narrowing_authority(self) -> None:
        self.assertIsNone(policy_fields_for("notes"))
        self.assertIsNone(policy_fields_for("payroll_export"))

    def test_a_truly_unknown_field_is_still_refused_everywhere(self) -> None:
        _, err = normalize_policy("notes", {"nonsense_key": 1})
        self.assertIsNotNone(err)
        self.assertIn("unknown policy field", err)


class TestNoneIsNotEmptySet(EnforcementTestCase):
    """`frozenset()` (adapter honours nothing) must not behave like None."""

    def test_adapter_with_no_fields_rejects_everything(self) -> None:
        register_share_adapter(_HonoursNothing())
        self.assertEqual(policy_fields_for("bare_resource"), frozenset())
        _, err = normalize_policy("bare_resource", {"permission": "view"})
        self.assertIsNotNone(err)

    def test_no_adapter_falls_back_rather_than_rejecting_everything(self) -> None:
        self.assertIsNone(policy_fields_for("notes"))
        _, err = normalize_policy("notes", {"permission": "view"})
        self.assertIsNone(err)


class TestKnownGapIsVisible(EnforcementTestCase):
    """google_calendar is not registry-backed until step 7.

    Asserted rather than left implicit: when step 7 lands and the calendar
    gets a publish_projection adapter, this test starts failing and the
    gap is closed deliberately instead of quietly.
    """

    def test_google_calendar_still_accepts_block_ids(self) -> None:
        clean, err = normalize_policy("google_calendar", {"block_ids": ["x"]})
        self.assertIsNone(err, "calendar is now registry-backed; update this test")
        self.assertEqual(clean, {"block_ids": ["x"]})

    def test_google_calendar_has_no_narrowing_authority_yet(self) -> None:
        self.assertIsNone(policy_fields_for("google_calendar"))


if __name__ == "__main__":
    unittest.main()
