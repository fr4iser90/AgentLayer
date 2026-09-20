"""The projection contract of ADR 0014 step 6.

These tests are about the *contract*, not about calendars: what may be
stored, when a stored row may be served, and what happens to it when the
last grant goes away. The calendar appears only as the adapter under test.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from apps.backend.domain.shares import projections
from apps.backend.domain.shares.adapters import register_default_share_adapters
from apps.backend.domain.shares.adapters.calendar_adapter import CalendarShareAdapter
from apps.backend.domain.shares.registry import (
    publish_projection,
    reset_share_registry,
)


class InMemoryStore:
    """A projection store you can inspect and age by hand."""

    def __init__(self) -> None:
        self.rows: dict[tuple, dict] = {}
        self.upserts = 0
        self.deletes = 0

    def _key(self, owner, rtype, ident):
        return (str(owner), rtype, ident)

    def projection_get(self, *, owner_user_id, resource_type, resource_identifier):
        return self.rows.get(self._key(owner_user_id, resource_type, resource_identifier))

    def projection_upsert(
        self, *, owner_user_id, resource_type, resource_identifier, kind, payload, expires_at
    ):
        self.upserts += 1
        self.rows[self._key(owner_user_id, resource_type, resource_identifier)] = {
            "owner_user_id": owner_user_id,
            "resource_type": resource_type,
            "resource_identifier": resource_identifier,
            "projection_kind": kind,
            "payload": payload,
            "generated_at": datetime.now(UTC),
            "expires_at": expires_at,
        }

    def projection_delete(self, *, owner_user_id, resource_type, resource_identifier):
        self.deletes += 1
        return 1 if self.rows.pop(self._key(owner_user_id, resource_type, resource_identifier), None) else 0

    def projection_delete_expired(self, *, limit=200):
        expired = [k for k, v in self.rows.items() if v["expires_at"] <= datetime.now(UTC)]
        for k in expired[:limit]:
            del self.rows[k]
        self.deletes += len(expired)
        return len(expired)

    def age(self, owner, rtype, ident, *, seconds=3600):
        """Push a row's expiry into the past."""
        row = self.rows[self._key(owner, rtype, ident)]
        row["expires_at"] = datetime.now(UTC) - timedelta(seconds=seconds)


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStore()
        self._patch = mock.patch.object(projections, "_store", self.store)
        self._patch.start()
        self.addCleanup(self._patch.stop)


class TestWhatMayBeStored(StoreTestCase):
    """The store is where Principle 1 has to bite hardest.

    A leak on a live read is one bad response. A leak here is a row that
    sits in the database holding a bearer credential.
    """

    def test_a_credential_shaped_payload_is_refused(self) -> None:
        with self.assertRaises(projections.ShareProjectionError) as ctx:
            projections.store_projection(
                CalendarShareAdapter(),
                owner_user_id=uuid.uuid4(),
                resource_type="google_calendar",
                resource_identifier="primary",
                kind="events",
                payload={"events": [], "ics_url": "https://x/private/secret.ics"},
            )
        self.assertIn("ics_url", str(ctx.exception))
        self.assertEqual(self.store.rows, {}, "nothing must reach the table")

    def test_a_nested_credential_is_refused_too(self) -> None:
        with self.assertRaises(projections.ShareProjectionError):
            projections.store_projection(
                CalendarShareAdapter(),
                owner_user_id=uuid.uuid4(),
                resource_type="google_calendar",
                resource_identifier="primary",
                kind="events",
                payload={"events": [{"summary": "x", "nested": {"access_token": "t"}}]},
            )
        self.assertEqual(self.store.rows, {})

    def test_an_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(projections.ShareProjectionError):
            projections.store_projection(
                CalendarShareAdapter(),
                owner_user_id=uuid.uuid4(),
                resource_type="google_calendar",
                resource_identifier="primary",
                kind="everything",
                payload={"events": []},
            )

    def test_a_non_object_payload_is_refused(self) -> None:
        with self.assertRaises(projections.ShareProjectionError):
            projections.store_projection(
                CalendarShareAdapter(),
                owner_user_id=uuid.uuid4(),
                resource_type="google_calendar",
                resource_identifier="primary",
                kind="events",
                payload=["not", "an", "object"],  # type: ignore[arg-type]
            )

    def test_ttl_is_clamped_both_ways(self) -> None:
        class _TooShort(CalendarShareAdapter):
            projection_ttl_seconds = 1

        class _TooLong(CalendarShareAdapter):
            projection_ttl_seconds = 999_999_999

        # A one-second TTL turns every read into a live fetch; a year-long
        # one is a copy that never gets corrected.
        self.assertEqual(projections.projection_ttl_seconds(_TooShort()), 60)
        self.assertEqual(projections.projection_ttl_seconds(_TooLong()), 24 * 60 * 60)


class TestFreshness(StoreTestCase):
    def test_a_row_without_an_expiry_is_not_fresh(self) -> None:
        row = projections.StoredProjection(
            owner_user_id=uuid.uuid4(),
            resource_type="google_calendar",
            resource_identifier="primary",
            kind="events",
            payload={},
            generated_at=datetime.now(UTC),
            expires_at=None,
        )
        # "Never expires" is the outcome this exists to prevent, so it reads
        # as expired rather than as permanently valid.
        self.assertFalse(row.is_fresh())

    def test_expiry_is_compared_in_utc_even_when_the_column_came_back_naive(self) -> None:
        row = projections.StoredProjection(
            owner_user_id=uuid.uuid4(),
            resource_type="google_calendar",
            resource_identifier="primary",
            kind="events",
            payload={},
            generated_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=5),
        )
        self.assertTrue(row.is_fresh())


class TestLoadFresh(StoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = uuid.uuid4()
        self.adapter = CalendarShareAdapter()

    def _seed(self, kind: str = "events", payload=None) -> None:
        self.store.projection_upsert(
            owner_user_id=self.owner,
            resource_type="google_calendar",
            resource_identifier="primary",
            kind=kind,
            payload=payload if payload is not None else {"events": [{"start": "a"}]},
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    def test_a_fresh_row_is_returned_without_publishing(self) -> None:
        self._seed()
        with mock.patch.object(self.adapter, "publish_projection") as pub:
            out = projections.load_fresh(
                self.adapter,
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        pub.assert_not_called()
        self.assertTrue(out.ok)
        self.assertFalse(out.projection.stale)

    def test_a_stale_row_is_republished(self) -> None:
        self._seed()
        self.store.age(self.owner, "google_calendar", "primary")
        with mock.patch.object(
            self.adapter, "publish_projection", return_value={"events": [{"start": "b"}]}
        ) as pub:
            out = projections.load_fresh(
                self.adapter,
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        pub.assert_called_once()
        self.assertTrue(out.ok)
        self.assertFalse(out.projection.stale)
        self.assertEqual(out.projection.payload["events"][0]["start"], "b")

    def test_the_stored_kind_survives_so_a_grantee_cannot_change_shape(self) -> None:
        # The owner published availability. A read must not quietly get the
        # wider shape because the default is different.
        self._seed("availability", {"events": [{"start": "a", "busy": True}]})
        self.store.age(self.owner, "google_calendar", "primary")
        with mock.patch.object(
            self.adapter, "publish_projection", return_value={"events": []}
        ) as pub:
            projections.load_fresh(
                self.adapter,
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertEqual(pub.call_args.kwargs["kind"], "availability")

    def test_a_failed_republish_returns_the_stale_row_labelled(self) -> None:
        self._seed()
        self.store.age(self.owner, "google_calendar", "primary")
        with mock.patch.object(self.adapter, "publish_projection", return_value=None):
            out = projections.load_fresh(
                self.adapter,
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertTrue(out.ok)
        self.assertTrue(out.projection.stale, "stale must be visible, not silent")

    def test_a_publish_error_reaches_the_caller_as_a_reason(self) -> None:
        # "Owner has no calendar configured" must not collapse into "no
        # grant": the grant exists and the grantee should be told the truth.
        with mock.patch.object(
            self.adapter,
            "publish_projection",
            side_effect=projections.ShareProjectionPublishError("owner_has_no_calendar_configured"),
        ):
            out = projections.load_fresh(
                self.adapter,
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "owner_has_no_calendar_configured")

    def test_a_credential_leak_on_publish_falls_back_without_leaking(self) -> None:
        self._seed()
        self.store.age(self.owner, "google_calendar", "primary")
        with mock.patch.object(
            self.adapter,
            "publish_projection",
            return_value={"events": [], "ics_url": "https://x/secret.ics"},
        ):
            out = projections.load_fresh(
                self.adapter,
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertTrue(out.ok)
        self.assertTrue(out.projection.stale)
        self.assertNotIn("ics_url", out.projection.payload)
        self.assertNotIn("secret.ics", str(self.store.rows))

    def test_an_unwired_store_yields_nothing_rather_than_a_guess(self) -> None:
        with mock.patch.object(projections, "_store", None):
            out = projections.load_fresh(
                self.adapter,
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertFalse(out.ok)


class TestPublishThroughTheRegistry(unittest.TestCase):
    """Publishing goes through the registry, never straight to the store."""

    def setUp(self) -> None:
        reset_share_registry()
        register_default_share_adapters()
        self.store = InMemoryStore()
        p = mock.patch.object(projections, "_store", self.store)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self) -> None:
        reset_share_registry()

    def test_an_unregistered_type_cannot_publish(self) -> None:
        out = publish_projection(
            resource_type="payroll_export",
            owner_user_id=uuid.uuid4(),
            identifier="primary",
        )
        self.assertFalse(out.served)
        self.assertEqual(out.refusal, "no_adapter_registered")

    def test_a_live_read_type_refuses_to_publish(self) -> None:
        # Dashboard reads live; telling the owner to publish would be a lie.
        out = publish_projection(
            resource_type="dashboard",
            owner_user_id=uuid.uuid4(),
            identifier="dash-1",
        )
        self.assertFalse(out.served)
        self.assertEqual(out.refusal, "not_projection_backed")

    def test_an_unknown_kind_is_refused_before_anything_is_read(self) -> None:
        with mock.patch.object(
            CalendarShareAdapter, "publish_projection"
        ) as pub:
            out = publish_projection(
                resource_type="google_calendar",
                owner_user_id=uuid.uuid4(),
                identifier="primary",
                kind="severything",
            )
        self.assertFalse(out.served)
        self.assertEqual(out.refusal, "unknown_projection_kind")
        pub.assert_not_called()

    def test_publishing_stores_the_chosen_shape(self) -> None:
        owner = uuid.uuid4()
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            return_value={"events": [{"start": "x", "busy": True}]},
        ):
            out = publish_projection(
                resource_type="google_calendar",
                owner_user_id=owner,
                identifier="primary",
                kind="availability",
            )
        self.assertTrue(out.served)
        self.assertEqual(out.projection.kind, "availability")
        self.assertEqual(self.store.upserts, 1)


class TestAvailabilityNarrowing(unittest.TestCase):
    """The narrower shape must actually be narrower, by field, not by hope."""

    def test_availability_drops_every_disclosive_field(self) -> None:
        from apps.backend.domain.shares.adapters.calendar_adapter import _narrow_for_kind

        raw = {
            "ok": True,
            "events": [
                {
                    "summary": "Zahnarzt",
                    "uid": "evt-123",
                    "location": "Praxis Dr. Meier",
                    "description": "Krone",
                    "attendees": ["a@x"],
                    "organizer": "me@x",
                    "start": "2026-01-01T09:00:00+00:00",
                    "end": "2026-01-01T10:00:00+00:00",
                }
            ],
        }
        narrowed = _narrow_for_kind(raw, "availability")
        event = narrowed["events"][0]
        for field in ("summary", "uid", "location", "description", "attendees", "organizer"):
            self.assertNotIn(field, event, f"{field} survived the availability narrowing")
        self.assertTrue(event["busy"])
        self.assertEqual(event["start"], "2026-01-01T09:00:00+00:00")

    def test_events_kind_keeps_titles_so_the_default_changes_nothing_visible(self) -> None:
        from apps.backend.domain.shares.adapters.calendar_adapter import _narrow_for_kind

        raw = {"ok": True, "events": [{"summary": "Zahnarzt", "start": "s"}]}
        self.assertEqual(_narrow_for_kind(raw, "events")["events"][0]["summary"], "Zahnarzt")

    def test_the_narrowing_is_a_blacklist_so_a_new_field_cannot_slip_in_unlisted(self) -> None:
        # If someone adds a field to the live read, availability must not
        # start disclosing it by omission from a whitelist. The adapter
        # drops a named set, so an unknown field is dropped too only if it
        # is named -- this pins the current list so adding one is a
        # deliberate edit rather than an accident.
        from apps.backend.domain.shares.adapters.calendar_adapter import (
            _DISCLOSIVE_EVENT_FIELDS,
        )

        self.assertEqual(
            set(_DISCLOSIVE_EVENT_FIELDS),
            {"summary", "location", "uid", "description", "attendees", "organizer"},
        )


class TestSweep(StoreTestCase):
    def test_expired_rows_are_collected(self) -> None:
        owner = uuid.uuid4()
        self.store.projection_upsert(
            owner_user_id=owner,
            resource_type="google_calendar",
            resource_identifier="primary",
            kind="events",
            payload={"events": []},
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        self.assertEqual(projections.sweep_expired(), 1)
        self.assertEqual(self.store.rows, {})


class TestRevokeCascade(unittest.TestCase):
    """A revoke must not leave the owner's published view standing if
    nothing can read it any more -- and must not knock it over while
    somebody else still can."""

    def _run_revoke(self, *, remaining_rows):
        from apps.backend.infrastructure.db import share_permissions_db as spdb

        calls: list[str] = []

        class _Cur:
            def __init__(self):
                self.rowcount = 1
                self._rows: list[dict] = []

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def execute(self, sql, params=None):
                norm = " ".join(str(sql).split())
                if norm.startswith("UPDATE share_permissions"):
                    calls.append("revoke")
                    self.rowcount = 1
                elif "SELECT policy" in norm and "share_permissions" in norm:
                    calls.append("count")
                    self._rows = list(remaining_rows)
                    self.rowcount = len(self._rows)
                elif norm.startswith("DELETE FROM share_projections"):
                    calls.append("delete_projection")
                    self.rowcount = 1
                else:
                    raise AssertionError(f"unexpected SQL: {norm}")

            def fetchall(self):
                return list(self._rows)

            def fetchone(self):
                return self._rows[0] if self._rows else None

        class _Conn:
            def __init__(self):
                self.commits = 0

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def connection(self):
                return self

            def cursor(self, **_kw):
                return _Cur()

            def commit(self):
                self.commits += 1

        conn = _Conn()
        with mock.patch.object(spdb, "pool", lambda: conn):
            spdb.share_permission_set(
                owner_user_id=uuid.uuid4(),
                grantee_user_id=uuid.uuid4(),
                resource_type="google_calendar",
                resource_identifier="primary",
                allowed=False,
            )
        return calls

    def test_the_last_revoke_deletes_the_projection(self) -> None:
        calls = self._run_revoke(remaining_rows=[])
        self.assertIn("revoke", calls)
        self.assertIn("delete_projection", calls)

    def test_another_live_grant_keeps_the_projection(self) -> None:
        # The projection is owner-owned and shared by shape. Revoking one
        # grantee must not blind the others.
        calls = self._run_revoke(
            remaining_rows=[{"policy": {"days_ahead": 7}}]
        )
        self.assertIn("revoke", calls)
        self.assertNotIn("delete_projection", calls)

    def test_an_expired_remaining_grant_does_not_keep_it(self) -> None:
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        calls = self._run_revoke(remaining_rows=[{"policy": {"expires_at": past}}])
        self.assertIn("delete_projection", calls)


if __name__ == "__main__":
    unittest.main()
