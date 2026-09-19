"""Tests for generic share grants and policy enforcement."""

from __future__ import annotations

import sqlite3
import sys
import types
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


class TestFriendCalendarSecretLookup(unittest.TestCase):
    def test_friend_calendar_ics_url_prefers_google_calendar(self) -> None:
        from plugins.tools.integrations.friends.lib.common import friend_calendar_ics_url

        uid = uuid.uuid4()
        with mock.patch(
            "plugins.tools.integrations.friends.lib.common.db.user_secret_get_plaintext",
            side_effect=[
                '{"ics_url":"https://calendar.google.com/calendar/ical/a/basic.ics"}',
                None,
            ],
        ) as get_secret:
            url = friend_calendar_ics_url(uid)
        self.assertEqual(url, "https://calendar.google.com/calendar/ical/a/basic.ics")
        get_secret.assert_any_call(uid, "google_calendar")


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


class TestFriendCalendarTool(unittest.TestCase):
    """The tool needs the grant *row*, not a yes/no — the policy on it caps the
    horizon it may read.

    It used to call a name that was never imported and then read a variable that
    was never assigned, so every call landed in the outer ``except`` handler.
    """

    def _run(self, grant, requested_days=30):
        from plugins.tools.integrations.friends import calendar as cal

        uid = uuid.uuid4()
        friend_id = uuid.uuid4()
        friend = {
            "friend_user_id": str(friend_id),
            "display_name": "Max",
            "email": "max@example.com",
        }
        # The parser is imported inside the function, so it is injected rather
        # than patched at the call site.
        fake_mod = types.ModuleType("plugins.tools.personal.calendar.ics")
        seen = {}

        def fake_calendar_ics(args):
            seen.update(args)
            return {"events": []}

        fake_mod.calendar_ics = fake_calendar_ics
        with mock.patch.dict(sys.modules, {"plugins.tools.personal.calendar.ics": fake_mod}):
            with mock.patch.object(cal, "get_identity", return_value=(1, uid)):
                with mock.patch.object(cal, "resolve_friend_by_name", return_value=friend):
                    with mock.patch.object(cal, "share_permission_get", return_value=grant):
                        with mock.patch.object(
                            cal,
                            "friend_calendar_ics_url",
                            return_value="https://calendar.example.com/basic.ics",
                        ):
                            out = cal.calendar({"name": "Max", "days": requested_days})
        return out, seen

    def test_granted_calendar_reads_the_policy_cap(self) -> None:
        out, seen = self._run({"policy": {"days_ahead": 3}}, requested_days=30)
        self.assertEqual(seen.get("days"), 3)
        self.assertNotIn("is not defined", out)

    def test_grant_without_policy_uses_the_requested_horizon(self) -> None:
        out, seen = self._run({"policy": {}}, requested_days=14)
        self.assertEqual(seen.get("days"), 14)
        self.assertNotIn("is not defined", out)

    def test_no_grant_reports_not_shared(self) -> None:
        out, _ = self._run(None)
        self.assertIn("has not shared their calendar", out)

    def test_the_grant_row_is_fetched_with_the_calendar_resource_type(self) -> None:
        from plugins.tools.integrations.friends import calendar as cal

        uid = uuid.uuid4()
        friend_id = uuid.uuid4()
        friend = {"friend_user_id": str(friend_id), "display_name": "Max"}
        with mock.patch.object(cal, "get_identity", return_value=(1, uid)):
            with mock.patch.object(cal, "resolve_friend_by_name", return_value=friend):
                with mock.patch.object(cal, "share_permission_get", return_value=None) as get_mock:
                    cal.calendar({"name": "Max"})
        kwargs = get_mock.call_args.kwargs
        self.assertEqual(kwargs["resource_type"], sp.SHARE_RESOURCE_GOOGLE_CALENDAR)
        self.assertEqual(kwargs["grantee_user_id"], uid)
        self.assertEqual(kwargs["owner_user_id"], friend_id)


if __name__ == "__main__":
    unittest.main()
