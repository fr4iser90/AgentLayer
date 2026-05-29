from __future__ import annotations

import unittest
import uuid
from unittest import mock

from apps.backend.infrastructure.db import share_permissions_db as sp


class TestShareResourceVariants(unittest.TestCase):
    def test_google_calendar_includes_legacy_calendar_alias(self) -> None:
        variants = sp._resource_type_variants(sp.SHARE_RESOURCE_GOOGLE_CALENDAR)
        self.assertEqual(variants, ("google_calendar", "calendar"))

    def test_unknown_type_is_single_variant(self) -> None:
        self.assertEqual(sp._resource_type_variants("notes"), ("notes",))


class TestSharePermissionCheckResolved(unittest.TestCase):
    def test_checks_all_variants_in_one_query(self) -> None:
        owner = uuid.uuid4()
        grantee = uuid.uuid4()
        conn = mock.Mock()
        cursor = mock.Mock()
        cursor.fetchone.return_value = (1,)
        conn.cursor.return_value.__enter__ = mock.Mock(return_value=cursor)
        conn.cursor.return_value.__exit__ = mock.Mock(return_value=False)
        pool = mock.Mock()
        pool.connection.return_value.__enter__ = mock.Mock(return_value=conn)
        pool.connection.return_value.__exit__ = mock.Mock(return_value=False)

        with mock.patch.object(sp, "pool", return_value=pool):
            allowed = sp.share_permission_check_resolved(
                owner_user_id=owner,
                grantee_user_id=grantee,
                resource_type=sp.SHARE_RESOURCE_GOOGLE_CALENDAR,
            )

        self.assertTrue(allowed)
        sql = cursor.execute.call_args[0][0]
        self.assertIn("resource_type = ANY(%s)", sql)
        params = cursor.execute.call_args[0][1]
        self.assertEqual(params[2], ["google_calendar", "calendar"])


class TestFriendSharesTool(unittest.TestCase):
    def test_get_friend_shares_for_unknown_friend(self) -> None:
        from plugins.tools.capabilities.platform.friends import get_friend_shares as gfs

        uid = uuid.uuid4()
        with mock.patch("plugins.tools.capabilities.platform.friends.get_friend_shares.get_identity", return_value=(1, uid)):
            with mock.patch(
                "plugins.tools.capabilities.platform.friends.get_friend_shares.resolve_friend_by_name",
                return_value=None,
            ):
                out = gfs.get_friend_shares({"name": "nobody@example.com"})
        self.assertIn("Could not find", out)

    def test_get_friend_shares_summary_without_name(self) -> None:
        from plugins.tools.capabilities.platform.friends import get_friend_shares as gfs

        uid = uuid.uuid4()
        with mock.patch("plugins.tools.capabilities.platform.friends.get_friend_shares.get_identity", return_value=(1, uid)):
            with mock.patch(
                "plugins.tools.capabilities.platform.friends.get_friend_shares.list_shares_by_owner",
                return_value=[],
            ):
                with mock.patch(
                    "plugins.tools.capabilities.platform.friends.get_friend_shares.list_shares_by_grantee",
                    return_value=[],
                ):
                    out = gfs.get_friend_shares({})
        self.assertIn('"outgoing_count": 0', out)
        self.assertIn('"incoming_count": 0', out)


class TestFriendCalendarSecretLookup(unittest.TestCase):
    def test_friend_calendar_ics_url_prefers_google_calendar(self) -> None:
        from plugins.tools.capabilities.platform.friends.friends_common import friend_calendar_ics_url

        uid = uuid.uuid4()
        with mock.patch(
            "plugins.tools.capabilities.platform.friends.friends_common.db.user_secret_get_plaintext",
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
