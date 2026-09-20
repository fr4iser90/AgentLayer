"""Tests for generic share grants and policy enforcement."""

from __future__ import annotations

import json
import re
import sqlite3
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from apps.backend.domain.shares import policy as share_policy
from apps.backend.infrastructure.db import friends_db as fdb
from apps.backend.infrastructure.db import share_permissions_db as sp


class TestShareResourceVariants(unittest.TestCase):
    def test_google_calendar_includes_legacy_calendar_alias(self) -> None:
        variants = sp._resource_type_variants(sp.SHARE_RESOURCE_GOOGLE_CALENDAR)
        self.assertIn("google_calendar", variants)
        self.assertIn("calendar", variants)

    def test_unknown_type_is_single_variant(self) -> None:
        self.assertEqual(sp._resource_type_variants("notes"), ("notes",))


class TestSharePolicy(unittest.TestCase):
    def test_normalize_days_ahead(self) -> None:
        clean, err = share_policy.normalize_policy("google_calendar", {"days_ahead": 7})
        self.assertIsNone(err)
        self.assertEqual(clean["days_ahead"], 7)

    def test_accepts_days_ahead_for_any_resource(self) -> None:
        clean, err = share_policy.normalize_policy("notes", {"days_ahead": 7})
        self.assertIsNone(err)
        self.assertEqual(clean["days_ahead"], 7)

    def test_grant_expires_at(self) -> None:
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        self.assertTrue(
            share_policy.grant_is_active(
                is_allowed=True,
                revoked_at=None,
                policy={"expires_at": future},
            )
        )
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        self.assertFalse(
            share_policy.grant_is_active(
                is_allowed=True,
                revoked_at=None,
                policy={"expires_at": past},
            )
        )

    def test_effective_days_ahead_caps_request(self) -> None:
        self.assertEqual(share_policy.effective_days_ahead({"days_ahead": 7}, 30), 7)
        self.assertEqual(share_policy.effective_days_ahead({}, 14), 14)


class TestSharePermissionCheckResolved(unittest.TestCase):
    def test_checks_all_variants_in_one_query(self) -> None:
        owner = uuid.uuid4()
        grantee = uuid.uuid4()
        conn = mock.Mock()
        cursor = mock.Mock()
        cursor.fetchone.return_value = {
            "owner_user_id": owner,
            "grantee_user_id": grantee,
            "resource_type": "google_calendar",
            "resource_identifier": "primary",
            "is_allowed": True,
            "policy": {},
            "revoked_at": None,
            "created_at": None,
            "updated_at": None,
        }
        conn.cursor.return_value.__enter__ = mock.Mock(return_value=cursor)
        conn.cursor.return_value.__exit__ = mock.Mock(return_value=False)
        pool = mock.Mock()
        pool.connection.return_value.__enter__ = mock.Mock(return_value=conn)
        pool.connection.return_value.__exit__ = mock.Mock(return_value=False)

        with mock.patch.object(sp, "pool", return_value=pool):
            grant = sp.share_permission_get(
                owner_user_id=owner,
                grantee_user_id=grantee,
                resource_type=sp.SHARE_RESOURCE_GOOGLE_CALENDAR,
            )

        self.assertIsNotNone(grant)
        sql = cursor.execute.call_args[0][0]
        self.assertIn("resource_type = ANY(%s)", sql)
        params = cursor.execute.call_args[0][1]
        self.assertEqual(params[2], ["google_calendar", "calendar"])


class TestFriendSharesTool(unittest.TestCase):
    def test_get_friend_shares_for_unknown_friend(self) -> None:
        from plugins.tools.integrations.friends import shares as gfs

        uid = uuid.uuid4()
        with mock.patch("plugins.tools.integrations.friends.shares.get_identity", return_value=(1, uid)):
            with mock.patch(
                "plugins.tools.integrations.friends.shares.resolve_friend_by_name",
                return_value=None,
            ):
                out = gfs.shares({"action": "list", "name": "nobody@example.com"})
        self.assertIn("Could not find", out)

    def test_get_friend_shares_summary_without_name(self) -> None:
        from plugins.tools.integrations.friends import shares as gfs

        uid = uuid.uuid4()
        with mock.patch("plugins.tools.integrations.friends.shares.get_identity", return_value=(1, uid)):
            with mock.patch(
                "plugins.tools.integrations.friends.shares.list_shares_by_owner",
                return_value=[],
            ):
                with mock.patch(
                    "plugins.tools.integrations.friends.shares.list_shares_by_grantee",
                    return_value=[],
                ):
                    with mock.patch(
                        "plugins.tools.integrations.friends.shares.catalog_for_api",
                        return_value=[{"id": "google_calendar"}],
                    ):
                        out = gfs.shares({"action": "list"})
        self.assertIn('"outgoing_count": 0', out)
        self.assertIn('"incoming_count": 0', out)

    def test_grant_calendar_with_days_ahead(self) -> None:
        from plugins.tools.integrations.friends import shares as gfs

        uid = uuid.uuid4()
        friend_id = uuid.uuid4()
        friend = {
            "friend_user_id": str(friend_id),
            "display_name": "Max",
            "email": "max@example.com",
        }
        with mock.patch("plugins.tools.integrations.friends.shares.get_identity", return_value=(1, uid)):
            with mock.patch(
                "plugins.tools.integrations.friends.shares.resolve_friend_by_name",
                return_value=friend,
            ):
                with mock.patch(
                    "plugins.tools.integrations.friends.shares.share_permission_set",
                    return_value=True,
                ) as set_mock:
                    out = gfs.shares(
                        {
                            "action": "grant",
                            "name": "Max",
                            "resource_type": "google_calendar",
                            "days_ahead": 7,
                        }
                    )
        self.assertIn('"ok": true', out.lower())
        set_mock.assert_called_once()
        kwargs = set_mock.call_args.kwargs
        self.assertEqual(kwargs["policy"], {"days_ahead": 7})


class _SqliteFriendRequests:
    """Runs the module's real SQL against in-memory sqlite.

    The defect this covers was boolean operator precedence, so asserting on the
    shape of the SQL string would prove nothing — the query has to actually run
    against rows with different statuses.
    """

    def __init__(self, seed: list[tuple[int, int, str, str, str]]) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE friend_requests ("
            " id INTEGER PRIMARY KEY, tenant_id INTEGER, from_user_id TEXT,"
            " to_user_id TEXT, status TEXT, message TEXT,"
            " created_at TEXT, responded_at TEXT)"
        )
        for row in seed:
            self.conn.execute(
                "INSERT INTO friend_requests (id, tenant_id, from_user_id, to_user_id, status)"
                " VALUES (?, ?, ?, ?, ?)",
                row,
            )
        self._cur = None

    def __call__(self):
        return self

    def connection(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self, row_factory=None):
        return self

    def execute(self, sql, params):
        # psycopg binds UUID objects directly; sqlite cannot, so they are passed
        # as the text they would be stored as.
        bound = [str(p) if isinstance(p, uuid.UUID) else p for p in (params or ())]
        self._cur = self.conn.execute(sql.replace("%s", "?"), bound)

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row else None

    def commit(self):
        pass


class TestFriendRequestGetBetweenPrecedence(unittest.TestCase):
    """``status = 'pending'`` has to constrain BOTH sides of the OR.

    The query used to parse as ``(A -> B) OR (B -> A AND pending)`` because AND
    binds tighter than OR. The A->B branch matched any status, so a *declined*
    request kept matching and ``send_friend_request`` refused to create a new one
    with a message claiming it was still pending.
    """

    def _between(self, seed, a, b):
        fake = _SqliteFriendRequests(seed)
        with mock.patch.object(fdb, "pool", fake):
            return fdb.friend_request_get_between(uuid.UUID(a), uuid.UUID(b))

    def test_declined_request_is_not_returned(self) -> None:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        self.assertIsNone(self._between([(1, 1, a, b, "declined")], a, b))

    def test_accepted_request_is_not_returned(self) -> None:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        self.assertIsNone(self._between([(1, 1, a, b, "accepted")], a, b))

    def test_pending_found_in_the_forward_direction(self) -> None:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        row = self._between([(1, 1, a, b, "pending")], a, b)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "pending")

    def test_pending_found_in_the_reverse_direction(self) -> None:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        row = self._between([(1, 1, b, a, "pending")], a, b)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "pending")

    def test_declined_in_one_direction_does_not_hide_pending_in_the_other(self) -> None:
        a, b, c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        # A declined toward B, but C has a live pending request toward A.
        row = self._between([(1, 1, a, b, "declined"), (2, 1, c, a, "pending")], a, c)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], 2)


class _FakeCalendarDeps:
    """Stands in for the injected DB + ICS reader behind CalendarShareAdapter,
    and for the projection store the adapter now reads through.

    One object plays both parts so a test can see the whole loop — publish
    writes here, read reads from here — without a database.
    """

    def __init__(self, grant: object, shared: dict) -> None:
        self._grant = grant
        self._shared = shared
        self.seen: dict[str, object] = {}
        self.rows: dict[tuple, dict] = {}

    def share_permission_get(self, *, owner_user_id, grantee_user_id, resource_type, resource_identifier):
        self.seen["grant_query"] = (
            owner_user_id,
            grantee_user_id,
            resource_type,
            resource_identifier,
        )
        return self._grant

    def read_shared_calendar(self, owner_user_id, *, days_ahead):
        self.seen.setdefault("publishes", []).append((owner_user_id, days_ahead))
        return dict(self._shared)

    # --- ShareProjectionStore ---
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
        return self.rows.pop(
            (str(owner_user_id), resource_type, resource_identifier), None
        ) and 1 or 0

    def projection_delete_expired(self, *, limit=200, grace_seconds=0):
        return 0

    def projection_list_due(self, *, limit, within_seconds):
        return []

    def projection_list_for_owner(self, *, owner_user_id):
        return []

    @property
    def published_kind(self):
        for row in self.rows.values():
            return row["projection_kind"]
        return None


def _iso(days_from_now: float) -> str:
    """Event time relative to now, so a day-cap is actually observable.

    A hard-coded 2026 date sits in the past by the time this runs and so
    survives every window, which would let a broken cap pass.
    """
    return (datetime.now(UTC) + timedelta(days=days_from_now)).isoformat()


class TestFriendCalendarTool(unittest.TestCase):
    """``calendar`` is a thin alias over ``shares(action="read")`` (step 4),
    and that read is served from a published projection (step 6).

    The seam is the calendar adapter's *injected dependencies* plus the
    projection store, so each test drives the real chain — alias, generic
    read action, registry, adapter, projection — and stubs only the
    database, the ICS fetch and the projection table. Patching the tool's
    own internals, as this class used to, asserts against a shape the
    module no longer has; it also would not notice the alias bypassing the
    registry.
    """

    def setUp(self) -> None:
        from apps.backend.domain.shares.adapters import register_default_share_adapters
        from apps.backend.domain.shares.registry import reset_share_registry

        reset_share_registry()
        register_default_share_adapters()

    def tearDown(self) -> None:
        from apps.backend.domain.shares.registry import reset_share_registry

        reset_share_registry()

    def _run(self, grant, requested_days=30, *, shared=None):
        from apps.backend.domain.shares import projections
        from apps.backend.domain.shares.adapters import calendar_adapter
        from plugins.tools.integrations.friends import calendar as cal
        from plugins.tools.integrations.friends import shares as shares_mod

        uid = uuid.uuid4()
        friend_id = uuid.uuid4()
        friend = {
            "friend_user_id": friend_id,  # a real UUID, as friends_list returns
            "display_name": "Max",
            "email": "max@example.com",
        }
        if shared is None:
            shared = {
                "ok": True,
                "source_hint": "google_ical",
                "count": 2,
                "events": [
                    {"summary": "Zahnarzt", "start": _iso(2)},
                    {"summary": "Ferien", "start": _iso(40)},
                ],
            }
        deps = _FakeCalendarDeps(grant, shared)

        with mock.patch.object(shares_mod, "get_identity", return_value=(1, uid)):
            with mock.patch.object(shares_mod, "resolve_friend_by_name", return_value=friend):
                with mock.patch.object(calendar_adapter, "_deps", deps):
                    with mock.patch.object(projections, "_store", deps):
                        out = cal.calendar({"name": "Max", "days": requested_days})
        return out, deps.seen, uid, friend_id, deps

    @staticmethod
    def _summaries(out: str) -> list[str]:
        try:
            parsed = json.loads(out)
        except (ValueError, TypeError):
            return []
        calendar = parsed.get("calendar") or {}
        return [e.get("summary") for e in calendar.get("events") or []]

    def test_granted_calendar_reads_the_policy_cap(self) -> None:
        out, seen, _, _, _ = self._run({"policy": {"days_ahead": 3}}, requested_days=30)
        self.assertIn('"days_effective": 3', out)
        # The 40-day event is outside the three days the owner granted.
        self.assertEqual(self._summaries(out), ["Zahnarzt"])

    def test_grant_without_policy_uses_the_requested_horizon(self) -> None:
        out, seen, _, _, _ = self._run({"policy": {}}, requested_days=14)
        self.assertIn('"days_effective": 14', out)
        self.assertEqual(self._summaries(out), ["Zahnarzt"])

    def test_the_calendar_read_targets_the_friend_not_the_caller(self) -> None:
        # Reading the caller's own calendar would look like a successful share
        # while showing the wrong person's appointments.
        out, seen, caller, friend_id, _ = self._run({"policy": {}})
        published = seen.get("publishes") or []
        self.assertTrue(published, "the owner's calendar was never read")
        for owner, _days in published:
            self.assertEqual(owner, friend_id)
            self.assertNotEqual(owner, caller)

    def test_no_grant_reports_not_shared(self) -> None:
        out, seen, _, _, deps = self._run(None)
        self.assertIn("has not shared their google calendar with you", out)
        self.assertNotIn("publishes", seen)  # never reached the reader
        self.assertEqual(deps.rows, {})  # and nothing was published

    def test_owner_without_a_calendar_secret_is_reported_not_empty(self) -> None:
        out, _, _, _, _ = self._run(
            {"policy": {}}, shared={"ok": False, "error": "owner_has_no_calendar_configured"}
        )
        self.assertIn("owner_has_no_calendar_configured", out)
        self.assertNotIn('"ok": true', out)

    def test_the_alias_output_shape_is_preserved(self) -> None:
        out, _, _, _, _ = self._run({"policy": {"days_ahead": 5}}, requested_days=30)
        parsed = json.loads(out)
        self.assertEqual(parsed["friend_name"], "Max")
        self.assertEqual(parsed["days_requested"], 30)
        self.assertEqual(parsed["days_effective"], 5)
        self.assertEqual(parsed["share_policy"], {"days_ahead": 5})
        self.assertEqual(parsed["calendar"]["count"], 1)
        # The projection envelope is visible to the grantee: which narrowing
        # they are looking at, and whether it is stale.
        self.assertEqual(parsed["calendar"]["projection_kind"], "events")
        self.assertFalse(parsed["calendar"]["projection_stale"])

    def test_the_grant_row_is_fetched_with_the_calendar_resource_type(self) -> None:
        _, seen, caller, friend_id, _ = self._run({"policy": {}})
        owner, grantee, rtype, ident = seen["grant_query"]
        self.assertEqual(owner, friend_id)
        self.assertEqual(grantee, caller)
        self.assertEqual(rtype, sp.SHARE_RESOURCE_GOOGLE_CALENDAR)
        self.assertEqual(ident, "primary")


class TestCalendarAliasStaysThin(unittest.TestCase):
    """The alias must not re-acquire the things step 4 moved out of it."""

    def test_the_alias_does_not_own_the_credential_path(self) -> None:
        from plugins.tools.integrations.friends import calendar as cal

        for name in (
            "fetch_shared_calendar",
            "share_permission_get",
            "effective_days_ahead",
            "friend_calendar_ics_url",
        ):
            self.assertFalse(
                hasattr(cal, name),
                f"calendar.py still carries {name!r}; the read belongs to the adapter",
            )

    def test_a_leaking_reader_cannot_reach_the_grantee_through_the_alias(self) -> None:
        # Principle 1 end to end: even if the underlying reader regressed and
        # returned the bearer URL, the registry gate refuses to serve it and
        # the alias surfaces a refusal instead of the credential.
        from apps.backend.domain.shares.adapters import register_default_share_adapters
        from apps.backend.domain.shares.adapters import calendar_adapter
        from apps.backend.domain.shares.registry import reset_share_registry
        from plugins.tools.integrations.friends import calendar as cal
        from plugins.tools.integrations.friends import shares as shares_mod

        reset_share_registry()
        register_default_share_adapters()

        url = "https://calendar.google.com/calendar/ical/max/private-supersecret/basic.ics"
        deps = _FakeCalendarDeps(
            {"policy": {}},
            {"ok": True, "ics_url": url, "events": []},
        )
        uid, friend_id = uuid.uuid4(), uuid.uuid4()
        from apps.backend.domain.shares import projections

        with mock.patch.object(shares_mod, "get_identity", return_value=(1, uid)):
            with mock.patch.object(
                shares_mod,
                "resolve_friend_by_name",
                return_value={"friend_user_id": friend_id, "display_name": "Max"},
            ):
                with mock.patch.object(calendar_adapter, "_deps", deps):
                    with mock.patch.object(projections, "_store", deps):
                        out = cal.calendar({"name": "Max"})

        self.assertNotIn("private-supersecret", out)
        self.assertNotIn("basic.ics", out)
        self.assertIn("Could not read", out)
        # The gate stopped it at the door of the store, not merely on the
        # way out — a credential must never become a row that sits there.
        self.assertEqual(deps.rows, {})


class TestSharePermissionGetterShape(unittest.TestCase):
    """``share_permission_get`` returns a projection, not the raw row.

    The collection paths read ``grant["is_allowed"]`` and ``grant["revoked_at"]``
    off this dict. Neither key is ever present, so every friend collection grant
    denied regardless of what was stored. These tests pin the returned shape so a
    future change to the getter is noticed rather than silently breaking callers.
    """

    def _raw_row(self, **over: object) -> dict:
        row = {
            "owner_user_id": uuid.uuid4(),
            "grantee_user_id": uuid.uuid4(),
            "resource_type": "collection",
            "resource_identifier": "haustiere",
            "is_allowed": True,
            "policy": {"permission": "view"},
            "revoked_at": None,
            "created_at": None,
            "updated_at": None,
        }
        row.update(over)
        return row

    def _patch_pool(self, row: object):
        cur = mock.MagicMock()
        cur.fetchone.return_value = row
        conn = mock.MagicMock()
        conn.cursor.return_value.__enter__ = mock.Mock(return_value=cur)
        conn.cursor.return_value.__exit__ = mock.Mock(return_value=False)
        pool = mock.MagicMock()
        pool.connection.return_value.__enter__ = mock.Mock(return_value=conn)
        pool.connection.return_value.__exit__ = mock.Mock(return_value=False)
        return mock.patch.object(sp, "pool", return_value=pool)

    def test_returned_dict_carries_no_is_allowed_or_revoked_at(self) -> None:
        owner, grantee = uuid.uuid4(), uuid.uuid4()
        with self._patch_pool(self._raw_row(owner_user_id=owner, grantee_user_id=grantee)):
            got = sp.share_permission_get(
                owner_user_id=owner,
                grantee_user_id=grantee,
                resource_type="collection",
                resource_identifier="haustiere",
            )
        self.assertIsNotNone(got)
        self.assertNotIn("is_allowed", got)
        self.assertNotIn("revoked_at", got)
        self.assertEqual(got["policy"], {"permission": "view"})

    def test_revoked_row_is_absent_rather_than_flagged(self) -> None:
        owner, grantee = uuid.uuid4(), uuid.uuid4()
        revoked = self._raw_row(
            owner_user_id=owner, grantee_user_id=grantee, revoked_at=datetime.now(UTC)
        )
        with self._patch_pool(revoked):
            self.assertIsNone(
                sp.share_permission_get(
                    owner_user_id=owner,
                    grantee_user_id=grantee,
                    resource_type="collection",
                    resource_identifier="haustiere",
                )
            )


class TestCollectionFriendGrantResolves(unittest.TestCase):
    """A friend collection grant must actually grant.

    Regression for the always-deny bug: both collection paths gated on
    ``grant.get("is_allowed")``, a key the getter never returns.
    """

    def setUp(self) -> None:
        self.owner = uuid.uuid4()
        self.grantee = uuid.uuid4()

    def _grant(self, permission: str = "view") -> dict:
        # Exactly what share_permission_get returns — no is_allowed, no revoked_at.
        return {
            "owner_user_id": self.owner,
            "grantee_user_id": self.grantee,
            "resource_type": "collection",
            "resource_identifier": "haustiere",
            "policy": {"permission": permission},
            "created_at": None,
            "updated_at": None,
        }

    def test_access_for_slug_grants_view(self) -> None:
        from apps.backend.domain.collections import access as ca

        with mock.patch.object(ca, "share_permission_get", return_value=self._grant("view")):
            with mock.patch.object(ca.col_db, "normalize_slug", return_value="haustiere"):
                with mock.patch.object(ca.col_db, "collection_get", return_value={"id": uuid.uuid4()}):
                    acc = ca.access_for_slug(self.grantee, "haustiere", owner_user_id=self.owner)
        self.assertIsNotNone(acc)
        self.assertEqual(acc.role, "viewer")
        self.assertFalse(acc.can_write)

    def test_access_for_slug_grants_edit(self) -> None:
        from apps.backend.domain.collections import access as ca

        with mock.patch.object(ca, "share_permission_get", return_value=self._grant("edit")):
            with mock.patch.object(ca.col_db, "normalize_slug", return_value="haustiere"):
                with mock.patch.object(ca.col_db, "collection_get", return_value={"id": uuid.uuid4()}):
                    acc = ca.access_for_slug(self.grantee, "haustiere", owner_user_id=self.owner)
        self.assertIsNotNone(acc)
        self.assertEqual(acc.role, "editor")
        self.assertTrue(acc.can_write)

    def test_no_grant_denies(self) -> None:
        from apps.backend.domain.collections import access as ca

        with mock.patch.object(ca, "share_permission_get", return_value=None):
            with mock.patch.object(ca.col_db, "normalize_slug", return_value="haustiere"):
                self.assertIsNone(
                    ca.access_for_slug(self.grantee, "haustiere", owner_user_id=self.owner)
                )

    def test_friend_collection_permission_grants(self) -> None:
        from apps.backend.domain.shares import collection_grant as cg

        with mock.patch.object(cg, "share_permission_get", return_value=self._grant("view")):
            with mock.patch.object(cg.col_db, "normalize_slug", return_value="haustiere"):
                got = cg.friend_collection_permission(self.grantee, self.owner, "haustiere")
        self.assertIsNotNone(got)
        self.assertEqual(got["policy"], {"permission": "view"})

    def test_friend_collection_permission_denies_without_grant(self) -> None:
        from apps.backend.domain.shares import collection_grant as cg

        with mock.patch.object(cg, "share_permission_get", return_value=None):
            with mock.patch.object(cg.col_db, "normalize_slug", return_value="haustiere"):
                self.assertIsNone(
                    cg.friend_collection_permission(self.grantee, self.owner, "haustiere")
                )

    def test_resolve_collection_reports_read_only(self) -> None:
        from apps.backend.domain.collections import access as ca

        with mock.patch.object(ca, "share_permission_get", return_value=self._grant("view")):
            with mock.patch.object(ca.col_db, "normalize_slug", return_value="haustiere"):
                with mock.patch.object(ca.col_db, "collection_get", return_value={"id": uuid.uuid4()}):
                    acc, col = ca.resolve_collection(
                        self.grantee, "haustiere", owner_user_id=self.owner, need_write=True
                    )
        self.assertIsNone(acc)
        self.assertEqual(col, "read-only access")


class TestAdvertisedSurfaceMatchesEnforcement(unittest.TestCase):
    """What the agent is *told* it may send must match what the grant path accepts.

    Before step 5 the tool advertised one flat set — ``{permission, block_ids,
    list_keys, days_ahead, expires_at}`` — for every type. An agent following
    that help put ``block_ids`` on a calendar grant and got a refusal the help
    had implied was impossible. The text is now derived from the registry, so
    these tests compare the advertised set against ``normalize_policy``
    directly: if the derivation is dropped, or an adapter's declared set and
    the validator disagree, this fails rather than the agent finding out.
    """

    def setUp(self) -> None:
        from apps.backend.domain.shares.adapters import register_default_share_adapters
        from apps.backend.domain.shares.registry import reset_share_registry

        reset_share_registry()
        register_default_share_adapters()

    def tearDown(self) -> None:
        from apps.backend.domain.shares.registry import reset_share_registry

        reset_share_registry()

    def _help_text(self) -> str:
        from plugins.tools.integrations.friends.shares import TOOLS

        return TOOLS[0]["function"]["TOOL_DESCRIPTION"]

    def _advertised_fields(self, rtype: str) -> frozenset | None:
        pattern = re.escape(rtype) + r" accepts \{([^}]*)\}"
        m = re.search(pattern, self._help_text())
        if not m:
            return None
        raw = m.group(1).strip()
        if raw == "nothing":
            return frozenset()
        return frozenset(x.strip() for x in raw.split(",") if x.strip())

    def test_every_type_advertises_exactly_its_enforced_field_set(self) -> None:
        from apps.backend.domain.shares.registry import describe_shareable_types

        for entry in describe_shareable_types():
            advertised = self._advertised_fields(entry["resource_type"])
            self.assertIsNotNone(
                advertised, f"{entry['resource_type']} is not advertised in the help text"
            )
            self.assertEqual(
                advertised,
                frozenset(entry["policy_fields"]),
                f"advertised fields for {entry['resource_type']} diverged from the adapter",
            )

    #: A value the validator will accept for each policy field, so the test
    #: checks "is this field allowed for this type" rather than tripping over
    #: a type mismatch of its own making.
    _SAMPLE = {
        "days_ahead": 7,
        "expires_at": "2026-12-31T00:00:00Z",
        "permission": "view",
        "block_ids": ["block-shifts"],
        "list_keys": ["pets"],
    }

    def test_every_advertised_field_is_actually_accepted_for_its_type(self) -> None:
        from apps.backend.domain.shares.registry import describe_shareable_types

        for entry in describe_shareable_types():
            for field in entry["policy_fields"]:
                self.assertIn(
                    field,
                    self._SAMPLE,
                    f"{field} is declared by an adapter but has no sample value here; "
                    "add one so this test keeps covering it",
                )
                _, err = share_policy.normalize_policy(
                    entry["resource_type"], {field: self._SAMPLE[field]}
                )
                self.assertIsNone(
                    err,
                    f"help advertises {field} on {entry['resource_type']} "
                    f"but the validator rejects it: {err}",
                )

    def test_list_keys_is_advertised_nowhere(self) -> None:
        # Nothing in the repo reads list_keys. Advertising it invites an owner
        # to believe they scoped a share to one list while the reader granted
        # the whole thing — the §1.9.1 defect. It must not appear at all.
        self.assertNotIn("list_keys", self._help_text())

    def test_block_ids_is_advertised_only_where_it_is_honoured(self) -> None:
        from apps.backend.domain.shares.registry import describe_shareable_types

        honouring = {
            e["resource_type"]
            for e in describe_shareable_types()
            if "block_ids" in e["policy_fields"]
        }
        self.assertEqual(honouring, {"dashboard"})
        for entry in describe_shareable_types():
            advertised = self._advertised_fields(entry["resource_type"]) or frozenset()
            if entry["resource_type"] in honouring:
                self.assertIn("block_ids", advertised)
            else:
                self.assertNotIn(
                    "block_ids",
                    advertised,
                    f"{entry['resource_type']} does not read block_ids but advertises it",
                )

    def test_readable_types_are_named_in_the_resource_type_param(self) -> None:
        from plugins.tools.integrations.friends.shares import TOOLS

        param = TOOLS[0]["function"]["parameters"]["properties"]["resource_type"]
        m = re.search(r"Readable here: ([^.]*)\.", param["TOOL_DESCRIPTION"])
        self.assertIsNotNone(m, "the resource_type help does not name the readable types")
        named = sorted(x.strip() for x in m.group(1).split(",") if x.strip())
        # Canonical ids only. Listing the legacy "calendar" alias alongside
        # "google_calendar" would read as two different things to share.
        self.assertEqual(named, ["collection", "dashboard", "google_calendar"])


if __name__ == "__main__":
    unittest.main()
