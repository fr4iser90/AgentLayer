"""Tests for generic share grants and policy enforcement."""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from apps.backend.domain.shares import policy as share_policy
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

    def test_rejects_days_ahead_for_notes(self) -> None:
        clean, err = share_policy.normalize_policy("notes", {"days_ahead": 7})
        self.assertIsNotNone(err)
        self.assertEqual(clean, {})

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
        from apps.backend.domain.friends.common import friend_calendar_ics_url

        uid = uuid.uuid4()
        with mock.patch(
            "apps.backend.domain.friends.common.db.user_secret_get_plaintext",
            side_effect=[
                '{"ics_url":"https://calendar.google.com/calendar/ical/a/basic.ics"}',
                None,
            ],
        ) as get_secret:
            url = friend_calendar_ics_url(uid)
        self.assertEqual(url, "https://calendar.google.com/calendar/ical/a/basic.ics")
        get_secret.assert_any_call(uid, "google_calendar")


if __name__ == "__main__":
    unittest.main()
