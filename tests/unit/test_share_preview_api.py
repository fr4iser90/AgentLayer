"""The generic share preview endpoint (ADR 0014 step 7).

The calendar-only preview this replaces re-checked the grant in the
controller and then fetched the live ICS feed. The projection contract —
the owner's chosen shape, the freshness bound, the credential gate —
therefore applied to the agent path and to nothing else, and the most
frequently read surface in the product sat outside it. In practice that
meant an owner who had published ``availability`` (busy windows, titles
deliberately dropped) still had event titles rendered in their friend's
dashboard, because the widget read the live feed rather than the
narrowed row.

These tests pin the endpoint to the registry path, which is the only way
the owner's choice reaches the widget at all.
"""

from __future__ import annotations

import asyncio
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from apps.backend.api.sharing.controllers import shares_api
from apps.backend.domain.shares.adapters import register_default_share_adapters
from apps.backend.domain.shares.adapters.calendar_adapter import (
    register_calendar_adapter_dependencies,
)
from apps.backend.domain.shares.projections import register_share_projection_store
from apps.backend.domain.shares.registry import (
    publish_projection,
    reset_share_registry,
)


def _iso(days_from_now: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days_from_now)).isoformat()


class _PreviewDeps:
    """Grant lookup, live calendar read and projection store in one object.

    Deliberately the same object for all three so a test can count how
    often the live read happened: a preview served from a fresh
    projection must not touch it.
    """

    def __init__(self, *, grant: object, events: list[dict]) -> None:
        self._grant = grant
        self._events = events
        self.live_reads: list[tuple] = []
        self.grant_queries: list[tuple] = []
        self.rows: dict[tuple, dict] = {}

    def share_permission_get(self, *, owner_user_id, grantee_user_id, resource_type, resource_identifier):
        self.grant_queries.append((owner_user_id, grantee_user_id, resource_type, resource_identifier))
        return self._grant

    def read_shared_calendar(self, owner_user_id, *, days_ahead):
        self.live_reads.append((owner_user_id, days_ahead))
        return {"ok": True, "events": [dict(e) for e in self._events]}

    def projection_get(self, *, owner_user_id, resource_type, resource_identifier):
        return self.rows.get((str(owner_user_id), resource_type, resource_identifier))

    def projection_upsert(
        self, *, owner_user_id, resource_type, resource_identifier, kind, payload, expires_at
    ):
        self.rows[(str(owner_user_id), resource_type, resource_identifier)] = {
            "owner_user_id": owner_user_id,
            "resource_type": resource_type,
            "resource_identifier": resource_identifier,
            "projection_kind": kind,
            "payload": payload,
            "generated_at": datetime.now(UTC),
            "expires_at": expires_at,
        }

    def projection_delete(self, *, owner_user_id, resource_type, resource_identifier):
        return 1 if self.rows.pop((str(owner_user_id), resource_type, resource_identifier), None) else 0

    def projection_delete_expired(self, *, limit=200, grace_seconds=0):
        return 0

    def projection_list_due(self, *, limit, within_seconds):
        return []

    def projection_list_for_owner(self, *, owner_user_id):
        return [
            dict(v)
            for v in self.rows.values()
            if str(v.get("owner_user_id")) == str(owner_user_id)
        ]


class _Caller:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.id = user_id


class PreviewApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        reset_share_registry()
        register_default_share_adapters()
        self.owner = uuid.uuid4()
        self.grantee = uuid.uuid4()

    def tearDown(self) -> None:
        reset_share_registry()
        register_calendar_adapter_dependencies(None)  # type: ignore[arg-type]
        register_share_projection_store(None)  # type: ignore[arg-type]

    def _wire(self, deps: _PreviewDeps) -> None:
        register_calendar_adapter_dependencies(deps)
        register_share_projection_store(deps)

    def _call(self, **kwargs):
        async def _go():
            async def _current_user(_request):
                return _Caller(self.grantee)

            with mock.patch.object(shares_api, "get_current_user", _current_user):
                return await shares_api.preview_shared_resource(None, **kwargs)

        return asyncio.run(_go())


class TestPreviewGoesThroughTheProjection(PreviewApiTestCase):
    def test_a_fresh_projection_is_served_without_touching_the_live_feed(self) -> None:
        deps = _PreviewDeps(
            grant={"policy": {"days_ahead": 7}},
            events=[{"summary": "Standup", "start": _iso(1)}],
        )
        self._wire(deps)
        publish_projection(
            resource_type="google_calendar", owner_user_id=self.owner, identifier="primary"
        )
        published_reads = len(deps.live_reads)

        out = self._call(resource_type="google_calendar", owner_user_id=str(self.owner))

        self.assertTrue(out["ok"])
        self.assertEqual(
            len(deps.live_reads),
            published_reads,
            "the preview re-fetched the owner's source instead of reading the projection",
        )

    def test_an_availability_preview_carries_no_event_titles(self) -> None:
        """The defect this endpoint replaces, pinned.

        The old preview fetched the live feed regardless of the published
        shape, so the owner's narrowing stopped at the projection boundary
        and never reached the screen that showed it most.
        """
        deps = _PreviewDeps(
            grant={"policy": {"days_ahead": 7}},
            events=[{"summary": "Dentist", "location": "Clinic 4", "start": _iso(1)}],
        )
        self._wire(deps)
        publish_projection(
            resource_type="google_calendar",
            owner_user_id=self.owner,
            identifier="primary",
            kind="availability",
        )

        out = self._call(resource_type="google_calendar", owner_user_id=str(self.owner))
        body = out["preview"]

        self.assertEqual(body["projection_kind"], "availability")
        self.assertTrue(body["events"], "expected the busy windows to still be there")
        for event in body["events"]:
            self.assertNotIn("summary", event)
            self.assertNotIn("location", event)
        self.assertNotIn("Dentist", str(out))

    def test_the_grant_is_enforced_by_the_adapter_not_reimplemented_upstream(self) -> None:
        deps = _PreviewDeps(grant=None, events=[{"summary": "x", "start": _iso(1)}])
        self._wire(deps)
        publish_projection(
            resource_type="google_calendar", owner_user_id=self.owner, identifier="primary"
        )
        with self.assertRaises(Exception) as ctx:
            self._call(resource_type="google_calendar", owner_user_id=str(self.owner))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 403)


class TestPreviewRefusals(PreviewApiTestCase):
    def test_an_unregistered_type_is_404(self) -> None:
        self._wire(_PreviewDeps(grant={"policy": {}}, events=[]))
        with self.assertRaises(Exception) as ctx:
            self._call(resource_type="payroll_export", owner_user_id=str(self.owner))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 404)

    def test_a_live_read_type_is_not_previewable(self) -> None:
        """An adapter that reads live returns a permission decision, not content.

        Offering it in a widget would render an empty box and imply the
        share was broken.
        """
        self._wire(_PreviewDeps(grant={"policy": {}}, events=[]))
        with self.assertRaises(Exception) as ctx:
            self._call(resource_type="collection", owner_user_id=str(self.owner))
        exc = ctx.exception
        self.assertEqual(getattr(exc, "status_code", None), 404)
        self.assertEqual(getattr(exc, "detail", None), "resource type is not previewable")

    def test_a_malformed_owner_id_is_400(self) -> None:
        self._wire(_PreviewDeps(grant={"policy": {}}, events=[]))
        with self.assertRaises(Exception) as ctx:
            self._call(resource_type="google_calendar", owner_user_id="not-a-uuid")
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_the_legacy_alias_still_resolves_to_the_canonical_type(self) -> None:
        deps = _PreviewDeps(
            grant={"policy": {"days_ahead": 7}},
            events=[{"summary": "Standup", "start": _iso(1)}],
        )
        self._wire(deps)
        publish_projection(
            resource_type="google_calendar", owner_user_id=self.owner, identifier="primary"
        )
        out = self._call(resource_type="calendar", owner_user_id=str(self.owner))
        self.assertEqual(out["resource_type"], "google_calendar")


class TestPreviewIdentifier(PreviewApiTestCase):
    def test_the_identifier_defaults_to_the_adapters_own(self) -> None:
        """No identifier passed: the adapter says what its default is.

        Hardcoding "primary" upstream would break the first adapter whose
        shares are not one-per-user.
        """
        deps = _PreviewDeps(
            grant={"policy": {"days_ahead": 7}},
            events=[{"summary": "Standup", "start": _iso(1)}],
        )
        self._wire(deps)
        publish_projection(
            resource_type="google_calendar", owner_user_id=self.owner, identifier="primary"
        )
        out = self._call(resource_type="google_calendar", owner_user_id=str(self.owner))
        self.assertTrue(out["ok"])
        self.assertEqual(deps.grant_queries[-1][3], "primary")

    def test_the_days_hint_reaches_the_adapter(self) -> None:
        """The widget's horizon is passed through; the grant still caps it.

        Without this the query parameter is decoration and the widget's
        ``daysAhead`` prop silently does nothing.
        """
        deps = _PreviewDeps(
            grant={"policy": {"days_ahead": 30}},
            events=[{"summary": "Near", "start": _iso(1)}],
        )
        self._wire(deps)
        publish_projection(
            resource_type="google_calendar", owner_user_id=self.owner, identifier="primary"
        )
        out = self._call(
            resource_type="google_calendar", owner_user_id=str(self.owner), days=3
        )
        self.assertEqual(out["preview"]["days_effective"], 3)


class TestOwnerEmptyIsNotNoGrant(PreviewApiTestCase):
    def test_an_owner_with_nothing_configured_is_served_not_refused(self) -> None:
        """A live grant with no data behind it is not the same as no grant.

        Collapsing the two sends the friend to ask for a permission they
        already hold.
        """
        deps = _PreviewDeps(grant={"policy": {"days_ahead": 7}}, events=[])
        self._wire(deps)
        deps.read_shared_calendar = lambda owner_user_id, *, days_ahead: {
            "ok": False,
            "error": "owner_has_no_calendar_configured",
        }  # type: ignore[assignment]

        publish_projection(
            resource_type="google_calendar", owner_user_id=self.owner, identifier="primary"
        )
        # The publish raises inside the adapter, so nothing was stored; the
        # read then reports the owner-side reason rather than "not granted".
        out = self._call(resource_type="google_calendar", owner_user_id=str(self.owner))
        self.assertTrue(out["ok"])
        self.assertEqual(out["preview"].get("error"), "owner_has_no_calendar_configured")


class TestCatalogAdvertisesPreviewability(PreviewApiTestCase):
    def test_only_projection_backed_types_are_advertised_as_previewable(self) -> None:
        from apps.backend.domain.shares.catalog import catalog_for_api

        by_id = {e["id"]: e for e in catalog_for_api()}
        self.assertTrue(by_id["google_calendar"]["previewable"])
        self.assertFalse(by_id["collection"]["previewable"])
        self.assertFalse(by_id["dashboard"]["previewable"])

    def test_the_advertised_set_matches_what_the_endpoint_serves(self) -> None:
        """A type the catalog calls previewable must not 404, and vice versa."""
        self._wire(_PreviewDeps(grant={"policy": {"days_ahead": 7}}, events=[]))
        from apps.backend.domain.shares.catalog import catalog_for_api

        for entry in catalog_for_api():
            if entry["previewable"]:
                continue
            with self.assertRaises(Exception) as ctx:
                self._call(resource_type=entry["id"], owner_user_id=str(self.owner))
            self.assertEqual(getattr(ctx.exception, "status_code", None), 404)


class TestOwnerSeesOwnPublishedShape(PreviewApiTestCase):
    """The owner picks the shape, so the owner has to be able to see it.

    The shape belongs to the resource, not to a friendship: one row per
    (owner, type, identifier), every grantee of that resource sees the
    same thing. An endpoint that leaked another owner's rows here would be
    the worst possible version of this feature, so that is the first
    thing pinned.
    """

    def _list_as(self, viewer: uuid.UUID):
        async def _go():
            async def _current_user(_request):
                return _Caller(viewer)

            with mock.patch.object(shares_api, "get_current_user", _current_user):
                return await shares_api.list_my_share_projections(None)

        return asyncio.run(_go())

    def _publish(self, kind: str, *, owner=None, ident="primary") -> None:
        publish_projection(
            resource_type="google_calendar",
            owner_user_id=owner or self.owner,
            identifier=ident,
            kind=kind,
        )

    def test_the_owner_sees_the_shape_they_published(self) -> None:
        deps = _PreviewDeps(
            grant={"policy": {}}, events=[{"summary": "Standup", "start": _iso(1)}]
        )
        self._wire(deps)
        self._publish("availability")

        out = self._list_as(self.owner)
        self.assertEqual(len(out["projections"]), 1)
        row = out["projections"][0]
        self.assertEqual(row["projection_kind"], "availability")
        self.assertEqual(row["resource_identifier"], "primary")
        self.assertTrue(row["fresh"])

    def test_the_offered_kinds_come_from_the_adapter(self) -> None:
        """The picker can only offer what this adapter actually publishes."""
        deps = _PreviewDeps(
            grant={"policy": {}}, events=[{"summary": "Standup", "start": _iso(1)}]
        )
        self._wire(deps)
        self._publish("events")

        row = self._list_as(self.owner)["projections"][0]
        self.assertEqual(sorted(row["available_kinds"]), ["availability", "events"])
        self.assertEqual(row["default_kind"], "events")

    def test_another_owner_sees_nothing(self) -> None:
        deps = _PreviewDeps(
            grant={"policy": {}}, events=[{"summary": "Standup", "start": _iso(1)}]
        )
        self._wire(deps)
        self._publish("events")

        self.assertEqual(self._list_as(uuid.uuid4())["projections"], [])

    def test_the_narrowed_content_is_not_returned(self) -> None:
        """The screen shows the shape's name, not the calendar inside it."""
        deps = _PreviewDeps(
            grant={"policy": {}}, events=[{"summary": "Geheim", "start": _iso(1)}]
        )
        self._wire(deps)
        self._publish("events")

        out = self._list_as(self.owner)
        self.assertNotIn("payload", str(out))
        self.assertNotIn("Geheim", str(out))

    def test_a_row_past_its_bound_is_reported_as_not_fresh(self) -> None:
        deps = _PreviewDeps(
            grant={"policy": {}}, events=[{"summary": "Standup", "start": _iso(1)}]
        )
        self._wire(deps)
        self._publish("events")
        for row in deps.rows.values():
            row["expires_at"] = datetime.now(UTC) - timedelta(seconds=30)

        row = self._list_as(self.owner)["projections"][0]
        self.assertFalse(row["fresh"])

    def test_every_identifier_the_owner_published_is_listed(self) -> None:
        """Not just the default one — "work" and "primary" are separate rows."""
        deps = _PreviewDeps(
            grant={"policy": {}}, events=[{"summary": "Standup", "start": _iso(1)}]
        )
        self._wire(deps)
        self._publish("events", ident="primary")
        self._publish("availability", ident="work")

        listed = {
            (r["resource_identifier"], r["projection_kind"])
            for r in self._list_as(self.owner)["projections"]
        }
        self.assertEqual(listed, {("primary", "events"), ("work", "availability")})


if __name__ == "__main__":
    unittest.main()
