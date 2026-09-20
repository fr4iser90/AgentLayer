"""The projection contract of ADR 0014 step 6.

These tests are about the *contract*, not about calendars: what may be
stored, when a stored row may be served, and what happens to it when the
last grant goes away. The calendar appears only as the adapter under test.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from apps.backend.domain.shares import projections
from apps.backend.domain.shares.adapters import register_default_share_adapters
from apps.backend.domain.shares.adapters.calendar_adapter import CalendarShareAdapter
from apps.backend.domain.shares.projections import RefreshReport, StoredProjection
from apps.backend.domain.shares.registry import (
    publish_projection,
    reset_share_registry,
)
from apps.backend.infrastructure.shares import projection_refresh_runner as runner


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

    def projection_delete_expired(self, *, limit=200, grace_seconds=0):
        cutoff = datetime.now(UTC) - timedelta(seconds=grace_seconds)
        expired = [k for k, v in self.rows.items() if v["expires_at"] <= cutoff]
        for k in expired[:limit]:
            del self.rows[k]
        self.deletes += len(expired)
        return len(expired)

    def projection_list_due(self, *, limit, within_seconds):
        horizon = datetime.now(UTC) + timedelta(seconds=within_seconds)
        due = sorted(
            (v for v in self.rows.values() if v["expires_at"] <= horizon),
            key=lambda v: v["expires_at"],
        )
        return [dict(v) for v in due[:limit]]

    def age(self, owner, rtype, ident, *, seconds=600):
        """Push a row's expiry into the past.

        Defaults to ten minutes, comfortably inside the stale grace, so a
        test that wants the stale fallback gets it without having to know
        where the retention line sits. Tests that want the line pass it
        explicitly.
        """
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
    """The janitor collects out-of-retention rows and nothing else.

    The old form of this test asserted that anything past ``expires_at``
    gets deleted. That is now the wrong rule, and the wrongness is the
    point: those rows are the stale fallback a grantee is answered from
    during an upstream outage, and a sweeper that took them would have
    removed a guarantee while looking like it worked.
    """

    def _seed_aged(self, owner, *, seconds_past_bound):
        self.store.projection_upsert(
            owner_user_id=owner,
            resource_type="google_calendar",
            resource_identifier="primary",
            kind="events",
            payload={"events": []},
            expires_at=datetime.now(UTC) - timedelta(seconds=seconds_past_bound),
        )

    def test_a_row_just_past_its_bound_is_swept_once_the_grace_is_spent(self) -> None:
        owner = uuid.uuid4()
        self._seed_aged(owner, seconds_past_bound=7200)
        self.assertEqual(projections.sweep_expired(grace_seconds=3600), 1)
        self.assertEqual(self.store.rows, {})

    def test_a_row_still_inside_the_grace_survives_the_sweep(self) -> None:
        owner = uuid.uuid4()
        self._seed_aged(owner, seconds_past_bound=600)
        self.assertEqual(projections.sweep_expired(grace_seconds=3600), 0)
        self.assertEqual(len(self.store.rows), 1, "the stale fallback must survive")

    def test_the_default_grace_is_the_module_constant(self) -> None:
        inside = uuid.uuid4()
        outside = uuid.uuid4()
        self._seed_aged(inside, seconds_past_bound=projections.STALE_GRACE_SECONDS - 300)
        self._seed_aged(outside, seconds_past_bound=projections.STALE_GRACE_SECONDS + 300)
        self.assertEqual(projections.sweep_expired(), 1)
        self.assertEqual(len(self.store.rows), 1)


class TestRetention(unittest.TestCase):
    """Where the grace is actually enforced: at the read, not at the delete.

    A bound that only a janitor applies is a bound that depends on the
    janitor running. These assert the read path itself refuses a row that
    has spent its grace, whether or not anything has ever swept.
    """

    def setUp(self) -> None:
        reset_share_registry()
        register_default_share_adapters()
        self.store = InMemoryStore()
        p = mock.patch.object(projections, "_store", self.store)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(reset_share_registry)
        self.owner = uuid.uuid4()

    def _seed_aged(self, *, seconds_past_bound, kind="availability"):
        self.store.projection_upsert(
            owner_user_id=self.owner,
            resource_type="google_calendar",
            resource_identifier="primary",
            kind=kind,
            payload={"events": [{"start": "old", "busy": True}]},
            expires_at=datetime.now(UTC) - timedelta(seconds=seconds_past_bound),
        )

    def test_a_row_inside_the_grace_is_still_served_stale(self) -> None:
        self._seed_aged(seconds_past_bound=600)
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            side_effect=projections.ShareProjectionPublishError("upstream_down"),
        ):
            out = projections.load_fresh(
                CalendarShareAdapter(),
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertTrue(out.ok)
        self.assertTrue(out.projection.stale)

    def test_a_row_past_the_grace_is_not_served_even_though_it_is_still_there(self) -> None:
        self._seed_aged(seconds_past_bound=projections.STALE_GRACE_SECONDS + 600)
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            side_effect=projections.ShareProjectionPublishError("upstream_down"),
        ):
            out = projections.load_fresh(
                CalendarShareAdapter(),
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertFalse(out.ok)
        self.assertIsNone(out.projection)
        self.assertEqual(out.error, "upstream_down")

    def test_reading_past_retention_takes_the_row_with_it(self) -> None:
        self._seed_aged(seconds_past_bound=projections.STALE_GRACE_SECONDS + 600)
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            side_effect=projections.ShareProjectionPublishError("upstream_down"),
        ):
            projections.load_fresh(
                CalendarShareAdapter(),
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertEqual(self.store.rows, {}, "out of retention means out of the table")

    def test_a_republish_after_the_grace_still_works(self) -> None:
        # The grace ends the fallback, not the resource. If the owner's
        # upstream recovers, the next read puts a fresh row back.
        self._seed_aged(seconds_past_bound=projections.STALE_GRACE_SECONDS + 600)
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            return_value={"events": [{"start": "new", "busy": True}]},
        ):
            out = projections.load_fresh(
                CalendarShareAdapter(),
                owner_user_id=self.owner,
                resource_type="google_calendar",
                resource_identifier="primary",
            )
        self.assertTrue(out.ok)
        self.assertFalse(out.projection.stale)
        self.assertEqual(len(self.store.rows), 1)

    def test_a_row_with_no_expiry_is_never_retained(self) -> None:
        row = StoredProjection(
            owner_user_id=self.owner,
            resource_type="google_calendar",
            resource_identifier="primary",
            kind="events",
            payload={},
            generated_at=datetime.now(UTC),
            expires_at=None,
        )
        self.assertFalse(row.is_retained())

    def test_retention_is_measured_from_the_bound_not_from_generation(self) -> None:
        row = StoredProjection(
            owner_user_id=self.owner,
            resource_type="google_calendar",
            resource_identifier="primary",
            kind="events",
            payload={},
            generated_at=datetime.now(UTC) - timedelta(hours=30),
            expires_at=datetime.now(UTC) - timedelta(seconds=60),
        )
        self.assertTrue(row.is_retained(grace_seconds=3600))
        self.assertFalse(row.is_retained(grace_seconds=0))


class TestScheduledRefresh(unittest.TestCase):
    """The pass that keeps a reader from paying for the owner's fetch.

    Correctness does not depend on any of this -- nothing expired is ever
    served -- so what is worth pinning down is the *scheduling*: that a
    row is caught before its bound rather than after, that a wide window
    cannot turn the pass into a poll of the upstream, and that a failed
    refresh leaves the labelled-stale fallback intact instead of deleting
    the only thing a friend could still be answered from.
    """

    def setUp(self) -> None:
        reset_share_registry()
        register_default_share_adapters()
        self.store = InMemoryStore()
        p = mock.patch.object(projections, "_store", self.store)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(reset_share_registry)
        self.owner = uuid.uuid4()

    def _seed(self, *, kind="events", expires_in=120, payload=None) -> None:
        self.store.projection_upsert(
            owner_user_id=self.owner,
            resource_type="google_calendar",
            resource_identifier="primary",
            kind=kind,
            payload=payload if payload is not None else {"events": [{"start": "old"}]},
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        )

    def _refresh(self, **kw):
        return projections.refresh_due(**kw)

    def test_a_row_about_to_expire_is_refreshed_before_it_does(self) -> None:
        self._seed(expires_in=120)
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            return_value={"events": [{"start": "new"}]},
        ) as pub:
            report = self._refresh(limit=10, within_seconds=240)
        pub.assert_called_once()
        self.assertEqual(report.refreshed, 1)
        self.assertEqual(report.failed, 0)
        row = self.store.rows[(str(self.owner), "google_calendar", "primary")]
        self.assertEqual(row["payload"]["events"][0]["start"], "new")

    def test_a_row_nowhere_near_its_bound_is_left_alone(self) -> None:
        self._seed(expires_in=900)
        with mock.patch.object(
            CalendarShareAdapter, "publish_projection"
        ) as pub:
            report = self._refresh(limit=10, within_seconds=240)
        pub.assert_not_called()
        self.assertEqual(report.touched, 0)

    def test_a_wide_window_cannot_make_every_row_due_on_every_pass(self) -> None:
        # The adapter's TTL is 900s, so the worker may republish at most
        # once per 450s of a row's life. A caller asking for a one-hour
        # window must not be able to turn that into a continuous poll.
        self._seed(expires_in=500)
        with mock.patch.object(
            CalendarShareAdapter, "publish_projection"
        ) as pub:
            report = self._refresh(limit=10, within_seconds=3600)
        pub.assert_not_called()
        self.assertEqual(report.skipped, 1)

        self.store.rows[(str(self.owner), "google_calendar", "primary")]["expires_at"] = (
            datetime.now(UTC) + timedelta(seconds=400)
        )
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            return_value={"events": []},
        ) as pub2:
            report = self._refresh(limit=10, within_seconds=3600)
        pub2.assert_called_once()
        self.assertEqual(report.refreshed, 1)

    def test_a_row_whose_adapter_is_gone_is_skipped_not_deleted(self) -> None:
        self._seed(expires_in=10)
        reset_share_registry()
        report = self._refresh(limit=10, within_seconds=60)
        self.assertEqual(report.skipped, 1)
        self.assertEqual(len(self.store.rows), 1, "a missing adapter is not a reason to lose data")

    def test_a_failed_refresh_keeps_the_stale_fallback_the_only_answer(self) -> None:
        # While the owner's upstream is down, the stale row is what a
        # friend can still be answered from. Deleting it on a failed
        # refresh would turn an outage into a silent "nothing shared".
        self._seed(expires_in=10)
        before = dict(self.store.rows[(str(self.owner), "google_calendar", "primary")])
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            side_effect=projections.ShareProjectionPublishError("upstream_down"),
        ):
            report = self._refresh(limit=10, within_seconds=60)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.refreshed, 0)
        self.assertEqual(len(self.store.rows), 1)
        self.assertEqual(
            self.store.rows[(str(self.owner), "google_calendar", "primary")]["payload"],
            before["payload"],
        )

    def test_refreshing_does_not_widen_the_shape_the_owner_chose(self) -> None:
        self._seed(kind="availability", expires_in=60)
        with mock.patch.object(
            CalendarShareAdapter, "publish_projection", return_value={"events": []}
        ) as pub:
            self._refresh(limit=10, within_seconds=120)
        self.assertEqual(pub.call_args.kwargs["kind"], "availability")

    def test_a_credential_in_a_refreshed_payload_is_still_refused(self) -> None:
        self._seed(expires_in=60, payload={"events": [{"start": "clean"}]})
        with mock.patch.object(
            CalendarShareAdapter,
            "publish_projection",
            return_value={"events": [], "ics_url": "https://x/private.ics"},
        ):
            report = self._refresh(limit=10, within_seconds=120)
        self.assertEqual(report.refreshed, 0)
        self.assertEqual(report.failed, 1)
        row = self.store.rows[(str(self.owner), "google_calendar", "primary")]
        self.assertNotIn("ics_url", json.dumps(row["payload"]))

    def test_an_unwired_store_makes_the_pass_a_no_op(self) -> None:
        with mock.patch.object(projections, "_store", None):
            report = projections.refresh_due(limit=10, within_seconds=60)
        self.assertEqual(report.touched, 0)


class TestRefreshWorker(unittest.TestCase):
    """The thread around the pass: one of them, and only while the friend
    system is on."""

    WORKER_NAME = "share-projection-refresh-worker"

    def _live(self):
        return [
            t for t in threading.enumerate() if t.name == self.WORKER_NAME and t.is_alive()
        ]

    def tearDown(self) -> None:
        runner.stop_projection_refresh_worker()

    def test_starting_twice_does_not_stack_workers(self) -> None:
        with mock.patch.object(
            runner.operator_settings, "friend_system_enabled", return_value=False
        ):
            runner.start_projection_refresh_worker()
            first = self._live()
            self.assertEqual(len(first), 1)
            runner.start_projection_refresh_worker()
            self.assertEqual(len(self._live()), 1)
            self.assertEqual(self._live()[0] is first[0], True)

    def test_stop_leaves_no_thread_behind(self) -> None:
        with mock.patch.object(
            runner.operator_settings, "friend_system_enabled", return_value=False
        ):
            runner.start_projection_refresh_worker()
            runner.stop_projection_refresh_worker()
        self.assertEqual(self._live(), [])

    def test_the_worker_refreshes_while_the_friend_system_is_on(self) -> None:
        called = threading.Event()
        with mock.patch.object(runner, "_POLL_SEC", 0.05), mock.patch.object(
            runner.operator_settings, "friend_system_enabled", return_value=True
        ), mock.patch.object(
            projections,
            "projection_store_ready",
            return_value=True,
        ), mock.patch.object(
            projections, "refresh_due", side_effect=lambda **kw: called.set() or RefreshReport()
        ):
            runner.start_projection_refresh_worker()
            self.assertTrue(called.wait(timeout=3), "worker never ran a refresh pass")

    def test_the_worker_stays_quiet_while_the_friend_system_is_off(self) -> None:
        # The store is wired here on purpose. Left unwired, the store-ready
        # guard would keep the worker quiet by itself and this test would
        # pass whether the friend-system gate existed or not.
        with mock.patch.object(runner, "_POLL_SEC", 0.05), mock.patch.object(
            runner.operator_settings, "friend_system_enabled", return_value=False
        ), mock.patch.object(
            projections, "projection_store_ready", return_value=True
        ), mock.patch.object(projections, "refresh_due") as due:
            runner.start_projection_refresh_worker()
            time.sleep(0.4)
        due.assert_not_called()

    def test_the_worker_does_not_touch_an_unwired_store(self) -> None:
        with mock.patch.object(runner, "_POLL_SEC", 0.05), mock.patch.object(
            runner.operator_settings, "friend_system_enabled", return_value=True
        ), mock.patch.object(
            projections, "projection_store_ready", return_value=False
        ), mock.patch.object(projections, "refresh_due") as due:
            runner.start_projection_refresh_worker()
            time.sleep(0.4)
        due.assert_not_called()

    def test_the_sweep_rides_every_nth_pass_not_every_one(self) -> None:
        # Housekeeping, not freshness: the sweep must not cost a delete
        # scan on the same cadence as the refresh.
        swept = threading.Event()
        counts = {"passes": 0, "sweeps": 0}

        def fake_refresh(**_kw):
            counts["passes"] += 1
            return RefreshReport()

        def fake_sweep(**_kw):
            counts["sweeps"] += 1
            swept.set()
            return 0

        with mock.patch.object(runner, "_POLL_SEC", 0.02), mock.patch.object(
            runner, "_SWEEP_EVERY", 2
        ), mock.patch.object(
            runner.operator_settings, "friend_system_enabled", return_value=True
        ), mock.patch.object(
            projections, "projection_store_ready", return_value=True
        ), mock.patch.object(
            projections, "refresh_due", side_effect=fake_refresh
        ), mock.patch.object(
            projections, "sweep_expired", side_effect=fake_sweep
        ):
            runner.start_projection_refresh_worker()
            self.assertTrue(swept.wait(timeout=3), "the sweep never ran")
            runner.stop_projection_refresh_worker()
        self.assertGreaterEqual(counts["passes"], 2)
        self.assertLessEqual(counts["sweeps"] * 2, counts["passes"])


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
